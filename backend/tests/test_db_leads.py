"""Database checks for migration 0003 (leads, patients, requests, appointments, tasks, timeline).

Each test runs in a transaction that is rolled back, including the lead counters. Writes go to the
test clinic CL99, plus a second throwaway clinic CL98 created inside the transaction.
Skipped when DATABASE_URL is not set.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import pytest

from app.core.config import get_settings
from tests.conftest import rejected

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")

AT = datetime(2026, 11, 2, 4, 30, tzinfo=UTC)  # 10:00 India time


async def lead(
    db: asyncpg.Connection, clinic: str = "CL99", phone: str | None = "+919800000001", **cols: object
) -> asyncpg.Record:
    row = {"clinic_id": clinic, "full_name": "Test Lead", "phone_e164": phone, "source": "chatbot", **cols}
    names = ", ".join(row)
    args = ", ".join(f"${i + 1}" for i in range(len(row)))
    rec: asyncpg.Record = await db.fetchrow(
        f"insert into app.leads ({names}) values ({args}) returning id, lead_code", *row.values()
    )
    return rec


async def second_clinic(db: asyncpg.Connection) -> None:
    await db.execute(
        "insert into app.clinics (id, name, bot_name, open_time, close_time, is_test) "
        "values ('CL98', 'Test Clinic 2', 'Test2 AI', '10:00', '19:00', true)"
    )


async def doctor(db: asyncpg.Connection, clinic: str = "CL99") -> UUID:
    doc: UUID = await db.fetchval(
        "insert into app.doctors (clinic_id, name, role_title) "
        "values ($1, 'Dr. Test', 'Doctor') returning id",
        clinic,
    )
    return doc


async def booking(
    db: asyncpg.Connection,
    lead_id: UUID,
    doc: UUID | None,
    start_min: int,
    length_min: int = 15,
    status: str = "pending",
) -> UUID:
    start = AT + timedelta(minutes=start_min)
    confirmed = AT if status in ("confirmed", "visited", "no_show") else None
    appt: UUID = await db.fetchval(
        """insert into app.appointments (clinic_id, lead_id, doctor_id, type, slot, status, confirmed_at)
           values ('CL99', $1, $2, 'in_clinic', tstzrange($3, $4, '[)'), $5, $6) returning id""",
        lead_id,
        doc,
        start,
        start + timedelta(minutes=length_min),
        status,
        confirmed,
    )
    return appt


# ---------- lead codes


async def test_codes_follow_each_clinics_own_counter(tx: asyncpg.Connection) -> None:
    n = await tx.fetchval("select next_lead_no from app.clinics where id = 'CL99'")
    codes = [(await lead(tx, phone=f"+91980000000{i}"))["lead_code"] for i in range(3)]
    assert codes == [f"CL99-{n:05d}", f"CL99-{n + 1:05d}", f"CL99-{n + 2:05d}"]
    await second_clinic(tx)
    assert (await lead(tx, "CL98"))["lead_code"] == "CL98-00001"


async def test_a_code_cannot_be_chosen_or_changed(tx: asyncpg.Connection) -> None:
    row = await lead(tx, lead_code="HACKED")
    assert row["lead_code"].startswith("CL99-")
    async with rejected(tx):
        await tx.execute("update app.leads set lead_code = 'CL99-99999' where id = $1", row["id"])
    async with rejected(tx):
        await tx.execute("update app.leads set clinic_id = 'CL01' where id = $1", row["id"])


# ---------- one lead per person per clinic


async def test_one_lead_per_phone_per_clinic(tx: asyncpg.Connection) -> None:
    first = await lead(tx)
    async with rejected(tx):
        await lead(tx)  # same phone, same clinic
    await second_clinic(tx)
    await lead(tx, "CL98")  # same phone, another clinic: fine
    await tx.execute("update app.leads set deleted_at = now() where id = $1", first["id"])
    await lead(tx)  # the old one was deleted: fine


async def test_email_only_leads_and_contact_details(tx: asyncpg.Connection) -> None:
    await lead(tx, phone=None, email="priya@example.com")
    async with rejected(tx):
        await lead(tx, phone=None, email="priya@example.com")
    async with rejected(tx):
        await lead(tx, phone=None)  # neither phone nor email
    async with rejected(tx):
        await lead(tx, phone="9876543210")  # no country code
    async with rejected(tx):
        await lead(tx, phone="+919811111111", email="Priya@Example.com")  # not lower case


# ---------- stages


@pytest.mark.parametrize(
    "stage, reason, ok",
    [
        ("lost", None, False),
        ("lost", "price", True),
        ("lost", "spam", False),  # an invalid-reason on a lost lead
        ("invalid", "spam", True),
        ("invalid", "price", False),
        ("new", "price", False),  # only lost and invalid carry a reason
        ("archived", None, False),
    ],
)
async def test_stage_rules(tx: asyncpg.Connection, stage: str, reason: str | None, ok: bool) -> None:
    row = await lead(tx)
    sql = "update app.leads set stage = $2, stage_reason = $3 where id = $1"
    if ok:
        await tx.execute(sql, row["id"], stage, reason)
    else:
        async with rejected(tx):
            await tx.execute(sql, row["id"], stage, reason)


# ---------- nothing points across clinics


async def test_links_must_stay_in_the_same_clinic(tx: asyncpg.Connection) -> None:
    row = await lead(tx)
    async with rejected(tx):  # a CL01 request for a CL99 lead
        await tx.execute(
            "insert into app.requests (clinic_id, lead_id, type) values ('CL01', $1, 'callback')", row["id"]
        )
    cl01_doctor = await tx.fetchval("select id from app.doctors where clinic_id = 'CL01' limit 1")
    async with rejected(tx):  # a CL01 doctor on a CL99 lead
        await tx.execute("update app.leads set doctor_id = $2 where id = $1", row["id"], cl01_doctor)
    uid = await tx.fetchval(
        "insert into auth.users (id, email) values (gen_random_uuid(), 'x@test.invalid') returning id"
    )
    await tx.execute(
        "insert into app.profiles (id, full_name, email) values ($1, 'Staff', 'x@test.invalid')", uid
    )
    await tx.execute(
        "insert into app.user_clinics (user_id, clinic_id, role) values ($1, 'CL01', 'front_desk')", uid
    )
    async with rejected(tx):  # CL01 staff assigned to a CL99 lead
        await tx.execute("update app.leads set assigned_to = $2 where id = $1", row["id"], uid)


async def test_only_cancel_and_reschedule_are_matched(tx: asyncpg.Connection) -> None:
    row = await lead(tx)
    await tx.execute(
        "insert into app.requests (clinic_id, lead_id, type, match_status) "
        "values ('CL99', $1, 'cancel', 'no_match')",
        row["id"],
    )
    async with rejected(tx):
        await tx.execute(
            "insert into app.requests (clinic_id, lead_id, type, match_status) "
            "values ('CL99', $1, 'book', 'matched')",
            row["id"],
        )


async def test_a_linked_booking_needs_the_matched_status(tx: asyncpg.Connection) -> None:
    # Guards the NULL loophole fixed in 0004: a link with no match status must not get through.
    row = await lead(tx)
    appt = await booking(tx, row["id"], await doctor(tx), 0)
    sql = """insert into app.requests (clinic_id, lead_id, type, match_status, matched_appointment_id)
             values ('CL99', $1, 'cancel', $2, $3)"""
    await tx.execute(sql, row["id"], "matched", appt)
    async with rejected(tx):
        await tx.execute(sql, row["id"], None, appt)
    async with rejected(tx):
        await tx.execute(sql, row["id"], "no_match", appt)


# ---------- appointments


async def test_no_double_booking_of_a_doctor(tx: asyncpg.Connection) -> None:
    row = await lead(tx)
    doc = await doctor(tx)
    await booking(tx, row["id"], doc, 0)  # 10:00 to 10:15 pending
    async with rejected(tx):
        await booking(tx, row["id"], doc, 10, status="confirmed")  # 10:10 overlaps
    await booking(tx, row["id"], doc, 15)  # 10:15 touches: fine
    cancelled = await booking(tx, row["id"], doc, 5, status="cancelled")  # cancelled never blocks
    await booking(tx, row["id"], await doctor(tx), 0)  # another doctor: fine
    async with rejected(tx):  # a cancelled one cannot come back over a taken slot
        await tx.execute("update app.appointments set status = 'pending' where id = $1", cancelled)


async def test_appointment_rules(tx: asyncpg.Connection) -> None:
    row = await lead(tx)
    async with rejected(tx):  # neither a slot nor a preferred day
        await tx.execute(
            "insert into app.appointments (clinic_id, lead_id, type) values ('CL99', $1, 'in_clinic')",
            row["id"],
        )
    async with rejected(tx):  # confirmed without a confirmation time
        await tx.execute(
            """insert into app.appointments (clinic_id, lead_id, type, preferred_date, status)
               values ('CL99', $1, 'in_clinic', current_date, 'confirmed')""",
            row["id"],
        )
    async with rejected(tx):  # a Meet link on an in-clinic visit
        await tx.execute(
            """insert into app.appointments (clinic_id, lead_id, type, preferred_date, meet_link)
               values ('CL99', $1, 'in_clinic', current_date, 'https://meet.google.com/abc-defg-hij')""",
            row["id"],
        )
    async with rejected(tx):  # a link that is not Google Meet
        await tx.execute(
            """insert into app.appointments (clinic_id, lead_id, type, preferred_date, meet_link)
               values ('CL99', $1, 'online', current_date, 'https://evil.example/meet')""",
            row["id"],
        )


# ---------- tasks and timeline


async def test_task_rules(tx: asyncpg.Connection) -> None:
    row = await lead(tx)
    sql = """insert into app.tasks (clinic_id, lead_id, type, due_at, attempt, status, outcome, completed_at)
             values ('CL99', $1, $2, now(), $3, $4, $5, $6)"""
    await tx.execute(sql, row["id"], "retry_call", 3, "open", None, None)
    async with rejected(tx):
        await tx.execute(sql, row["id"], "retry_call", 4, "open", None, None)  # max 3 tries
    async with rejected(tx):
        await tx.execute(sql, row["id"], "call_new_lead", 2, "open", None, None)  # only retries count up
    async with rejected(tx):
        await tx.execute(
            sql, row["id"], "call_new_lead", 1, "done", None, AT
        )  # a done call needs its outcome
    async with rejected(tx):
        await tx.execute(sql, row["id"], "call_new_lead", 1, "done", "answered", None)  # done needs a time
    await tx.execute(sql, row["id"], "call_new_lead", 1, "done", "no_answer", AT)


async def test_timeline_is_add_only_and_goes_with_the_lead(tx: asyncpg.Connection) -> None:
    row = await lead(tx)
    event = await tx.fetchval(
        "insert into app.lead_events (clinic_id, lead_id, kind) values ('CL99', $1, 'contact') returning id",
        row["id"],
    )
    async with rejected(tx):
        await tx.execute("update app.lead_events set kind = 'note' where id = $1", event)
    await tx.execute("delete from app.leads where id = $1", row["id"])  # a patient deletion request
    assert await tx.fetchval("select count(*) from app.lead_events where lead_id = $1", row["id"]) == 0
