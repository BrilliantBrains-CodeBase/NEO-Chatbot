"""Team & access: the team list, access requests and who may decide them."""

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture


@needs_db
async def test_requests_are_decided(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    try:
        req = await pool.fetchval(
            """insert into app.access_requests (clinic_id, role, full_name, email)
               values ('CL99', 'front_desk', 'Test Person', 'team-test@example.com') returning id"""
        )
        team = (await api.get("/v1/crm/team/CL99", headers=headers)).json()
        assert team["can_manage"] is True
        assert [r["email"] for r in team["requests"] if r["status"] == "pending"] == ["team-test@example.com"]
        r = await api.post(f"/v1/crm/team/CL99/requests/{req}", json={"status": "approved", "role": "doctor"},
                           headers=headers)  # fmt: skip
        assert r.status_code == 200
        sql = "select status, role, decided_by from app.access_requests where id = $1"
        done = await pool.fetchrow(sql, req)
        assert done["status"] == "approved" and done["role"] == "doctor"
        assert str(done["decided_by"]) == str(admin)
        url = f"/v1/crm/team/CL99/requests/{req}"
        again = await api.post(url, json={"status": "rejected"}, headers=headers)
        assert again.status_code == 404  # decided already
        bad = {"full_name": "X Y", "email": "x@example.com", "password": "longenough", "clinic": "CL00",
               "role": "front_desk"}  # fmt: skip
        assert (await api.post("/v1/auth/request-access", json=bad)).status_code == 404  # no such clinic
    finally:
        await pool.execute("delete from app.access_requests where email = 'team-test@example.com'")


@needs_db
async def test_request_access_makes_a_login_and_reject_removes_it(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real Supabase Auth (needs SUPABASE_SECRET_KEY): no email is sent for a created login."""
    import uuid

    from app.core.config import get_settings
    from app.crm import supabase_admin

    if not get_settings().supabase_secret_key:
        pytest.skip("SUPABASE_SECRET_KEY is not set")
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    email = f"neo-test-{uuid.uuid4().hex[:8]}@example.com"
    ask = {"full_name": "Test Person", "email": email, "password": "test-pass-123", "clinic": "CL99",
           "role": "front_desk"}  # fmt: skip
    uid = None
    try:
        r = await api.post("/v1/auth/request-access", json=ask)
        assert r.status_code == 201, r.text
        uid = await pool.fetchval("select id from app.profiles where email = $1", email)
        assert uid is not None
        assert (await api.post("/v1/auth/request-access", json=ask)).status_code == 409  # asked already
        headers = signed_in_as(monkeypatch, str(admin))
        req = await pool.fetchval("select id from app.access_requests where email = $1", email)
        url = f"/v1/crm/team/CL99/requests/{req}"
        assert (await api.post(url, json={"status": "rejected"}, headers=headers)).status_code == 200
        assert await pool.fetchval("select 1 from app.profiles where email = $1", email) is None  # login gone
        uid = None
    finally:
        if uid is not None:  # the test stopped half way: remove the login it made
            await supabase_admin.delete_user(str(uid))
        await pool.execute("delete from app.access_requests where email = $1", email)
