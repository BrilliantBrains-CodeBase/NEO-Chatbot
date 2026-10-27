"""Database checks for migration 0002 (staff, roles, doctors, availability, leave).

Each test runs in a transaction that is rolled back. Throwaway sign-in users are created inside it,
and writes go to the test clinic CL99 only. Skipped when DATABASE_URL is not set.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from uuid import UUID

import asyncpg
import pytest

from app.core.config import get_settings

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")

# A rejected row: a rule (constraint) error, or a data error raised while a generated column is
# computed (e.g. an inverted time range). Either way the row does not get in.
Rejected = (asyncpg.exceptions.IntegrityConstraintViolationError, asyncpg.exceptions.DataError)


@asynccontextmanager
async def rejected(db: asyncpg.Connection) -> AsyncIterator[None]:
    """Expect the block to be rejected. A savepoint keeps the test's transaction usable afterwards."""
    with pytest.raises(Rejected):
        async with db.transaction():
            yield


@pytest.fixture
async def db() -> AsyncIterator[asyncpg.Connection]:
    get_settings.cache_clear()
    conn = await asyncpg.connect(get_settings().database_url, statement_cache_size=0, timeout=15)
    tr = conn.transaction()
    await tr.start()
    try:
        yield conn
    finally:
        await tr.rollback()
        await conn.close()


async def person(db: asyncpg.Connection, email: str, clinic: str | None = None, role: str = "") -> UUID:
    """A throwaway sign-in user with a profile, and optionally a role in a clinic."""
    uid: UUID = await db.fetchval(
        "insert into auth.users (id, email) values (gen_random_uuid(), $1) returning id", email
    )
    await db.execute(
        "insert into app.profiles (id, full_name, email) values ($1, 'Test Person', $2)", uid, email
    )
    if clinic:
        await db.execute(
            "insert into app.user_clinics (user_id, clinic_id, role) values ($1, $2, $3)", uid, clinic, role
        )
    return uid


async def doctor(db: asyncpg.Connection, clinic: str = "CL99", user_id: UUID | None = None) -> UUID:
    doc: UUID = await db.fetchval(
        """insert into app.doctors (clinic_id, user_id, name, role_title)
           values ($1, $2, 'Dr. Test', 'Doctor') returning id""",
        clinic,
        user_id,
    )
    return doc


async def hours(
    db: asyncpg.Connection, doc: UUID, clinic: str, weekday: int, mode: str, start: str, end: str
) -> None:
    await db.execute(
        """insert into app.doctor_availability (doctor_id, clinic_id, weekday, mode, start_time, end_time)
           values ($1, $2, $3, $4, $5::text::time, $6::text::time)""",
        doc,
        clinic,
        weekday,
        mode,
        start,
        end,
    )


# ---------- seed


async def test_neo_follicle_doctor_and_hours_are_seeded(db: asyncpg.Connection) -> None:
    doc = await db.fetchrow("select * from app.doctors where clinic_id = 'CL01'")
    assert doc["name"] == "Dr. Sandeep Mahapatra"
    rows = await db.fetch(
        """select weekday, mode, start_time::text s, end_time::text e
           from app.doctor_availability where doctor_id = $1""",
        doc["id"],
    )
    # In-clinic and online (added 2026-10-24 for online consults), the same hours; Tuesday (2) closed.
    for mode in ("in_clinic", "online"):
        days = sorted(r["weekday"] for r in rows if r["mode"] == mode)
        assert days == [0, 1, 3, 4, 5, 6], mode
    assert {(r["s"], r["e"]) for r in rows} == {("10:00:00", "19:00:00")}


# ---------- availability and leave


async def test_overlapping_hours_are_rejected_but_other_mode_is_fine(db: asyncpg.Connection) -> None:
    doc = await doctor(db)
    await hours(db, doc, "CL99", 1, "in_clinic", "10:00", "13:00")
    await hours(db, doc, "CL99", 1, "in_clinic", "13:00", "17:00")  # touching is fine
    await hours(db, doc, "CL99", 1, "online", "11:00", "12:00")  # other mode is fine
    async with rejected(db):
        await hours(db, doc, "CL99", 1, "in_clinic", "12:30", "14:00")


@pytest.mark.parametrize(
    "weekday, mode, start, end",
    [(7, "in_clinic", "10:00", "11:00"), (1, "home", "10:00", "11:00"), (1, "online", "11:00", "10:00")],
)
async def test_bad_hours_are_rejected(
    db: asyncpg.Connection, weekday: int, mode: str, start: str, end: str
) -> None:
    doc = await doctor(db)
    async with rejected(db):
        await hours(db, doc, "CL99", weekday, mode, start, end)


async def test_hours_cannot_point_to_another_clinics_doctor(db: asyncpg.Connection) -> None:
    doc = await doctor(db, "CL99")
    async with rejected(db):
        await hours(db, doc, "CL01", 1, "in_clinic", "10:00", "11:00")


async def test_leave_must_not_end_before_it_starts(db: asyncpg.Connection) -> None:
    doc = await doctor(db)
    async with rejected(db):
        await db.execute(
            """insert into app.doctor_leave (doctor_id, clinic_id, from_date, to_date)
               values ($1, 'CL99', $2, $3)""",
            doc,
            date(2026, 11, 5),
            date(2026, 11, 4),
        )


# ---------- staff and roles


async def test_only_front_desk_can_be_in_the_round_robin(db: asyncpg.Connection) -> None:
    uid = await person(db, "rr@test.invalid", "CL99", "front_desk")
    await db.execute("update app.user_clinics set in_round_robin = true where user_id = $1", uid)
    async with rejected(db):
        await db.execute("update app.user_clinics set role = 'clinic_manager' where user_id = $1", uid)


async def test_unknown_role_and_uppercase_email_are_rejected(db: asyncpg.Connection) -> None:
    async with rejected(db):
        await person(db, "role@test.invalid", "CL99", "owner")
    async with rejected(db):
        await person(db, "Upper@Test.invalid")


async def test_doctor_login_must_be_a_doctor_of_the_same_clinic(db: asyncpg.Connection) -> None:
    desk = await person(db, "desk@test.invalid", "CL99", "front_desk")
    async with rejected(db):
        await doctor(db, "CL99", desk)  # not a doctor
    other = await person(db, "other@test.invalid", "CL01", "doctor")
    async with rejected(db):
        await doctor(db, "CL99", other)  # doctor of another clinic
    ok = await person(db, "doc@test.invalid", "CL99", "doctor")
    assert await doctor(db, "CL99", ok)


async def test_linked_doctor_keeps_the_doctor_role(db: asyncpg.Connection) -> None:
    uid = await person(db, "linked@test.invalid", "CL99", "doctor")
    await doctor(db, "CL99", uid)
    async with rejected(db):
        await db.execute("update app.user_clinics set role = 'front_desk' where user_id = $1", uid)


async def test_deleting_a_sign_in_keeps_the_doctor_and_clears_the_link(db: asyncpg.Connection) -> None:
    uid = await person(db, "gone@test.invalid", "CL99", "doctor")
    doc = await doctor(db, "CL99", uid)
    await db.execute("delete from auth.users where id = $1", uid)
    assert await db.fetchval("select count(*) from app.profiles where id = $1", uid) == 0
    assert await db.fetchval("select count(*) from app.user_clinics where user_id = $1", uid) == 0
    assert await db.fetchval("select user_id from app.doctors where id = $1", doc) is None
