"""Free slots from the database (B5a). Rolled back after each test; data in the test clinic CL99
(open 10:00 to 19:00, last slot 30 minutes before closing, 15-minute slots, Tuesday closed)."""

from datetime import date, datetime
from uuid import UUID

import asyncpg
import pytest

from app.chat.slots import free_slots
from app.core.config import get_settings

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")

MON = date(2026, 10, 26)  # a Monday
TUE = date(2026, 10, 27)
FAR = date(2026, 1, 1)  # "today" far away, so no time is in the past


async def doctor(
    db: asyncpg.Connection, start: str, end: str, mode: str = "in_clinic", weekday: int = 1
) -> UUID:
    doc: UUID = await db.fetchval(
        "insert into app.doctors (clinic_id, name, role_title) "
        "values ('CL99', 'Dr. Test', 'Doctor') returning id"
    )
    await db.execute(
        """insert into app.doctor_availability (doctor_id, clinic_id, weekday, mode, start_time, end_time)
           values ($1, 'CL99', $2, $3, $4::text::time, $5::text::time)""",
        doc,
        weekday,
        mode,
        start,
        end,
    )
    return doc


async def booked(db: asyncpg.Connection, doc: UUID, hm: str, status: str = "pending") -> None:
    lead = await db.fetchval(
        "select id from app.leads where clinic_id = 'CL99' and phone_e164 = '+919800000001'"
    )
    if lead is None:
        lead = await db.fetchval(
            "insert into app.leads (clinic_id, full_name, phone_e164, source) "
            "values ('CL99', 'Lead', '+919800000001', 'chatbot') returning id"
        )
    start = datetime.fromisoformat(f"{MON.isoformat()}T{hm}:00+05:30")
    await db.execute(
        """insert into app.appointments (clinic_id, lead_id, doctor_id, type, slot, status, confirmed_at)
           values ('CL99', $1, $2, 'in_clinic',
                   tstzrange($3::timestamptz, $3::timestamptz + interval '15 minutes', '[)'), $4, $5)""",
        lead,
        doc,
        start,
        status,
        start if status == "confirmed" else None,
    )


async def slots(
    db: asyncpg.Connection, day: date = MON, mode: str = "in_clinic", today: date = FAR, now: int = 0
) -> list[str]:
    return await free_slots(db, "CL99", day, mode, today, now)  # type: ignore[arg-type]


async def test_slots_follow_the_doctors_hours(tx: asyncpg.Connection) -> None:
    await doctor(tx, "10:00", "12:00")
    got = await slots(tx)
    assert got[0] == "10:00" and got[-1] == "11:45" and len(got) == 8  # last start leaves a full slot


async def test_clinic_closing_limits_the_last_slot(tx: asyncpg.Connection) -> None:
    await doctor(tx, "17:00", "21:00")  # works past closing
    assert (await slots(tx))[-1] == "18:30"  # 19:00 closing minus 30 minutes


async def test_taken_slots_are_hidden_cancelled_ones_are_not(tx: asyncpg.Connection) -> None:
    doc = await doctor(tx, "10:00", "11:00")
    await booked(tx, doc, "10:15", "pending")
    await booked(tx, doc, "10:30", "confirmed")
    await booked(tx, doc, "10:45", "cancelled")
    assert await slots(tx) == ["10:00", "10:45"]


async def test_a_time_is_free_if_any_doctor_is_free(tx: asyncpg.Connection) -> None:
    first = await doctor(tx, "10:00", "10:30")
    await booked(tx, first, "10:15")
    await doctor(tx, "10:00", "10:30")  # a second doctor is free at 10:15
    assert await slots(tx) == ["10:00", "10:15"]


async def test_leave_mode_and_closed_days(tx: asyncpg.Connection) -> None:
    doc = await doctor(tx, "10:00", "11:00")
    assert await slots(tx, mode="online") == []  # only in-clinic hours set
    assert await slots(tx, day=TUE) == []  # Tuesday closed
    await tx.execute(
        "insert into app.doctor_leave (doctor_id, clinic_id, from_date, to_date) values ($1, 'CL99', $2, $2)",
        doc,
        MON,
    )
    assert await slots(tx) == []  # on leave


async def test_today_hides_past_times(tx: asyncpg.Connection) -> None:
    await doctor(tx, "10:00", "11:00")
    assert await slots(tx, today=MON, now=10 * 60 + 20) == ["10:30", "10:45"]


async def test_holidays_have_no_slots(tx: asyncpg.Connection) -> None:
    await doctor(tx, "10:00", "11:00")
    await tx.execute(
        "insert into app.clinic_holidays (clinic_id, day, reason) values ('CL99', $1, 'Diwali')", MON
    )
    assert await slots(tx) == []


async def test_new_sources_lost_wording_and_settings(tx: asyncpg.Connection) -> None:
    lead = await tx.fetchval(
        "insert into app.leads (clinic_id, full_name, phone_e164, source) "
        "values ('CL99', 'Walk In', '+919800000005', 'walk_in') returning id"
    )
    await tx.execute("update app.leads set stage = 'lost', stage_reason = 'no_response' where id = $1", lead)
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await tx.execute("update app.leads set stage_reason = 'not_reachable' where id = $1", lead)


async def test_audit_is_trimmed_after_one_year(tx: asyncpg.Connection) -> None:
    await tx.execute(
        "insert into app.audit_log (table_name, row_id, action, at) "
        "values ('leads', 'old', 'update', now() - interval '13 months')"
    )
    await tx.fetchval("select app.job_trim_audit_log()")
    assert await tx.fetchval("select count(*) from app.audit_log where row_id = 'old'") == 0
