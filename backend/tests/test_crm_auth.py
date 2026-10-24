"""CRM sign-in check (app.crm.auth) and GET /v1/crm/me. The token check against Supabase's signing keys is
replaced by a stub; the profile and roles come from the real database (skipped without one)."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.crm import initials
from app.core.config import get_settings
from app.core.db import close_pool, get_pool
from app.crm import auth
from app.main import create_app

needs_db = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        yield client
    await close_pool()


def signed_in_as(monkeypatch: pytest.MonkeyPatch, user_id: str) -> dict[str, str]:
    def verify(token: str) -> dict[str, Any]:
        if token != "good":
            raise jwt.InvalidTokenError("bad")
        return {"sub": user_id}

    monkeypatch.setattr(auth, "verify", verify)
    return {"Authorization": "Bearer good"}


async def test_no_or_bad_token_is_401(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert (await api.get("/v1/crm/me")).status_code == 401
    signed_in_as(monkeypatch, str(uuid.uuid4()))
    r = await api.get("/v1/crm/me", headers={"Authorization": "Bearer bad"})
    assert r.status_code == 401 and r.json()["detail"].startswith("Your sign-in has expired")


@needs_db
async def test_a_valid_login_without_an_approved_profile_has_no_access(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = await api.get("/v1/crm/me", headers=signed_in_as(monkeypatch, str(uuid.uuid4())))
    assert r.status_code == 403 and r.json()["detail"] == auth.NO_ACCESS


@needs_db
async def test_bb_admin_sees_every_active_clinic(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        """select p.id from app.profiles p join app.user_clinics u on u.user_id = p.id
           where u.role = 'bb_admin' and u.active and p.active limit 1"""
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    r = await api.get("/v1/crm/me", headers=signed_in_as(monkeypatch, str(admin)))
    assert r.status_code == 200
    me = r.json()
    assert me["bb_admin"] and me["role_label"] == "BB Admin"
    ids = [c["id"] for c in me["clinics"]]
    assert "CL01" in ids and "CL99" not in ids  # the test clinic is never listed
    assert all(c["role"] == "bb_admin" for c in me["clinics"])


@pytest.mark.parametrize(
    ("name", "want"), [("Mohammed Abdul Abid", "MA"), ("Priya", "P"), ("Dr Sandeep Mahapatra", "SM")]
)
def test_initials(name: str, want: str) -> None:
    assert initials(name) == want


@needs_db
async def test_dashboard_returns_the_numbers(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    admin = await (await get_pool()).fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    r = await api.get("/v1/crm/dashboard?clinic=CL01&days=7", headers=headers)
    assert r.status_code == 200
    d = r.json()
    assert [f["key"] for f in d["funnel"]] == ["new", "follow_up", "booked", "visited", "lost", "invalid"]
    assert d["new_leads"] >= 0 and isinstance(d["today"], list)
    assert (await api.get("/v1/crm/dashboard?clinic=bad", headers=headers)).status_code == 422


@needs_db
async def test_dashboard_needs_access_to_the_clinic(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = await get_pool()
    row = await pool.fetchrow(
        """select u.user_id, c.id from app.user_clinics u join app.profiles p on p.id = u.user_id
           cross join app.clinics c
           where u.active and p.active and u.role <> 'bb_admin' and c.id not in
             (select clinic_id from app.user_clinics where user_id = u.user_id) limit 1"""
    )
    if row is None:
        pytest.skip("no staff member without access to some clinic")
    r = await api.get(f"/v1/crm/dashboard?clinic={row[1]}", headers=signed_in_as(monkeypatch, str(row[0])))
    assert r.status_code == 403


@needs_db
async def test_leads_list_and_one_lead(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    r = await api.get("/v1/crm/leads?clinic=CL01&limit=5", headers=headers)
    assert r.status_code == 200
    d = r.json()
    assert [s["key"] for s in d["stages"]][0] == "new" and len(d["items"]) <= 5
    assert d["total"] == sum(s["count"] for s in d["stages"])
    assert (await api.get("/v1/crm/leads/NOPE-0", headers=headers)).status_code == 404
    none = (await api.get("/v1/crm/leads?clinic=CL01&from=2020-01-01&to=2020-01-02", headers=headers)).json()
    assert none["total"] == 0 and none["items"] == []
    if d["items"]:
        one = (await api.get(f"/v1/crm/leads/{d['items'][0]['code']}", headers=headers)).json()
        assert one["code"] == d["items"][0]["code"] and isinstance(one["events"], list)


@needs_db
async def test_lead_stage_owner_note_and_call(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    lead = await pool.fetchrow(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Test Lead', '+919000000001', 'manual') returning id, lead_code"""
    )
    code = lead["lead_code"]
    added = await pool.execute(  # the admin takes leads in the test clinic during this test only
        """insert into app.user_clinics (user_id, clinic_id, role) values ($1, 'CL99', 'front_desk')
           on conflict do nothing""",
        admin,
    )
    try:
        r = await api.patch(f"/v1/crm/leads/{code}", json={"stage": "lost"}, headers=headers)
        assert r.status_code == 422  # Lost needs a reason
        r = await api.patch(
            f"/v1/crm/leads/{code}", json={"stage": "lost", "stage_reason": "price"}, headers=headers
        )
        assert r.status_code == 200 and r.json()["stage"] == "lost" and r.json()["stage_reason"] == "price"
        r = await api.patch(f"/v1/crm/leads/{code}", json={"assigned_to": str(admin)}, headers=headers)
        assert r.json()["assigned"]
        await api.post(f"/v1/crm/leads/{code}/notes", json={"text": "Prefers evening"}, headers=headers)
        r = await api.post(f"/v1/crm/leads/{code}/calls", json={"outcome": "no_answer"}, headers=headers)
        kinds = [e["kind"] for e in r.json()["events"]]
        assert kinds[:4] == ["call", "note", "assigned", "stage_change"]
        assert r.json()["events"][3]["by"]  # who did it
    finally:
        await pool.execute("select app.delete_patient_data($1)", lead["id"])
        if added.endswith("1"):
            await pool.execute(
                "delete from app.user_clinics where user_id = $1 and clinic_id = 'CL99'", admin
            )


@needs_db
async def test_add_lead_and_duplicate_phone(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    body = {
        "clinic": "CL99",
        "name": "Walk  In",
        "phone": "9000000002",
        "source": "manual",
        "note": "Walk-in",
    }
    assert (
        await api.post("/v1/crm/leads", json=body | {"phone": "12345"}, headers=headers)
    ).status_code == 422
    r = await api.post("/v1/crm/leads", json=body, headers=headers)
    assert r.status_code == 201
    lead = r.json()
    try:
        assert lead["name"] == "Walk In" and lead["phone"] == "+919000000002" and lead["notes"] == "Walk-in"
        assert lead["events"][0]["kind"] == "contact"
        dup = await api.post("/v1/crm/leads", json=body, headers=headers)
        assert dup.status_code == 409 and lead["code"] in dup.json()["detail"]
        opts = await api.get("/v1/crm/lead-options?clinic=CL01", headers=headers)
        assert "Hair Transplant for Men" in opts.json()["treatments"]
    finally:
        lead_id = await pool.fetchval("select id from app.leads where lead_code = $1", lead["code"])
        await pool.execute("select app.delete_patient_data($1)", lead_id)
