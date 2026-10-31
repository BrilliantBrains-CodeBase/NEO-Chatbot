"""Dashboard → Website install: only approved websites get the chatbot (app.clinics.allowed_origins)."""

from typing import Any

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
    # every other clinic: the one shared script
    code = (await api.get("/v1/crm/console/CL99/websites/embed", headers=headers)).json()["code"]
    assert code == '<script src="http://test/v1/widget/clinic.js" data-clinic="CL99" defer></script>'


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
    assert [i["id"] for i in r.json()] == ["calcom", "sheet", "forms", "webhooks", "whatsapp", "email"]
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
        # The doctor, their online hours, leave and length are set in Dashboard → Doctors.
        doctor = {
            "name": "Dr Test Online",
            "online_minutes": 10,
            "online": [{"weekday": 1, "start": "10:00", "end": "13:00"}],
            "leave": [{"from_date": "2030-01-01", "to_date": "2030-01-02", "reason": "Test"}],
        }
        docs = (await api.post("/v1/crm/console/CL99/doctors", json=doctor, headers=headers)).json()
        [made] = [d for d in docs["doctors"] if d["name"] == "Dr Test Online"]
        setup = (await api.get(f"{base}/setup", headers=headers)).json()
        [doc] = [d for d in setup["doctors"] if d["name"] == "Dr Test Online"]
        doc["online"] = True  # this screen only ticks the doctor
        body = {"doctors": [doc], "holidays": [{"day": "2030-01-26", "reason": "Republic Day"}]}
        r = (await api.put(f"{base}/setup", json=body, headers=headers)).json()
        assert r["problems"] == []
        [saved] = [d for d in r["doctors"] if d["name"] == "Dr Test Online"]
        assert saved["online"] and saved["consult_minutes"] == 10 and saved["hours"][0]["start"] == "10:00"
        row = await pool.fetchrow(
            "select event_type_id, schedule_id from app.calcom_doctors where clinic_id = 'CL99'"
        )
        h = {"Authorization": f"Bearer {key}", "cal-api-version": calcom.EVENTS}

        async def length() -> Any:
            async with httpx.AsyncClient() as c:
                got = await c.get(f"{calcom.API}/event-types/{row['event_type_id']}", headers=h)
            return got.json()["data"]

        event = await length()
        assert event["lengthInMinutes"] == 10 and event["title"] == "Online consult with Dr Test Online"
        # Saving the doctor in Dashboard → Doctors sends the new length to Cal.com.
        r = await api.put(
            f"/v1/crm/console/CL99/doctors/{made['id']}",
            json=doctor | {"online_minutes": 20},
            headers=headers,
        )
        assert r.status_code == 200 and r.json()["problems"] == [], r.text
        assert (await length())["lengthInMinutes"] == 20
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


@needs_db
async def test_sheet_tab_mapping(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from urllib.parse import urlsplit

    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    url = "/v1/crm/console/CL99/integrations/sheets"
    try:
        [sheet] = (await api.post(url, json={"name": "Mapping test"}, headers=headers)).json()
        link = (await api.get(f"{url}/{sheet['id']}/script", headers=headers)).json()["link"]
        parts = urlsplit(link)
        cols = ["Name", "Contact Number", "Email Address", "Date", "Remark"]
        await api.post(f"{parts.path}?{parts.query}", json={"tabs": [{"tab": "Lead", "headers": cols}]})
        tab = (await api.get(url, headers=headers)).json()[0]["tabs"][0]
        put = f"{url}/{sheet['id']}/tabs/{tab['id']}"
        good = {"Name": "name", "Contact Number": "phone", "Date": "date", "Remark": "skip"}
        r = await api.put(put, json={"active": True, "mapping": good}, headers=headers)
        saved = r.json()[0]["tabs"][0]
        assert saved["active"] and saved["mapping"] == {
            "Name": "name",
            "Contact Number": "phone",
            "Date": "date",
        }
        no_phone = await api.put(put, json={"active": True, "mapping": {"Name": "name"}}, headers=headers)
        assert no_phone.status_code == 422 and "Phone" in no_phone.json()["detail"]
        twice = {"Name": "name", "Remark": "name"}
        assert (await api.put(put, json={"mapping": twice}, headers=headers)).status_code == 422
        assert (await api.put(put, json={"mapping": {"Nope": "name"}}, headers=headers)).status_code == 422
        r = await api.post(f"{parts.path}?{parts.query}", json={"tabs": []})
        assert r.json()["active_tabs"] == ["Lead"]  # the script now knows which tabs to send
    finally:
        await pool.execute("delete from app.lead_sheets where clinic_id = 'CL99'")


@needs_db
async def test_sheet_rows_become_leads(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from urllib.parse import urlsplit

    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    url = "/v1/crm/console/CL99/integrations/sheets"
    cols = ["id", "created_time", "platform", "question", "full_name", "phone_number", "email", "notes"]
    raw = ["l:1016149801463045", "2026-08-26T01:26:17-05:00", "fb", "yes,_i_have", "himavanth",
           "p:+919000000094", "himavanthkb@example.com", "Visit in september"]  # fmt: skip
    try:
        [sheet] = (await api.post(url, json={"name": "Rows test"}, headers=headers)).json()
        parts = urlsplit((await api.get(f"{url}/{sheet['id']}/script", headers=headers)).json()["link"])
        link = f"{parts.path}?{parts.query}"
        await api.post(link, json={"tabs": [{"tab": "Leads", "headers": cols}]})
        tab = (await api.get(url, headers=headers)).json()[0]["tabs"][0]
        mapping = {"full_name": "name", "phone_number": "phone", "email": "email", "created_time": "date"}
        await api.put(
            f"{url}/{sheet['id']}/tabs/{tab['id']}",
            json={"active": True, "mapping": mapping},
            headers=headers,
        )
        row = {"tab": "Leads", "row": 2, "values": dict(zip(cols, raw, strict=True))}
        bad = {"tab": "Leads", "row": 3, "values": {"full_name": "No Phone"}}
        [ok, refused] = (await api.post(link, json={"rows": [row, bad]})).json()["results"]
        assert ok["status"].startswith("CL99-") and ok["status"].endswith("✓")
        assert refused["status"].startswith("Not imported")
        lead = await pool.fetchrow("select * from app.leads where lead_code = $1", ok["status"][:-2])
        assert lead["phone_e164"] == "+919000000094" and lead["source"] == "meta_ads"
        assert lead["first_contact_at"].isoformat().startswith("2026-08-26T06:26:17")  # 11:56 AM in India
        assert "Facebook" in lead["notes"] and "yes, I have" in lead["notes"] and "l:" not in lead["notes"]
        again = (await api.post(link, json={"rows": [row | {"lead_code": ok["status"]}]})).json()["results"][
            0
        ]
        assert again["status"] == ok["status"]  # the same lead, counted again
    finally:
        await pool.execute("delete from app.leads where clinic_id = 'CL99' and phone_e164 = '+919000000094'")
        await pool.execute("delete from app.lead_sheets where clinic_id = 'CL99'")


@needs_db
async def test_calcom_webhook_moves_and_cancels(api: AsyncClient) -> None:
    import hashlib
    import hmac
    import json

    from app.api.v1.crm_console import _save_test_lead
    from app.crm import vault
    from app.crm.auth import Staff

    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    user = Staff(id=str(admin), email="", name="", bb_admin=True, roles={})
    saved = await _save_test_lead(
        user, {"type": "online", "name": "Cal Test", "phone": "+91 9000000093"}, "desktop"
    )
    async with pool.acquire() as conn:
        key = await vault.save(conn, "unused", "calcom key CL99 test")
        hook = await vault.save(conn, "hook-secret", "calcom webhook CL99 test")
    try:
        await pool.execute(
            "insert into app.calcom_accounts (clinic_id, key_secret, webhook_secret) values ('CL99', $1, $2)",
            key,
            hook,
        )
        lead = await pool.fetchval("select id from app.leads where lead_code = $1", saved["code"])
        await pool.execute(
            """insert into app.appointments (clinic_id, lead_id, type, preferred_date, calendar_event_id)
               values ('CL99', $1, 'online', current_date + 1, 'uid-old')""",
            lead,
        )

        async def send(event: dict[str, object], secret: str = "hook-secret") -> int:
            body = json.dumps(event).encode()
            sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            r = await api.post(
                "/v1/integrations/calcom/CL99", content=body, headers={"x-cal-signature-256": sig}
            )
            return r.status_code

        new: dict[str, object] = {
            "uid": "uid-new",
            "rescheduleUid": "uid-old",
            "startTime": "2030-01-02T05:00:00Z",
        }
        new |= {
            "endTime": "2030-01-02T05:30:00Z",
            "videoCallData": {"url": "https://meet.google.com/abc-defg-hij"},
        }
        moved: dict[str, object] = {"triggerEvent": "BOOKING_RESCHEDULED", "payload": new}
        assert await send(moved, "wrong") == 401
        assert await send(moved) == 200
        row = await pool.fetchrow("select * from app.appointments where lead_id = $1", lead)
        assert row["calendar_event_id"] == "uid-new" and row["meet_link"].startswith(
            "https://meet.google.com/"
        )
        assert row["slot"].lower.isoformat().startswith("2030-01-02T05:00")
        assert await send({"triggerEvent": "BOOKING_CANCELLED", "payload": {"uid": "uid-new"}}) == 200
        assert (
            await pool.fetchval("select status from app.appointments where lead_id = $1", lead) == "cancelled"
        )
    finally:
        await pool.execute("delete from app.leads where lead_code = $1", saved["code"])
        await pool.execute("delete from app.calcom_accounts where clinic_id = 'CL99'")
        async with pool.acquire() as conn:
            await vault.delete(conn, key, hook)


@needs_db
async def test_calcom_direct_bookings_are_cancelled(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib
    import hmac
    import json

    from app.crm import calcom, vault

    cancelled: list[tuple[str, str]] = []

    async def cancel(uid: str, reason: str, acc: object = None) -> None:
        cancelled.append((uid, reason))

    monkeypatch.setattr(calcom, "cancel", cancel)
    pool = await get_pool()
    async with pool.acquire() as conn:
        key = await vault.save(conn, "unused", "calcom key CL99 test")
        hook = await vault.save(conn, "hook-secret", "calcom webhook CL99 test")
    try:
        await pool.execute(
            "insert into app.calcom_accounts (clinic_id, key_secret, webhook_secret) values ('CL99', $1, $2)",
            key,
            hook,
        )

        async def send(payload: dict[str, object]) -> str:
            body = json.dumps({"triggerEvent": "BOOKING_CREATED", "payload": payload}).encode()
            sig = hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
            r = await api.post(
                "/v1/integrations/calcom/CL99", content=body, headers={"x-cal-signature-256": sig}
            )
            return str(r.json()["ok"])

        assert (await send({"uid": "made-by-crm", "metadata": {"lead": "CL99-00001"}})) == "ignored"
        assert (await send({"uid": "made-in-calcom", "metadata": {}})).startswith("cancelled")
        assert cancelled == [
            ("made-in-calcom", "Please book your online consultation through the clinic's website chat.")
        ]
    finally:
        await pool.execute("delete from app.calcom_accounts where clinic_id = 'CL99'")
        async with pool.acquire() as conn:
            await vault.delete(conn, key, hook)


@needs_db
async def test_webhooks_send_and_receive(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    import hashlib
    import hmac
    import json
    from urllib.parse import urlsplit

    import httpx

    from app.crm import vault, webhooks

    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    got: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        got.append(request)
        return httpx.Response(500 if len(got) == 1 else 200)  # fails once, then accepts

    real = httpx.AsyncClient
    monkeypatch.setattr(
        "app.crm.webhooks.httpx.AsyncClient", lambda **kw: real(transport=httpx.MockTransport(answer))
    )
    monkeypatch.setattr(webhooks, "WAITS", (0, 0, 0))
    url = "/v1/crm/console/CL99/integrations/webhooks"
    try:
        send = {
            "direction": "send",
            "name": "Zapier",
            "url": "https://hooks.example.com/x",
            "events": ["lead_new"],
        }
        assert (await api.post(url, json=send | {"url": "http://x.com"}, headers=headers)).status_code == 422
        hooks = (await api.post(url, json=send, headers=headers)).json()
        hooks = (
            await api.post(url, json={"direction": "receive", "name": "Website form"}, headers=headers)
        ).json()
        [out] = [h for h in hooks if h["direction"] == "send"]
        [inbox] = [h for h in hooks if h["direction"] == "receive"]
        parts = urlsplit(inbox["url"])
        assert (await api.post(f"{parts.path}?key=wrong", json={"name": "X"})).status_code == 403
        lead = {"name": "Web Form Test", "phone": "9000000092", "treatment": "PRP", "budget": "50k"}
        r = await api.post(f"{parts.path}?{parts.query}", json=lead)
        assert r.status_code == 200 and r.json()["lead_code"].startswith("CL99-")
        notes = await pool.fetchval("select notes from app.leads where lead_code = $1", r.json()["lead_code"])
        assert "budget: 50k" in notes  # extra keys kept
        for _ in range(50):  # the send runs in the background
            if len(got) >= 2:
                break
            await asyncio.sleep(0.1)
        assert len(got) == 2  # failed once (500), retried, accepted
        body = json.loads(got[1].content)
        assert body["event"] == "lead_new" and body["lead_code"] == r.json()["lead_code"]
        secret_id = await pool.fetchval("select secret from app.webhooks where id = $1::uuid", out["id"])
        async with pool.acquire() as conn:
            secret = await vault.read(conn, secret_id) or ""
        sig = "sha256=" + hmac.new(secret.encode(), got[1].content, hashlib.sha256).hexdigest()
        assert got[1].headers["x-neo-signature"] == sig
        [listed] = [h for h in (await api.get(url, headers=headers)).json() if h["direction"] == "send"]
        assert [(x["attempt"], x["ok"]) for x in listed["log"]] == [(2, True), (1, False)]
    finally:
        await pool.execute("delete from app.leads where clinic_id = 'CL99' and phone_e164 = '+919000000092'")
        for s in await pool.fetch("delete from app.webhooks where clinic_id = 'CL99' returning secret"):
            async with pool.acquire() as conn:
                await vault.delete(conn, s["secret"])


@needs_db
async def test_whatsapp_templates_and_test_message(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    import httpx

    from app.crm import vault

    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(201, json={"result": True})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        "app.crm.whatsapp.httpx.AsyncClient", lambda **kw: real(transport=httpx.MockTransport(answer))
    )
    url = "/v1/crm/console/CL99/integrations/whatsapp"
    try:
        r = await api.post(url, json={"api_key": "interakt-test-key-123"}, headers=headers)
        assert r.json()["connected"] and "interakt-test-key-123" not in r.text  # never sent back
        tpl = {"inclinic_confirmed": {"name": "appt_confirmed_v1", "language": "en",
                                      "values": ["name", "date", "time", "clinic_name"]}}  # fmt: skip
        r = await api.put(f"{url}/templates", json=tpl, headers=headers)
        assert r.json()["templates"]["inclinic_confirmed"]["name"] == "appt_confirmed_v1"
        bad = {"inclinic_confirmed": {"name": "x", "values": ["password"]}}
        assert (await api.put(f"{url}/templates", json=bad, headers=headers)).status_code == 422
        r = await api.post(
            f"{url}/test", json={"purpose": "inclinic_confirmed", "phone": "+91 90000 00091"}, headers=headers
        )
        assert r.status_code == 200 and r.json()["log"][0]["ok"]
        body = json.loads(sent[0].content)
        assert body["countryCode"] == "+91" and body["phoneNumber"] == "9000000091"
        assert body["template"]["name"] == "appt_confirmed_v1"
        assert body["template"]["bodyValues"][:3] == ["Test Patient", "Thu 29 Oct", "11:00 AM"]
        assert body["template"]["bodyValues"][3] == "Test Clinic"  # filled from the clinic itself
        assert sent[0].headers["authorization"] == "Basic interakt-test-key-123"
        tpl["inclinic_confirmed"]["buttons"] = ["map", "website"]
        await api.put(f"{url}/templates", json=tpl, headers=headers)
        test = {"purpose": "inclinic_confirmed", "phone": "9000000091"}
        await api.post(f"{url}/test", json=test, headers=headers)
        assert json.loads(sent[-1].content)["template"]["buttonValues"] == {
            "0": ["CL99/map"],
            "1": ["CL99/website"],
        }
        none = await api.post(
            f"{url}/test", json={"purpose": "reminder", "phone": "9000000091"}, headers=headers
        )
        assert none.status_code == 422 and "No template" in none.json()["detail"]
    finally:
        old = await pool.fetchval(
            "delete from app.whatsapp_accounts where clinic_id = 'CL99' returning key_secret"
        )
        await pool.execute("delete from app.whatsapp_log where clinic_id = 'CL99'")
        if old:
            async with pool.acquire() as conn:
                await vault.delete(conn, old)


@needs_db
async def test_button_links_open_the_right_page(api: AsyncClient) -> None:
    pool = await get_pool()
    maps = await pool.fetchval(
        "select coalesce(nullif(published->'contact', 'null'::jsonb), draft->'contact')->>'maps_link' "
        "from app.clinic_settings where clinic_id = 'CL01'"
    )
    if not maps:
        pytest.skip("CL01 has no map link in this database")
    r = await api.get("/v1/r/CL01/map", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == maps
    menu = await api.get("/v1/r/CL01/menu/page-clinic/b1", follow_redirects=False)
    assert menu.status_code == 302 and menu.headers["location"].startswith("https://")
    assert (await api.get("/v1/r/CL01/nothing", follow_redirects=False)).status_code == 404


@needs_db
async def test_whatsapp_send_to_a_contact(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    import httpx

    from app.api.v1.crm_console import _save_test_lead
    from app.crm import vault
    from app.crm.auth import Staff

    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    sent: list[httpx.Request] = []
    real = httpx.AsyncClient

    def answer(r: httpx.Request) -> httpx.Response:
        sent.append(r)
        return httpx.Response(201)

    monkeypatch.setattr(
        "app.crm.whatsapp.httpx.AsyncClient", lambda **kw: real(transport=httpx.MockTransport(answer))
    )
    user = Staff(id=str(admin), email="", name="", bb_admin=True, roles={})
    saved = await _save_test_lead(
        user, {"type": "book", "name": "Asha Rao", "phone": "+91 9000000089"}, "desktop"
    )
    url = "/v1/crm/console/CL99/integrations/whatsapp"
    try:
        lead = await pool.fetchval("select id from app.leads where lead_code = $1", saved["code"])
        await pool.execute(
            "insert into app.appointments (clinic_id, lead_id, type, preferred_date) "
            "values ('CL99', $1, 'in_clinic', '2030-01-02')",
            lead,
        )
        await api.post(url, json={"api_key": "interakt-test-key-123"}, headers=headers)
        tpl = {
            "inclinic_confirmed": {"name": "app_booked_ut", "values": ["name", "date", "time", "lead_code"]}
        }
        await api.put(f"{url}/templates", json=tpl, headers=headers)
        r = await api.post(
            f"{url}/send", json={"purpose": "inclinic_confirmed", "lead_code": saved["code"]}, headers=headers
        )
        assert r.status_code == 200
        body = json.loads(sent[0].content)
        assert body["phoneNumber"] == "9000000089"  # the contact's own phone
        assert body["template"]["bodyValues"] == [
            "Asha Rao",
            "Wed 02 Jan",
            "time to be confirmed",
            saved["code"],
        ]
        nobody = await api.post(
            f"{url}/send", json={"purpose": "inclinic_confirmed", "lead_code": "CL99-99999"}, headers=headers
        )
        assert nobody.status_code == 404
    finally:
        await pool.execute("delete from app.leads where lead_code = $1", saved["code"])
        old = await pool.fetchval(
            "delete from app.whatsapp_accounts where clinic_id = 'CL99' returning key_secret"
        )
        await pool.execute("delete from app.whatsapp_log where clinic_id = 'CL99'")
        if old:
            async with pool.acquire() as conn:
                await vault.delete(conn, old)
