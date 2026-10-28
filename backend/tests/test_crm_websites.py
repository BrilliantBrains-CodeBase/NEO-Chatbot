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


def test_pages_rule() -> None:
    from app.api.v1.widget import page_shown

    assert page_shown("all", [], "/careers")
    assert page_shown("only", ["/hair-transplant/*"], "/hair-transplant/fue")
    assert not page_shown("only", ["/hair-transplant/*"], "/careers")
    assert not page_shown("except", ["/careers", "/blog/*"], "/careers/")
    assert page_shown("except", ["/careers"], "/contact")


@needs_db
async def test_widget_shows_only_on_approved_sites_and_pages(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.chat import guard

    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    url = "/v1/crm/console/CL99/websites"
    site = "https://www.clinic-test.example.com"

    async def shown(origin: str, path: str) -> bool:
        guard._clinics.clear()
        r = await api.get(f"/v1/widget/show?clinic=CL99&path={path}", headers={"Origin": origin})
        return bool(r.json()["show"])

    try:
        [s] = (await api.post(url, json={"address": site}, headers=headers)).json()
        assert not await shown(site, "/")  # pending: not shown
        await api.post(f"{url}/{s['id']}/decision", json={"status": "approved"}, headers=headers)
        assert await shown(site, "/")
        assert await shown("https://clinic-test.example.com", "/")  # with or without www
        assert not await shown("https://other-site.example.com", "/")  # not approved: refused
        rule = {"pages_mode": "except", "pages": ["/careers"]}
        await api.put(f"{url}/{s['id']}/pages", json=rule, headers=headers)
        assert not await shown(site, "/careers") and await shown(site, "/contact")
        check = (await api.post(f"{url}/{s['id']}/check", headers=headers)).json()
        assert check["found"] is False  # the example site does not exist
    finally:
        await pool.execute("delete from app.clinic_websites where clinic_id = 'CL99'")
        await pool.execute("update app.clinics set allowed_origins = '{}' where id = 'CL99'")


@needs_db
async def test_integrations_status_never_shows_keys(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    r = await api.get("/v1/crm/console/CL01/integrations", headers=headers)
    assert r.status_code == 200
    assert [i["id"] for i in r.json()] == ["calcom", "sheet", "whatsapp", "email"]
    s = get_settings()
    for key in (s.calcom_api_key, s.sheet_webhook_secret, s.interakt_api_key):
        assert not key or key not in r.text  # keys are never sent


@needs_db
async def test_connect_calcom_keeps_the_key_in_vault(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings
    from app.crm import vault

    key = get_settings().calcom_api_key
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None or not key:
        pytest.skip("no BB Admin or no Cal.com key in this setup")
    headers = signed_in_as(monkeypatch, str(admin))
    url = "/v1/crm/console/CL99/integrations/calcom"
    try:
        bad = await api.post(url, json={"api_key": "cal_live_wrong_key"}, headers=headers)
        assert bad.status_code == 422 and "API key" in bad.json()["detail"]
        r = await api.post(url, json={"api_key": key}, headers=headers)
        assert r.status_code == 200 and key not in r.text  # the key is never sent back
        [cal] = [i for i in r.json() if i["id"] == "calcom"]
        assert cal["state"] == "connected" and cal["detail"][0].startswith("Account: ")
        row = await pool.fetchrow(
            "select key_secret, webhook_id from app.calcom_accounts where clinic_id = 'CL99'"
        )
        async with pool.acquire() as conn:
            assert await vault.read(conn, row["key_secret"]) == key  # in Vault, readable by the backend only
        assert row["webhook_id"] is None  # the test backend is not online over https
        await api.delete(url, headers=headers)
        async with pool.acquire() as conn:
            assert await vault.read(conn, row["key_secret"]) is None  # deleted from Vault
    finally:
        old = await pool.fetchval(
            "delete from app.calcom_accounts where clinic_id = 'CL99' returning key_secret"
        )
        if old:
            async with pool.acquire() as conn:
                await vault.delete(conn, old)


@needs_db
async def test_online_consult_setup_goes_to_calcom(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from app.core.config import get_settings
    from app.crm import calcom, vault

    key = get_settings().calcom_api_key
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None or not key:
        pytest.skip("no BB Admin or no Cal.com key in this setup")
    headers = signed_in_as(monkeypatch, str(admin))
    base = "/v1/crm/console/CL99/integrations/calcom"
    try:
        await api.post(base, json={"api_key": key}, headers=headers)
        setup = (await api.post(f"{base}/doctors", json={"name": "Dr Test Online"}, headers=headers)).json()
        [doc] = [d for d in setup["doctors"] if d["name"] == "Dr Test Online"]
        doc |= {
            "online": True,
            "consult_minutes": 15,
            "hours": [{"weekday": 1, "start": "10:00", "end": "13:00"}],
            "leave": [{"from_date": "2030-01-01", "to_date": "2030-01-02", "reason": "Test"}],
        }
        body = {"doctors": [doc], "holidays": [{"day": "2030-01-26", "reason": "Republic Day"}]}
        r = (await api.put(f"{base}/setup", json=body, headers=headers)).json()
        assert r["problems"] == []
        [saved] = [d for d in r["doctors"] if d["name"] == "Dr Test Online"]
        assert saved["online"] and saved["consult_minutes"] == 15 and saved["hours"][0]["start"] == "10:00"
        row = await pool.fetchrow(
            "select event_type_id, schedule_id from app.calcom_doctors where clinic_id = 'CL99'"
        )
        h = {"Authorization": f"Bearer {key}", "cal-api-version": calcom.EVENTS}
        async with httpx.AsyncClient() as c:
            event = (await c.get(f"{calcom.API}/event-types/{row['event_type_id']}", headers=h)).json()[
                "data"
            ]
        assert event["lengthInMinutes"] == 15 and event["title"] == "Online consult with Dr Test Online"
        body["doctors"][0]["online"] = False  # off: removed from Cal.com
        await api.put(f"{base}/setup", json=body, headers=headers)
        async with httpx.AsyncClient() as c:
            gone = await c.get(f"{calcom.API}/event-types/{row['event_type_id']}", headers=h)
        assert gone.status_code == 404
    finally:
        await pool.execute("delete from app.calcom_doctors where clinic_id = 'CL99'")
        await pool.execute("delete from app.doctors where clinic_id = 'CL99' and name = 'Dr Test Online'")
        await pool.execute("delete from app.clinic_holidays where clinic_id = 'CL99' and day = '2030-01-26'")
        old = await pool.fetchval(
            "delete from app.calcom_accounts where clinic_id = 'CL99' returning key_secret"
        )
        if old:
            async with pool.acquire() as conn:
                await vault.delete(conn, old)


@needs_db
async def test_sheet_link_reports_tabs(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from urllib.parse import parse_qs, urlsplit

    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    url = "/v1/crm/console/CL99/integrations/sheets"
    try:
        [sheet] = (await api.post(url, json={"name": "Meta leads test"}, headers=headers)).json()
        got = (await api.get(f"{url}/{sheet['id']}/script", headers=headers)).json()
        assert got["link"] in got["script"] and "crmSetup" in got["script"]
        parts = urlsplit(got["link"])
        key = parse_qs(parts.query)["key"][0]
        tabs = {"tabs": [{"tab": "Form A", "headers": ["Full Name", "Phone", " ", "Created Time"]}]}
        r = await api.post(f"{parts.path}?key={key}", json=tabs)
        assert r.status_code == 200 and r.json()["active_tabs"] == []
        [listed] = (await api.get(url, headers=headers)).json()
        assert (
            listed["tabs"][0]["headers"] == ["Full Name", "Phone", "Created Time"] and listed["last_seen_at"]
        )
        assert (await api.post(f"{parts.path}?key=wrong", json=tabs)).status_code == 403
        await api.delete(f"{url}/{sheet['id']}", headers=headers)
        assert (await api.post(f"{parts.path}?key={key}", json=tabs)).status_code == 403  # deleted: link dead
    finally:
        await pool.execute("delete from app.lead_sheets where clinic_id = 'CL99'")
