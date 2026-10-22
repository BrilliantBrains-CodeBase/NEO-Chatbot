"""Patient data deletion (migration 0011): everything about the person goes, only the fact remains.

Rolled back after each test; data in CL99 and a second test clinic CL98. Skipped without DATABASE_URL.
"""

from uuid import UUID

import asyncpg
import pytest

from app.core.config import get_settings
from tests.conftest import rejected
from tests.test_db_access import person, signed_in
from tests.test_db_audit import new_lead

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")

SID = "s_" + "c" * 32


async def full_history(db: asyncpg.Connection, lead: UUID) -> None:
    """A request, appointment, task, timeline entry, message, chat and question for the lead."""
    req = await db.fetchval(
        "insert into app.requests (clinic_id, lead_id, type) values ('CL99', $1, 'book') returning id", lead
    )
    await db.execute(
        """insert into app.appointments (clinic_id, lead_id, request_id, type, preferred_date)
           values ('CL99', $1, $2, 'in_clinic', current_date + 1)""",
        lead,
        req,
    )
    await db.execute(
        "insert into app.tasks (clinic_id, lead_id, type, due_at) "
        "values ('CL99', $1, 'call_new_lead', now())",
        lead,
    )
    await db.execute(
        "insert into app.lead_events (clinic_id, lead_id, kind) values ('CL99', $1, 'contact')", lead
    )
    await db.execute(
        "insert into app.outbox (clinic_id, channel, kind, lead_id) "
        "values ('CL99', 'whatsapp', 'booked', $1)",
        lead,
    )
    await db.execute(
        "insert into app.chat_sessions (id, clinic_id, visitor_id, lead_id) values ($1, 'CL99', $2, $3)",
        SID,
        "v_" + "0" * 32,
        lead,
    )
    await db.execute(
        "insert into app.chat_messages (session_id, clinic_id, role, text, event) "
        "values ($1, 'CL99', 'patient', 'My number is 9800000001', 'text')",
        SID,
    )
    await db.execute(
        "insert into app.unanswered_questions (clinic_id, question_text, reason, lead_id) "
        "values ('CL99', 'Is it safe for me?', 'medical', $1)",
        lead,
    )
    await db.execute(
        "update app.leads set full_name = 'Priya Sharma' where id = $1", lead
    )  # an audited change


async def leftovers(db: asyncpg.Connection, lead: UUID) -> dict[str, int]:
    checks = {
        "leads": "select count(*) from app.leads where id = $1",
        "requests": "select count(*) from app.requests where lead_id = $1",
        "appointments": "select count(*) from app.appointments where lead_id = $1",
        "tasks": "select count(*) from app.tasks where lead_id = $1",
        "lead_events": "select count(*) from app.lead_events where lead_id = $1",
        "outbox": "select count(*) from app.outbox where lead_id = $1",
        "unanswered": "select count(*) from app.unanswered_questions where lead_id = $1",
        # Any audit row still holding personal details (name or phone) about this lead.
        "audit_details": "select count(*) from app.audit_log "
        "where row_id = $1::uuid::text and changed::text ~ 'Priya|98000'",
    }
    counts = {k: await db.fetchval(sql, lead) for k, sql in checks.items()}
    counts["chat"] = await db.fetchval("select count(*) from app.chat_messages where session_id = $1", SID)
    return counts


async def test_manager_deletes_everything_and_only_the_fact_remains(tx: asyncpg.Connection) -> None:
    lead = await new_lead(tx)
    code = await tx.fetchval("select lead_code from app.leads where id = $1", lead)
    await full_history(tx, lead)
    boss = await person(tx, "boss", "CL99", "clinic_manager")
    async with signed_in(tx, boss):
        assert await tx.fetchval("select app.delete_patient_data($1)", lead) == code
    assert set((await leftovers(tx, lead)).values()) == {0}
    fact = await tx.fetchrow(
        "select * from app.audit_log where table_name = 'privacy_request' and row_id = $1", code
    )
    assert fact["actor"] == boss
    assert fact["action"] == "delete"


async def test_only_a_manager_of_that_clinic_can_delete(tx: asyncpg.Connection) -> None:
    await tx.execute(
        "insert into app.clinics (id, name, bot_name, open_time, close_time, is_test) "
        "values ('CL98', 'Test Clinic 2', 'Test2 AI', '10:00', '19:00', true)"
    )
    lead = await new_lead(tx)
    desk = await person(tx, "desk", "CL99", "front_desk")
    other_boss = await person(tx, "otherboss", "CL98", "clinic_manager")
    for who in (desk, other_boss):
        async with signed_in(tx, who):
            async with rejected(tx):
                await tx.fetchval("select app.delete_patient_data($1)", lead)
    assert await tx.fetchval("select count(*) from app.leads where id = $1", lead) == 1
    async with signed_in(tx, None):  # anon cannot even call it
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            async with tx.transaction():
                await tx.fetchval("select app.delete_patient_data($1)", lead)


async def test_a_patient_record_shared_with_another_lead_is_kept(tx: asyncpg.Connection) -> None:
    patient = await tx.fetchval(
        "insert into app.patients (clinic_id, full_name, phone_e164) "
        "values ('CL99', 'Priya', '+919800000001') returning id"
    )
    first, second = await new_lead(tx), await new_lead(tx, phone="+919800000009")
    await tx.execute("update app.leads set patient_id = $1 where id in ($2, $3)", patient, first, second)
    await tx.fetchval("select app.delete_patient_data($1)", first)  # the backend, no signed-in user
    assert await tx.fetchval("select count(*) from app.patients where id = $1", patient) == 1
    await tx.fetchval("select app.delete_patient_data($1)", second)  # the last lead using it
    assert await tx.fetchval("select count(*) from app.patients where id = $1", patient) == 0
