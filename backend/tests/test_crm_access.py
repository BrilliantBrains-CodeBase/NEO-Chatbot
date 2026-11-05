"""Who reaches what, through the API: one clinic's staff never reach another clinic; Front Desk works in one
clinic; invites never lower anyone; limits on Admins hold; Doctors see only their own patients; only the
main Super Admin changes Super Admins. Uses the test clinics CL99 and CL98; removes what it makes."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.api.v1 import crm_team
from app.core.db import close_pool, get_pool
from app.crm import permissions as perm
from app.crm import supabase_admin
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture

TEAM = "/v1/crm/team/CL99"
TODAY = date.today().isoformat()
# Everything a clinic's screens read, for CL98. Each must refuse someone who only works in CL99.
OTHER_CLINIC = [
    "/v1/crm/dashboard?clinic=CL98",
    "/v1/crm/leads?clinic=CL98",
    "/v1/crm/leads/export?clinic=CL98",
    "/v1/crm/staff?clinic=CL98",
    "/v1/crm/lead-options?clinic=CL98",
    "/v1/crm/inbox?clinic=CL98",
    "/v1/crm/inbox/export?clinic=CL98",
    "/v1/crm/slots?clinic=CL98&mode=in_clinic",
    f"/v1/crm/appointments?clinic=CL98&from={TODAY}",
    "/v1/crm/patients?clinic=CL98",
    "/v1/crm/availability/doctors?clinic=CL98",
    "/v1/crm/availability?clinic=CL98",
    "/v1/crm/team/CL98",
    "/v1/crm/permissions/CL98",
    "/v1/crm/console/CL98/settings",
    "/v1/crm/console/CL98/kb",
    "/v1/crm/console/CL98/doctors",
    "/v1/crm/clinic-settings/CL98",
    "/v1/crm/clinic-settings/CL98/branding",
]


async def _person(pool: Any, made: list[Any], name: str, *roles: tuple[str, str]) -> dict[str, str]:
    """A login with roles (clinic, role)."""
    email = f"access-{name}-{uuid.uuid4().hex[:8]}@example.com"
    uid = await pool.fetchval(
        "insert into auth.users (id, email) values (gen_random_uuid(), $1) returning id", email
    )
    made.append(uid)
    sql = "insert into app.profiles (id, full_name, email) values ($1, $2, $3)"
    await pool.execute(sql, uid, f"Test {name}", email)
    for clinic, role in roles:
        await pool.execute(
            "insert into app.user_clinics (user_id, clinic_id, role) values ($1, $2, $3)", uid, clinic, role
        )
    return {"id": str(uid), "email": email}


@pytest.fixture
async def world() -> AsyncIterator[dict[str, Any]]:
    """Both test clinics, a person in each role, a lead in each clinic, and two doctors' appointments."""
    pool = await get_pool()
    await pool.execute(
        """insert into app.clinics (id, name, bot_name, open_time, close_time, is_test)
           values ('CL98', 'Test Clinic 2', 'Test2 AI', '10:00', '19:00', true) on conflict do nothing"""
    )
    made: list[Any] = []
    w: dict[str, Any] = {
        "bb": await _person(pool, made, "bb", ("CL99", "bb_admin")),
        "manager": await _person(pool, made, "manager", ("CL99", "clinic_manager")),
        "both": await _person(pool, made, "both", ("CL99", "clinic_manager"), ("CL98", "clinic_manager")),
        "desk": await _person(pool, made, "desk", ("CL99", "front_desk")),
        "doctor": await _person(pool, made, "doctor", ("CL99", "doctor")),
    }
    phone = f"+9198{uuid.uuid4().int % 10**8:08d}"
    other = f"+9197{uuid.uuid4().int % 10**8:08d}"
    lead = "insert into app.leads (clinic_id, full_name, phone_e164, source) values ($1, $2, $3, 'chatbot') "
    w["lead"] = await pool.fetchrow(lead + "returning id, lead_code", "CL99", "Our Patient", phone)
    w["other_lead"] = await pool.fetchrow(lead + "returning id, lead_code", "CL98", "Their Patient", other)
    new_doctor = """insert into app.doctors (clinic_id, name, role_title) values ('CL99', $1, 'Doctor')
                    returning id"""
    w["my_record"] = str(await pool.fetchval(new_doctor, "Dr Mine"))
    w["other_record"] = str(await pool.fetchval(new_doctor, "Dr Other"))
    start = datetime.now(UTC) + timedelta(minutes=5)
    for offset, record in enumerate((w["my_record"], w["other_record"])):
        at = start + timedelta(minutes=30 * offset)
        await pool.execute(
            """insert into app.appointments (clinic_id, lead_id, doctor_id, type, slot)
               values ('CL99', $1, $2::uuid, 'in_clinic', tstzrange($3, $4, '[)'))""",
            w["lead"]["id"], record, at, at + timedelta(minutes=15),
        )  # fmt: skip
    rules = await pool.fetchval("select permissions from app.platform where id = 1")
    try:
        yield w
    finally:
        await pool.execute("update app.platform set permissions = $1 where id = 1", rules or "{}")
        await pool.execute("delete from app.clinic_permissions where clinic_id in ('CL98', 'CL99')")
        await pool.execute("delete from app.appointments where lead_id = $1", w["lead"]["id"])
        await pool.execute(
            "delete from app.doctors where id = any($1::uuid[])", [w["my_record"], w["other_record"]]
        )
        await pool.execute(
            "delete from app.leads where id = any($1::uuid[])", [w["lead"]["id"], w["other_lead"]["id"]]
        )
        await pool.execute("delete from auth.users where id = any($1::uuid[])", made)
        await pool.execute("delete from app.clinics where id = 'CL98'")
        await close_pool()


def _no_emails(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Nothing reaches Supabase Auth; new logins get an id, and each call is noted."""
    calls: list[str] = []

    async def invite(email: str, name: str) -> str:
        calls.append(email)
        pool = await get_pool()
        return str(
            await pool.fetchval(
                "insert into auth.users (id, email) values (gen_random_uuid(), $1) returning id", email
            )
        )

    async def reset(email: str) -> None:
        calls.append(email)

    monkeypatch.setattr(supabase_admin, "invite", invite)
    monkeypatch.setattr(supabase_admin, "reset_password", reset)
    return calls


@needs_db
async def test_front_desk_reaches_nothing_of_another_clinic(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    headers = signed_in_as(monkeypatch, world["desk"]["id"])
    me = (await api.get("/v1/crm/me", headers=headers)).json()
    assert "CL98" not in [c["id"] for c in me["clinics"]]
    assert (await api.get("/v1/crm/leads?clinic=CL99", headers=headers)).status_code == 200
    for url in OTHER_CLINIC:
        assert (await api.get(url, headers=headers)).status_code == 403, url


@needs_db
async def test_another_clinics_lead_answers_not_found(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    """Exactly as a code that does not exist: nothing shows that the lead is there."""
    headers = signed_in_as(monkeypatch, world["desk"]["id"])
    url = f"/v1/crm/leads/{world['other_lead']['lead_code']}"
    assert (await api.get(url, headers=headers)).status_code == 404
    assert (await api.patch(url, json={"stage": "lost"}, headers=headers)).status_code == 404
    assert (await api.post(f"{url}/notes", json={"text": "x"}, headers=headers)).status_code == 404
    mine = f"/v1/crm/leads/{world['lead']['lead_code']}"
    assert (await api.get(mine, headers=headers)).status_code == 200


@needs_db
async def test_a_clinic_manager_reaches_nothing_of_another_clinic(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    headers = signed_in_as(monkeypatch, world["manager"]["id"])
    for url in OTHER_CLINIC:
        assert (await api.get(url, headers=headers)).status_code == 403, url
    new = {
        "full_name": "Some One",
        "email": "some-one@example.com",
        "role": "front_desk",
        "clinics": ["CL98"],
    }
    assert (await api.post(f"{TEAM}/invite", json=new, headers=headers)).status_code == 403


@needs_db
async def test_front_desk_works_in_exactly_one_clinic(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    calls = _no_emails(monkeypatch)
    headers = signed_in_as(monkeypatch, world["bb"]["id"])
    desk = world["desk"]
    two = {"full_name": "New Desk", "email": "new-desk@example.com", "role": "front_desk",
           "clinics": ["CL99", "CL98"]}  # fmt: skip
    assert (await api.post(f"{TEAM}/invite", json=two, headers=headers)).status_code == 422
    assert calls == []  # refused before any login is made
    other = {"full_name": "Desk", "email": desk["email"], "role": "doctor", "clinics": ["CL98"]}
    assert (await api.post(f"{TEAM}/invite", json=other, headers=headers)).status_code == 422
    url = f"{TEAM}/members/{desk['id']}/clinics"
    assert (await api.put(url, json={"clinics": ["CL99", "CL98"]}, headers=headers)).status_code == 422
    # Moving to the other clinic is one clinic still.
    assert (await api.put(url, json={"clinics": ["CL98"]}, headers=headers)).status_code == 200
    pool = await get_pool()
    rows = await pool.fetch("select clinic_id from app.user_clinics where user_id = $1::uuid", desk["id"])
    assert [r["clinic_id"] for r in rows] == ["CL98"]
    # Someone with two clinics cannot become Front Desk in one of them.
    both = f"{TEAM}/members/{world['both']['id']}"
    assert (await api.put(both, json={"role": "front_desk"}, headers=headers)).status_code == 422


@needs_db
async def test_an_invite_never_lowers_anyone(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    _no_emails(monkeypatch)
    headers = signed_in_as(monkeypatch, world["both"]["id"])
    pool = await get_pool()
    role = "select role from app.user_clinics where user_id = $1::uuid and clinic_id = $2"
    manager = {"full_name": "Manager", "email": world["manager"]["email"], "role": "doctor",
               "clinics": ["CL99", "CL98"]}  # fmt: skip
    assert (await api.post(f"{TEAM}/invite", json=manager, headers=headers)).status_code == 200
    assert await pool.fetchval(role, world["manager"]["id"], "CL99") == "clinic_manager"  # kept
    assert await pool.fetchval(role, world["manager"]["id"], "CL98") == "doctor"  # the new clinic
    # A Super Admin's row is out of reach, and so is a disabled Admin's.
    bb = {"full_name": "BB", "email": world["bb"]["email"], "role": "doctor", "clinics": ["CL99", "CL98"]}
    assert (await api.post(f"{TEAM}/invite", json=bb, headers=headers)).status_code == 409
    assert await pool.fetchval(role, world["bb"]["id"], "CL99") == "bb_admin"
    await pool.execute(
        "update app.user_clinics set active = false where user_id = $1::uuid and clinic_id = 'CL99'",
        world["manager"]["id"],
    )
    again = {
        "full_name": "Manager",
        "email": world["manager"]["email"],
        "role": "doctor",
        "clinics": ["CL99"],
    }
    assert (await api.post(f"{TEAM}/invite", json=again, headers=headers)).status_code == 403
    assert await pool.fetchval(role, world["manager"]["id"], "CL99") == "clinic_manager"


@needs_db
async def test_limits_on_clinic_managers_hold_on_the_server(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    bb = signed_in_as(monkeypatch, world["bb"]["id"])
    url = "/v1/crm/permissions/CL99"
    table = (await api.get(url, headers=bb)).json()["effective"]
    table["clinic_manager"]["dash_ai"] = "hidden"
    table["clinic_manager"]["dash_appearance"] = "view"
    assert (await api.put(url, json={"rules": table}, headers=bb)).status_code == 200

    manager = signed_in_as(monkeypatch, world["manager"]["id"])
    assert (await api.get("/v1/crm/console/CL99/kb", headers=manager)).status_code == 403  # hidden
    assert (await api.get("/v1/crm/console/CL99/settings", headers=manager)).status_code == 200
    saved = await api.put("/v1/crm/console/CL99/settings/appearance", json={}, headers=manager)
    assert saved.status_code == 403  # view only
    # "Use the defaults" clears the clinic's rules for Front Desk and Doctors, not Super Admin's limits.
    table["front_desk"]["patients"] = "view"
    assert (await api.put(url, json={"rules": table}, headers=manager)).status_code == 200
    kept = (await api.put(url, json={"rules": {}}, headers=manager)).json()["own"]
    assert kept == {"clinic_manager": {"dash_ai": "hidden", "dash_appearance": "view"}}
    assert (await api.get("/v1/crm/console/CL99/kb", headers=manager)).status_code == 403
    # Super Admin lifts them.
    signed_in_as(monkeypatch, world["bb"]["id"])
    assert (await api.put(url, json={"rules": {}}, headers=bb)).json()["own"] == {}
    signed_in_as(monkeypatch, world["manager"]["id"])
    assert (await api.get("/v1/crm/console/CL99/kb", headers=manager)).status_code == 200


@needs_db
async def test_who_sees_what_lists_only_screens_it_decides(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    headers = signed_in_as(monkeypatch, world["bb"]["id"])
    rules = (await api.get("/v1/crm/permissions/CL99", headers=headers)).json()
    keys = {s["key"] for s in rules["screens"]}
    assert not keys & perm.FIXED and "leads" in keys and "dash_ai" in keys
    assert "dash_team" not in perm.SCREENS


@needs_db
async def test_team_is_for_managers_and_password_resets_respect_rank(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    calls = _no_emails(monkeypatch)
    desk = signed_in_as(monkeypatch, world["desk"]["id"])
    pool = await get_pool()
    assert (await perm.for_person(pool, "CL99", world["desk"]["id"], "front_desk"))["team"] == "hidden"
    own = (await api.get(TEAM, headers=desk)).json()
    assert [m["id"] for m in own["members"]] == [world["desk"]["id"]] and not own["can_manage"]

    manager = signed_in_as(monkeypatch, world["manager"]["id"])
    listed = {m["id"] for m in (await api.get(TEAM, headers=manager)).json()["members"]}
    assert world["desk"]["id"] in listed and world["bb"]["id"] not in listed  # Super Admins are not listed
    for person in ("bb", "both"):
        url = f"{TEAM}/members/{world[person]['id']}/reset"
        assert (await api.post(url, headers=manager)).status_code == 403
    assert calls == []
    url = f"{TEAM}/members/{world['desk']['id']}/reset"
    assert (await api.post(url, headers=manager)).status_code == 200
    assert calls == [world["desk"]["email"]]


@needs_db
async def test_only_the_main_bb_admin_changes_bb_admins(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    calls = _no_emails(monkeypatch)
    new = {
        "full_name": "New Admin",
        "email": "new-admin@example.com",
        "role": "bb_admin",
        "clinics": ["CL99"],
    }
    manager = signed_in_as(monkeypatch, world["manager"]["id"])
    assert (await api.post(f"{TEAM}/invite", json=new, headers=manager)).status_code == 403

    async def someone_else() -> str:
        return "someone-else@example.com"

    monkeypatch.setattr(crm_team, "main_email", someone_else)
    bb = signed_in_as(monkeypatch, world["bb"]["id"])
    team = (await api.get(TEAM, headers=bb)).json()
    assert team["can_add_admins"] is False
    assert (await api.post(f"{TEAM}/invite", json=new, headers=bb)).status_code == 403
    assert calls == []

    async def me() -> str:
        return str(world["bb"]["email"])

    monkeypatch.setattr(crm_team, "main_email", me)
    done = await api.post(f"{TEAM}/invite", json=new, headers=bb)
    assert done.status_code == 200 and calls == [new["email"]]
    pool = await get_pool()
    added = await pool.fetchval("select id from app.profiles where email = $1", new["email"])
    try:
        assert await pool.fetchval(
            "select role from app.user_clinics where user_id = $1 and clinic_id = 'CL99'", added
        ) == "bb_admin"  # fmt: skip
        # The public form never offers it.
        ask = {"full_name": "Sneaky", "email": "sneaky@example.com", "password": "test-pass-123",
               "clinic": "CL99", "role": "bb_admin"}  # fmt: skip
        assert (await api.post("/v1/auth/request-access", json=ask)).status_code == 422
    finally:
        await pool.execute("delete from auth.users where id = $1", added)


@needs_db
async def test_a_doctor_sees_only_their_own_patients(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    doctor = world["doctor"]
    bb = signed_in_as(monkeypatch, world["bb"]["id"])
    link = f"{TEAM}/members/{doctor['id']}/doctor"
    missing = {"doctor_id": str(uuid.uuid4())}
    assert (await api.put(link, json=missing, headers=bb)).status_code == 404
    done = await api.put(link, json={"doctor_id": world["my_record"]}, headers=bb)
    assert done.status_code == 200
    linked = next(m for m in done.json()["members"] if m["id"] == doctor["id"])
    assert linked["doctor_id"] == world["my_record"]
    desk = f"{TEAM}/members/{world['desk']['id']}/doctor"
    assert (await api.put(desk, json={"doctor_id": world["other_record"]}, headers=bb)).status_code == 422

    me = signed_in_as(monkeypatch, doctor["id"])
    for url in ("/v1/crm/leads?clinic=CL99", "/v1/crm/inbox?clinic=CL99", "/v1/crm/dashboard?clinic=CL99",
                f"/v1/crm/leads/{world['lead']['lead_code']}"):  # fmt: skip
        assert (await api.get(url, headers=me)).status_code == 403, url
    today = datetime.now(UTC).date()
    seen = await api.get(
        f"/v1/crm/appointments?clinic=CL99&from={today}&to={today + timedelta(days=1)}", headers=me
    )
    assert {a["doctor_id"] for a in seen.json()["items"]} == {world["my_record"]}
    board = (await api.get("/v1/crm/availability?clinic=CL99", headers=me)).json()["doctors"]
    bookings = {c["doctor"]["id"]: [b["patient"] for b in c["today"]["bookings"]] for c in board}
    assert not bookings[world["other_record"]]  # the other doctor's hours show; their patients do not
    other = await api.get(f"/v1/crm/availability/{world['other_record']}?clinic=CL99", headers=me)
    assert not any(d["bookings"] for d in other.json()["days"])
    mine = await api.get(f"/v1/crm/availability/{world['my_record']}?clinic=CL99", headers=me)
    assert any(d["bookings"] for d in mine.json()["days"])
    hours: dict[str, list[str]] = {"in_clinic": [], "online": [], "leave": []}
    url = f"/v1/crm/availability/{world['other_record']}/schedule?clinic=CL99"
    assert (await api.put(url, json=hours, headers=me)).status_code == 403

    # Front Desk still sees every doctor's bookings.
    desk_headers = signed_in_as(monkeypatch, world["desk"]["id"])
    other = await api.get(f"/v1/crm/availability/{world['other_record']}?clinic=CL99", headers=desk_headers)
    assert any(d["bookings"] for d in other.json()["days"])
    # Changing the role clears the link instead of failing on the database's rule.
    signed_in_as(monkeypatch, world["bb"]["id"])
    change = f"{TEAM}/members/{doctor['id']}"
    assert (await api.put(change, json={"role": "clinic_manager"}, headers=bb)).status_code == 200
    pool = await get_pool()
    sql = "select user_id from app.doctors where id = $1::uuid"
    assert await pool.fetchval(sql, world["my_record"]) is None
