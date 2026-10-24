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
