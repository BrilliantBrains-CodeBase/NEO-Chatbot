"""Knowledge base facts and Q/A (0014). Rolled back after each test, test clinic CL99."""

import asyncpg
import pytest

from app.core.config import get_settings
from tests.conftest import rejected
from tests.test_db_access import person, signed_in

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")


async def test_facts_and_qa_rules(tx: asyncpg.Connection) -> None:
    await tx.execute(
        "insert into app.kb_facts (clinic_id, key, value) values ('CL99', 'timings', 'Mon 10-7')"
    )
    async with rejected(tx):
        await tx.execute("insert into app.kb_facts (clinic_id, key, value) values ('CL99', 'timings', 'x')")
    async with rejected(tx):
        await tx.execute("insert into app.kb_facts (clinic_id, key, value) values ('CL99', 'Bad Key', 'x')")
    async with rejected(tx):
        await tx.execute(
            "insert into app.kb_facts (clinic_id, key, value, status) values ('CL99', 'a1', 'x', 'approved')"
        )
    await tx.execute(
        "insert into app.kb_qa (clinic_id, question, variants, answer) "
        "values ('CL99', 'What does a hair transplant cost?', 'transplant kitne ka hai', 'Rs 60 to 100.')"
    )
    hits = await tx.fetchval(
        "select count(*) from app.kb_qa "
        "where clinic_id = 'CL99' and tsv @@ websearch_to_tsquery('english', 'costs')"
    )
    hinglish = await tx.fetchval(
        "select count(*) from app.kb_qa "
        "where clinic_id = 'CL99' and tsv @@ plainto_tsquery('simple', 'kitne')"
    )
    assert hits == 1 and hinglish == 1


async def test_only_managers_of_the_clinic_see_the_kb(tx: asyncpg.Connection) -> None:
    await tx.execute("insert into app.kb_facts (clinic_id, key, value) values ('CL99', 'phone', '+91 1')")
    desk = await person(tx, "desk", "CL99", "front_desk")
    boss = await person(tx, "boss", "CL99", "clinic_manager")
    async with signed_in(tx, desk):
        assert await tx.fetchval("select count(*) from app.kb_facts") == 0
    async with signed_in(tx, boss):
        assert await tx.fetchval("select count(*) from app.kb_facts where clinic_id = 'CL99'") == 1
        async with rejected(tx):
            await tx.execute("delete from app.kb_facts")
