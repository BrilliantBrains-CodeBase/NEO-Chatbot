"""Audit log (migration 0007): written by the database, never edited, readable by managers and BB Admin.

Rolled back after each test; data in CL99 and a second test clinic CL98. Skipped without DATABASE_URL.
"""

import json
from uuid import UUID

import asyncpg
import pytest

from app.core.config import get_settings
from tests.conftest import rejected
from tests.test_db_access import person, signed_in

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")


async def new_lead(db: asyncpg.Connection, clinic: str = "CL99", phone: str = "+919800000001") -> UUID:
    lead: UUID = await db.fetchval(
        "insert into app.leads (clinic_id, full_name, phone_e164, source) "
        "values ($1, 'Lead', $2, 'chatbot') returning id",
        clinic,
        phone,
    )
    return lead


async def log_for(db: asyncpg.Connection, lead: UUID) -> list[asyncpg.Record]:
    rows: list[asyncpg.Record] = await db.fetch(
        "select action, actor, changed from app.audit_log "
        "where table_name = 'leads' and row_id = $1 order by id",
        str(lead),
    )
    return rows


async def test_changes_are_logged_with_who_and_only_what_changed(tx: asyncpg.Connection) -> None:
    lead = await new_lead(tx)  # the chatbot (no signed-in user)
    desk = await person(tx, "desk", "CL99", "front_desk")
    async with signed_in(tx, desk):
        await tx.execute("update app.leads set stage = 'follow_up' where id = $1", lead)
        await tx.execute("update app.leads set stage = 'follow_up' where id = $1", lead)  # no change
    rows = await log_for(tx, lead)
    assert [r["action"] for r in rows] == ["insert", "update"]
    assert rows[0]["actor"] is None
    assert rows[1]["actor"] == desk
    changed = rows[1]["changed"]
    assert json.loads(changed) == {"stage": ["new", "follow_up"]}


async def test_the_log_cannot_be_edited_or_deleted_even_by_the_backend(tx: asyncpg.Connection) -> None:
    lead = await new_lead(tx)
    async with rejected(tx):
        await tx.execute("update app.audit_log set actor = null where row_id = $1", str(lead))
    async with rejected(tx):
        await tx.execute("delete from app.audit_log where row_id = $1", str(lead))
    # Only a patient data deletion (switch on in its own transaction) may remove rows.
    await tx.execute("select set_config('app.privacy_delete', 'on', true)")
    await tx.execute("delete from app.audit_log where row_id = $1", str(lead))
    await tx.execute("select set_config('app.privacy_delete', '', true)")


async def test_who_may_read_the_log(tx: asyncpg.Connection) -> None:
    await tx.execute(
        "insert into app.clinics (id, name, bot_name, open_time, close_time, is_test) "
        "values ('CL98', 'Test Clinic 2', 'Test2 AI', '10:00', '19:00', true)"
    )
    mine, theirs = await new_lead(tx, "CL99"), await new_lead(tx, "CL98", "+919800000002")
    desk = await person(tx, "desk", "CL99", "front_desk")
    boss = await person(tx, "boss", "CL99", "clinic_manager")
    sql = "select row_id from app.audit_log where table_name = 'leads'"
    async with signed_in(tx, desk):
        assert await tx.fetch(sql) == []  # front desk: no audit access
        async with rejected(tx):  # and no way to write to it
            await tx.execute(
                "insert into app.audit_log (table_name, row_id, action) values ('leads', 'x', 'export')"
            )
    async with signed_in(tx, boss):
        seen = {r["row_id"] for r in await tx.fetch(sql)}
        assert str(mine) in seen and str(theirs) not in seen  # own clinic only
