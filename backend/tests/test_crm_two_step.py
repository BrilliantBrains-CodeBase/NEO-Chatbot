"""2-step login: a role that needs a code is refused until this sign-in's emailed code is verified; wrong
codes count down. Gmail is replaced, so no email is sent. Leaves the setting as it found it."""

import uuid
from typing import Any

import jwt
import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from app.crm import auth, email
from tests.test_crm_auth import api, needs_db

__all__ = ["api"]  # the client fixture
H = {"Authorization": "Bearer good"}


@needs_db
async def test_code_needed_then_verified(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    session = str(uuid.uuid4())

    def verify(token: str) -> dict[str, Any]:
        if token != "good":
            raise jwt.InvalidTokenError("bad")
        return {"sub": str(admin), "session_id": session}

    monkeypatch.setattr(auth, "verify", verify)
    codes: list[str] = []

    async def fake_send(clinic: str | None, to: str, subject: str, text: str, kind: str) -> None:
        codes.append(subject.rsplit(" ", 1)[-1])

    monkeypatch.setattr(email, "send", fake_send)
    before = await pool.fetchval("select two_step_roles from app.platform where id = 1")
    had_gmail = await pool.fetchval("select 1 from app.email_senders where clinic_id is null")
    try:
        if not had_gmail:  # switching on needs the BB Gmail
            bb = {"address": "bb@example.com", "app_password": "abcdefghijklmnop"}
            await api.put("/v1/crm/security/email", json=bb, headers=H)
        r = await api.put("/v1/crm/security/two-step", json={"roles": ["bb_admin"]}, headers=H)
        assert r.json()["roles"] == ["bb_admin"]
        assert (await api.get("/v1/crm/me", headers=H)).status_code == 200  # who switched it on stays in
        session = str(uuid.uuid4())  # a new sign-in
        r = await api.get("/v1/crm/me", headers=H)
        assert r.status_code == 403 and r.json()["detail"] == auth.CODE_NEEDED
        assert (await api.post("/v1/auth/code/send", headers=H)).status_code == 200
        assert (await api.post("/v1/auth/code/send", headers=H)).status_code == 429  # one a minute
        wrong = "000000" if codes[-1] != "000000" else "111111"
        r = await api.post("/v1/auth/code/verify", json={"code": wrong}, headers=H)
        assert r.status_code == 422 and "4 tries left" in r.json()["detail"]
        r = await api.post("/v1/auth/code/verify", json={"code": codes[-1]}, headers=H)
        assert r.status_code == 200
        assert (await api.get("/v1/crm/me", headers=H)).status_code == 200  # in
    finally:
        await pool.execute("update app.platform set two_step_roles = $1 where id = 1", before or [])
        await pool.execute("delete from app.login_codes where user_id = $1", admin)
        await pool.execute(
            "delete from app.login_sessions where user_id = $1 and verified_at > now() - interval '1 hour'",
            admin,
        )
        if not had_gmail:
            await api.delete("/v1/crm/security/email", headers=H)
