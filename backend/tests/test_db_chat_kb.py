"""Database checks for migration 0005 (chat, knowledge base, unanswered questions).

Rolled back after each test; writes go to the test clinic CL99 (and CL98 created inside the test).
Skipped when DATABASE_URL is not set.
"""

from uuid import UUID

import asyncpg
import pytest

from app.core.config import get_settings
from tests.conftest import rejected

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")

SID = "s_" + "a" * 32
VID = "v_" + "b" * 32


def vec(*head: float) -> str:
    """A 384-number vector as text, starting with the given numbers and padded with zeros."""
    nums = list(head) + [0.0] * (384 - len(head))
    return "[" + ",".join(str(n) for n in nums) + "]"


async def session(db: asyncpg.Connection, sid: str = SID, clinic: str = "CL99") -> None:
    await db.execute(
        "insert into app.chat_sessions (id, clinic_id, visitor_id) values ($1, $2, $3)", sid, clinic, VID
    )


async def document(db: asyncpg.Connection, clinic: str = "CL99") -> UUID:
    doc: UUID = await db.fetchval(
        "insert into app.kb_documents (clinic_id, file_name, version) values ($1, 'kb.pdf', 1) returning id",
        clinic,
    )
    return doc


async def chunk(db: asyncpg.Connection, doc: UUID, text: str, embedding: str, clinic: str = "CL99") -> None:
    await db.execute(
        """insert into app.kb_chunks (clinic_id, document_id, text, embedding, status)
           values ($1, $2, $3, $4::extensions.vector, 'approved')""",
        clinic,
        doc,
        text,
        embedding,
    )


# ---------- chat


@pytest.mark.parametrize("sid", ["s_123", "s_" + "A" * 32, "x_" + "a" * 32])
async def test_session_ids_must_have_the_widget_format(tx: asyncpg.Connection, sid: str) -> None:
    async with rejected(tx):
        await session(tx, sid)


async def test_messages_belong_to_a_session_of_the_same_clinic(tx: asyncpg.Connection) -> None:
    await session(tx)
    sql = (
        "insert into app.chat_messages (session_id, clinic_id, role, text, event, answered_by) "
        "values ($1, $2, $3, $4, $5, $6)"
    )
    await tx.execute(sql, SID, "CL99", "patient", "Hi", "text", None)
    await tx.execute(sql, SID, "CL99", "bot", "Hello", None, "menu")
    async with rejected(tx):
        await tx.execute(sql, SID, "NFHT", "patient", "Hi", "text", None)  # another clinic
    async with rejected(tx):
        await tx.execute(sql, SID, "CL99", "patient", "Hi", None, None)  # a patient message needs its event
    async with rejected(tx):
        await tx.execute(sql, SID, "CL99", "patient", "Hi", "text", "kb")  # only the bot answers
    async with rejected(tx):
        await tx.execute(sql, SID, "CL99", "patient", "x" * 4001, "text", None)  # too long


async def test_deleting_a_session_deletes_its_messages(tx: asyncpg.Connection) -> None:
    await session(tx)
    await tx.execute(
        "insert into app.chat_messages (session_id, clinic_id, role, text, event) "
        "values ($1, 'CL99', 'patient', 'Hi', 'text')",
        SID,
    )
    await tx.execute("delete from app.chat_sessions where id = $1", SID)
    assert await tx.fetchval("select count(*) from app.chat_messages where session_id = $1", SID) == 0


# ---------- knowledge base


async def test_embeddings_must_have_384_numbers(tx: asyncpg.Connection) -> None:
    doc = await document(tx)
    async with rejected(tx):
        await chunk(tx, doc, "Short vector", "[1,2,3]")
    await chunk(tx, doc, "Right size", vec(1.0))


async def test_chunks_cannot_point_to_another_clinics_document(tx: asyncpg.Connection) -> None:
    doc = await document(tx, "CL99")
    async with rejected(tx):
        await chunk(tx, doc, "Wrong clinic", vec(1.0), clinic="NFHT")


async def test_approved_document_needs_an_approval_time(tx: asyncpg.Connection) -> None:
    async with rejected(tx):
        await tx.execute(
            "insert into app.kb_documents (clinic_id, file_name, version, status) "
            "values ('CL99', 'a.pdf', 1, 'approved')"
        )


async def test_vector_and_keyword_search_return_the_right_chunk(tx: asyncpg.Connection) -> None:
    doc = await document(tx)
    await chunk(tx, doc, "The clinic is open Wednesday to Monday, 10 AM to 7 PM.", vec(1.0, 0.0))
    await chunk(tx, doc, "PRP uses platelet rich plasma from your own blood.", vec(0.0, 1.0))
    nearest = await tx.fetchval(
        """select text from app.kb_chunks where clinic_id = 'CL99' and status = 'approved'
           order by embedding <=> $1::extensions.vector limit 1""",
        vec(0.9, 0.1),
    )
    assert nearest.startswith("The clinic is open")
    by_keyword = await tx.fetchval(
        """select text from app.kb_chunks where clinic_id = 'CL99'
           and tsv @@ websearch_to_tsquery('english', 'platelet plasma')"""
    )
    assert by_keyword.startswith("PRP")


# ---------- unanswered questions


async def test_unanswered_question_reasons(tx: asyncpg.Connection) -> None:
    sql = "insert into app.unanswered_questions (clinic_id, question_text, reason) values ('CL99', $1, $2)"
    await tx.execute(sql, "Is minoxidil safe for me?", "medical")
    async with rejected(tx):
        await tx.execute(sql, "Anything", "other")
    async with rejected(tx):
        await tx.execute(sql, "   ", "no_match")
