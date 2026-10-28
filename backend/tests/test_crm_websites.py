"""Dashboard → Website install: only approved websites get the chatbot (app.clinics.allowed_origins)."""

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture


@needs_db
async def test_only_approved_sites_are_allowed(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    url = "/v1/crm/console/CL99/websites"
    allowed = "select allowed_origins from app.clinics where id = 'CL99'"
    try:
        r = await api.post(url, json={"address": "Test-Clinic.example.com/some/page"}, headers=headers)
        [site] = r.json()
        assert site["origin"] == "https://test-clinic.example.com" and site["status"] == "pending"
        assert await pool.fetchval(allowed) == []  # pending: not allowed yet
        assert (await api.post(url, json={"address": "http://x.com"}, headers=headers)).status_code == 422
        again = await api.post(url, json={"address": "https://test-clinic.example.com"}, headers=headers)
        assert again.status_code == 409
        r = await api.post(f"{url}/{site['id']}/decision", json={"status": "approved"}, headers=headers)
        assert r.json()[0]["decided_by"] is not None
        assert await pool.fetchval(allowed) == ["https://test-clinic.example.com"]
        r = await api.put(
            f"{url}/{site['id']}/pages", json={"pages_mode": "only", "pages": ["/hair/*"]}, headers=headers
        )
        assert r.json()[0]["pages"] == ["/hair/*"]
        bad = await api.put(f"{url}/{site['id']}/pages", json={"pages": ["hair"]}, headers=headers)
        assert bad.status_code == 422
        await api.post(f"{url}/{site['id']}/decision", json={"status": "rejected"}, headers=headers)
        assert await pool.fetchval(allowed) == []  # rejected: refused again
        assert (await api.delete(f"{url}/{site['id']}", headers=headers)).json() == []
    finally:
        await pool.execute("delete from app.clinic_websites where clinic_id = 'CL99'")
        await pool.execute("update app.clinics set allowed_origins = '{}' where id = 'CL99'")


@needs_db
async def test_embed_code(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    code = (await api.get("/v1/crm/console/CL01/websites/embed", headers=headers)).json()["code"]
    assert (
        code == '<script src="http://test/v1/widget/neo-follicle.js" defer></script>'
    )  # this backend's address
    js = await api.get("/v1/widget/neo-follicle.js")
    assert js.status_code == 200 and js.headers["content-type"].startswith("application/javascript")
    assert (await api.get("/v1/widget/..%2F.env")).status_code == 404  # only widget files, by name
    assert (await api.get("/v1/crm/console/CL99/websites/embed", headers=headers)).json()["code"] == ""
