"""Outbox (migration 0008): no duplicates, valid states, same clinic, managers only.

Rolled back after each test; data in CL99. Skipped when DATABASE_URL is not set.
"""

from uuid import UUID

import asyncpg
import pytest

from app.core.config import get_settings
from tests.conftest import rejected
from tests.test_db_access import person, signed_in
from tests.test_db_audit import new_lead

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")

SQL = (
    "insert into app.outbox (clinic_id, channel, kind, lead_id, dedupe_key) "
    "values ($1, $2, $3, $4, $5) returning id"
)


async def queue(
    db: asyncpg.Connection, lead: UUID | None, key: str | None = None, clinic: str = "CL99"
) -> int:
    msg: int = await db.fetchval(SQL, clinic, "whatsapp", "booking_confirmed", lead, key)
    return msg


async def test_the_same_message_is_never_queued_twice(tx: asyncpg.Connection) -> None:
    lead = await new_lead(tx)
    await queue(tx, lead, f"booking_confirmed:{lead}")
    async with rejected(tx):
        await queue(tx, lead, f"booking_confirmed:{lead}")


@pytest.mark.parametrize(
    "change",
    [
        "status = 'sent'",  # sent needs its time
        "status = 'failed'",  # failed needs its error
        "attempts = 11",  # 10 tries at most
        "sent_at = now()",  # a sent time without the sent status
    ],
)
async def test_state_rules(tx: asyncpg.Connection, change: str) -> None:
    msg = await queue(tx, await new_lead(tx))
    async with rejected(tx):
        await tx.execute(f"update app.outbox set {change} where id = $1", msg)


async def test_valid_states(tx: asyncpg.Connection) -> None:
    msg = await queue(tx, await new_lead(tx))
    await tx.execute(
        "update app.outbox set status = 'failed', attempts = 10, last_error = 'timeout' where id = $1", msg
    )
    await tx.execute("update app.outbox set status = 'sent', sent_at = now() where id = $1", msg)


async def test_bad_channel_or_kind_is_rejected(tx: asyncpg.Connection) -> None:
    lead = await new_lead(tx)
    async with rejected(tx):
        await tx.fetchval(SQL, "CL99", "sms", "booking_confirmed", lead, None)
    async with rejected(tx):
        await tx.fetchval(SQL, "CL99", "email", "Booking Confirmed!", lead, None)


async def test_same_clinic_and_deleted_with_the_lead(tx: asyncpg.Connection) -> None:
    lead = await new_lead(tx)
    async with rejected(tx):
        await queue(tx, lead, clinic="NFHT")  # a CL99 lead under NFHT
    msg = await queue(tx, lead)
    await tx.execute("delete from app.leads where id = $1", lead)
    assert await tx.fetchval("select count(*) from app.outbox where id = $1", msg) == 0


async def test_only_managers_read_it(tx: asyncpg.Connection) -> None:
    await queue(tx, await new_lead(tx))
    desk = await person(tx, "desk", "CL99", "front_desk")
    boss = await person(tx, "boss", "CL99", "clinic_manager")
    async with signed_in(tx, desk):
        assert await tx.fetch("select id from app.outbox") == []
    async with signed_in(tx, boss):
        assert len(await tx.fetch("select id from app.outbox")) >= 1
        async with rejected(tx):  # read only, even for managers
            await tx.execute("update app.outbox set status = 'cancelled'")
