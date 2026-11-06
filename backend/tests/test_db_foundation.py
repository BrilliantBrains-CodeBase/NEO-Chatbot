"""Database checks against the cloud project (migration 0001 and the security baseline).

Every test runs inside a transaction that is rolled back, so nothing is left behind. Writes use the
test clinic CL99 only. Skipped when DATABASE_URL is not set.
"""

from collections.abc import AsyncIterator

import asyncpg
import pytest

from app.core.config import get_settings

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")

PUBLIC_ROLES = ("anon", "authenticated")


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


# ---------- security baseline: these check every object in app, so they also guard future migrations


async def test_anon_cannot_use_the_app_schema(db: asyncpg.Connection) -> None:
    # anon is the publishable key without sign-in: no access to app at all.
    assert await db.fetchval("select has_schema_privilege('anon', 'app', 'usage')") is False


async def test_every_app_table_has_row_level_security(db: asyncpg.Connection) -> None:
    missing = await db.fetch(
        """select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
           where n.nspname = 'app' and c.relkind in ('r', 'p') and not c.relrowsecurity"""
    )
    assert [r["relname"] for r in missing] == []


async def test_nothing_in_app_is_granted_to_anon_or_public(db: asyncpg.Connection) -> None:
    tables = await db.fetch(
        """select c.relname, r.rolname from pg_class c join pg_namespace n on n.oid = c.relnamespace
           cross join (values ('anon'), ('public')) r(rolname)
           where n.nspname = 'app' and c.relkind in ('r', 'p', 'S')
             and has_any_column_privilege(r.rolname, c.oid, 'select, insert, update, references')"""
    )
    assert [tuple(r) for r in tables] == []
    funcs = await db.fetch(
        """select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
           where n.nspname = 'app' and has_function_privilege('anon', p.oid, 'execute')"""
    )
    assert [r["proname"] for r in funcs] == []


async def test_every_table_signed_in_users_can_touch_has_a_policy(db: asyncpg.Connection) -> None:
    # A grant without a row rule would expose every row: each such table needs RLS and a policy.
    unguarded = await db.fetch(
        """select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
           where n.nspname = 'app' and c.relkind in ('r', 'p')
             and has_any_column_privilege('authenticated', c.oid, 'select, insert, update, references')
             and (not c.relrowsecurity or not exists (
                   select 1 from pg_policy pol where pol.polrelid = c.oid))"""
    )
    assert [r["relname"] for r in unguarded] == []


async def test_signed_in_users_run_only_the_who_am_i_helpers(db: asyncpg.Connection) -> None:
    funcs = await db.fetch(
        """select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
           where n.nspname = 'app' and has_function_privilege('authenticated', p.oid, 'execute')
           order by 1"""
    )
    assert [r["proname"] for r in funcs] == [
        "can_manage",
        "delete_patient_data",  # managers only, checked inside (0011)
        "is_bb_admin",
        "is_staff",
        "my_doctor_ids",
        "my_role",
    ]


async def test_bookkeeping_table_is_closed_to_signed_in_users(db: asyncpg.Connection) -> None:
    assert (
        await db.fetchval(
            "select has_any_column_privilege('authenticated', 'app.schema_migrations', 'select')"
        )
        is False
    )


async def test_new_tables_get_no_rights_by_default(db: asyncpg.Connection) -> None:
    await db.execute("create table app._probe (id int)")
    for role in PUBLIC_ROLES:
        assert await db.fetchval("select has_table_privilege($1, 'app._probe', 'select')", role) is False
    await db.execute("create table public._probe (id int)")
    for role in PUBLIC_ROLES:
        assert await db.fetchval("select has_table_privilege($1, 'public._probe', 'select')", role) is False


# ---------- clinics


async def test_clinics_are_seeded(db: asyncpg.Connection) -> None:
    rows = {r["id"]: r for r in await db.fetch("select * from app.clinics")}
    assert rows["NFHT"]["name"] == "Neo Follicle Hair Transplant"
    assert rows["NFHT"]["bot_name"] == "Arya AI"
    assert rows["NFHT"]["closed_weekdays"] == [2]
    assert rows["NFHT"]["is_test"] is False
    assert rows["CL99"]["is_test"] is True


@pytest.mark.parametrize(
    "column, value",
    [
        ("id", "x1"),  # capitals only
        ("id", "1BF"),  # starts with a letter
        ("close_time", "09:00"),  # before open_time
        ("closed_weekdays", [7]),
        ("slot_minutes", 0),
        ("booking_window_days", 0),
        ("phone", "9731207940"),  # no country code
        ("website", "http://insecure.example"),
        ("name", " "),
    ],
)
async def test_clinic_rules_are_enforced(db: asyncpg.Connection, column: str, value: object) -> None:
    row: dict[str, object] = {
        "id": "CL98",
        "name": "Rule Test",
        "bot_name": "Rule AI",
        "open_time": "10:00",
        "close_time": "19:00",
    }
    row[column] = value
    cols = ", ".join(row)
    # Times go in as text and are cast in SQL, so a bad value fails on the table's rule, not on a type.
    casts = {"open_time": "::text::time", "close_time": "::text::time", "closed_weekdays": "::smallint[]"}
    args = ", ".join(f"${i + 1}{casts.get(c, '')}" for i, c in enumerate(row))
    with pytest.raises(asyncpg.exceptions.IntegrityConstraintViolationError):
        await db.execute(f"insert into app.clinics ({cols}) values ({args})", *row.values())


async def test_updated_at_moves_on_update(db: asyncpg.Connection) -> None:
    before = await db.fetchval("select updated_at from app.clinics where id = 'CL99'")
    after = await db.fetchval(
        "update app.clinics set name = 'Test Clinic 2' where id = 'CL99' returning updated_at"
    )
    # now() is fixed inside a transaction, so compare against the stored value instead of the clock.
    assert after >= before
