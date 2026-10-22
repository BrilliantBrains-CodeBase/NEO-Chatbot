"""Access rules (migration 0006), checked by signing in as each role.

Each test signs in the way the backend will: Postgres role "authenticated" plus the user's id in the
request claims. Everything runs in a transaction that is rolled back; data goes to CL99 and to a second
test clinic CL98 created inside it. Skipped when DATABASE_URL is not set.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import pytest

from app.core.config import get_settings
from tests.conftest import rejected

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")

AT = datetime(2026, 11, 2, 4, 30, tzinfo=UTC)


async def person(db: asyncpg.Connection, name: str, clinic: str, role: str, active: bool = True) -> UUID:
    email = f"{name}@test.invalid"
    uid: UUID = await db.fetchval(
        "insert into auth.users (id, email) values (gen_random_uuid(), $1) returning id", email
    )
    await db.execute(
        "insert into app.profiles (id, full_name, email) values ($1, $2, $3)", uid, name.title(), email
    )
    await db.execute(
        "insert into app.user_clinics (user_id, clinic_id, role, active) values ($1, $2, $3, $4)",
        uid,
        clinic,
        role,
        active,
    )
    return uid


@asynccontextmanager
async def signed_in(db: asyncpg.Connection, uid: UUID | None) -> AsyncIterator[None]:
    """Act as a signed-in CRM user (uid) or, with None, as anon (the publishable key, not signed in)."""
    await db.execute("set local role " + ("authenticated" if uid else "anon"))
    claims = json.dumps({"sub": str(uid), "role": "authenticated"}) if uid else ""
    await db.execute("select set_config('request.jwt.claims', $1, true)", claims)
    try:
        yield
    finally:
        await db.execute("reset role")
        await db.execute("select set_config('request.jwt.claims', '', true)")


@pytest.fixture
async def world(tx: asyncpg.Connection) -> dict[str, UUID]:
    """Two clinics with one lead each, a doctor with a login and one without, and their appointments."""
    await tx.execute(
        "insert into app.clinics (id, name, bot_name, open_time, close_time, is_test) "
        "values ('CL98', 'Test Clinic 2', 'Test2 AI', '10:00', '19:00', true)"
    )
    w: dict[str, UUID] = {}
    for key, clinic, phone in (("lead99", "CL99", "+919800000001"), ("lead98", "CL98", "+919800000002")):
        w[key] = await tx.fetchval(
            "insert into app.leads (clinic_id, full_name, phone_e164, source) "
            "values ($1, 'Lead', $2, 'chatbot') returning id",
            clinic,
            phone,
        )
    w["doc_user"] = await person(tx, "doctor", "CL99", "doctor")
    for key, user in (("my_doc", w["doc_user"]), ("other_doc", None)):
        w[key] = await tx.fetchval(
            "insert into app.doctors (clinic_id, user_id, name, role_title) "
            "values ('CL99', $1, 'Dr. X', 'Doctor') returning id",
            user,
        )
    for key, doc in (("my_appt", w["my_doc"]), ("other_appt", w["other_doc"])):
        w[key] = await tx.fetchval(
            """insert into app.appointments (clinic_id, lead_id, doctor_id, type, slot)
               values ('CL99', $1, $2, 'in_clinic', tstzrange($3, $4, '[)')) returning id""",
            w["lead99"],
            doc,
            AT,
            AT + timedelta(minutes=15),
        )
    return w


async def visible_leads(db: asyncpg.Connection) -> set[UUID]:
    return {r["id"] for r in await db.fetch("select id from app.leads")}


# ---------- anon


async def test_anon_reaches_nothing(tx: asyncpg.Connection, world: dict[str, UUID]) -> None:
    async with signed_in(tx, None):
        async with rejected(tx):
            await tx.fetch("select * from app.leads")


# ---------- front desk


async def test_front_desk_works_only_in_their_clinic(tx: asyncpg.Connection, world: dict[str, UUID]) -> None:
    desk = await person(tx, "desk", "CL99", "front_desk")
    async with signed_in(tx, desk):
        assert await visible_leads(tx) == {world["lead99"]}
        # Another clinic's lead: invisible, so an update changes nothing.
        assert (
            await tx.execute("update app.leads set notes = 'x' where id = $1", world["lead98"]) == "UPDATE 0"
        )
        async with rejected(tx):  # cannot add a lead to another clinic
            await tx.execute(
                "insert into app.leads (clinic_id, full_name, phone_e164, source) "
                "values ('CL98', 'X', '+919811111111', 'manual')"
            )
        # A manual lead in their own clinic gets its code (the counter trigger runs with owner rights).
        code = await tx.fetchval(
            "insert into app.leads (clinic_id, full_name, phone_e164, source) "
            "values ('CL99', 'Walk In', '+919822222222', 'manual') returning lead_code"
        )
        assert code.startswith("CL99-")


async def test_front_desk_cannot_delete_or_rewrite_identity(
    tx: asyncpg.Connection, world: dict[str, UUID]
) -> None:
    desk = await person(tx, "desk", "CL99", "front_desk")
    async with signed_in(tx, desk):
        async with rejected(tx):  # only managers delete
            await tx.execute("update app.leads set deleted_at = now() where id = $1", world["lead99"])
        async with rejected(tx):  # the code is not an editable column
            await tx.execute("update app.leads set lead_code = 'CL99-99999' where id = $1", world["lead99"])
        async with rejected(tx):  # neither is the contact count
            await tx.execute("update app.leads set contact_count = 99 where id = $1", world["lead99"])
        async with rejected(tx):  # nor the clinic's lead counter
            await tx.execute("update app.clinics set next_lead_no = 1 where id = 'CL99'")


async def test_timeline_entries_carry_the_writers_own_id(
    tx: asyncpg.Connection, world: dict[str, UUID]
) -> None:
    desk = await person(tx, "desk", "CL99", "front_desk")
    sql = "insert into app.lead_events (clinic_id, lead_id, kind, actor) values ('CL99', $1, 'note', $2)"
    async with signed_in(tx, desk):
        await tx.execute(sql, world["lead99"], desk)
        async with rejected(tx):  # writing under someone else's name
            await tx.execute(sql, world["lead99"], world["doc_user"])


async def test_inactive_staff_see_nothing(tx: asyncpg.Connection, world: dict[str, UUID]) -> None:
    gone = await person(tx, "gone", "CL99", "front_desk", active=False)
    async with signed_in(tx, gone):
        assert await visible_leads(tx) == set()
        assert await tx.fetch("select id from app.clinics") == []


# ---------- clinic manager


async def test_manager_deletes_leads_and_manages_the_team_but_not_bb_admins(
    tx: asyncpg.Connection, world: dict[str, UUID]
) -> None:
    boss = await person(tx, "boss", "CL99", "clinic_manager")
    newbie = await tx.fetchval(
        "insert into auth.users (id, email) values (gen_random_uuid(), 'new@test.invalid') returning id"
    )
    await tx.execute(
        "insert into app.profiles (id, full_name, email) values ($1, 'New', 'new@test.invalid')", newbie
    )
    sql = "insert into app.user_clinics (user_id, clinic_id, role) values ($1, $2, $3)"
    async with signed_in(tx, boss):
        await tx.execute("update app.leads set deleted_at = now() where id = $1", world["lead99"])
        await tx.execute(sql, newbie, "CL99", "front_desk")
        async with rejected(tx):  # only BB Admin creates BB Admins
            await tx.execute("update app.user_clinics set role = 'bb_admin' where user_id = $1", newbie)
        async with rejected(tx):  # not their clinic
            await tx.execute(sql, newbie, "CL98", "front_desk")


# ---------- doctor


async def test_doctor_sees_only_own_appointments_and_no_leads(
    tx: asyncpg.Connection, world: dict[str, UUID]
) -> None:
    async with signed_in(tx, world["doc_user"]):
        assert await visible_leads(tx) == set()
        appts = {r["id"] for r in await tx.fetch("select id from app.appointments")}
        assert appts == {world["my_appt"]}
        assert await tx.fetch("select id from app.chat_messages") == []


async def test_doctor_edits_only_own_hours(tx: asyncpg.Connection, world: dict[str, UUID]) -> None:
    sql = """insert into app.doctor_availability (doctor_id, clinic_id, weekday, mode, start_time, end_time)
             values ($1, 'CL99', 1, 'online', '10:00', '12:00')"""
    async with signed_in(tx, world["doc_user"]):
        await tx.execute(sql, world["my_doc"])
        async with rejected(tx):
            await tx.execute(sql, world["other_doc"])


# ---------- BB Admin


async def test_bb_admin_sees_every_clinic(tx: asyncpg.Connection, world: dict[str, UUID]) -> None:
    admin = await person(tx, "admin", "CL99", "bb_admin")
    async with signed_in(tx, admin):
        assert {world["lead99"], world["lead98"]} <= await visible_leads(tx)


# ---------- profiles


async def test_own_profile_name_yes_email_no_others_no(
    tx: asyncpg.Connection, world: dict[str, UUID]
) -> None:
    desk = await person(tx, "desk", "CL99", "front_desk")
    async with signed_in(tx, desk):
        await tx.execute("update app.profiles set full_name = 'Desk Two' where id = $1", desk)
        async with rejected(tx):  # email is not editable
            await tx.execute("update app.profiles set email = 'x@test.invalid' where id = $1", desk)
        assert (
            await tx.execute("update app.profiles set full_name = 'Hacked' where id = $1", world["doc_user"])
            == "UPDATE 0"
        )
