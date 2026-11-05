"""Dashboard → Integrations → Website forms: a clinic's own form sends each submission to its address."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture


@needs_db
async def test_form_submissions_become_leads(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    url = "/v1/crm/console/CL99/integrations/forms"
    phone = "+919000012345"
    try:
        [form] = (await api.post(url, json={"name": "Book appointment"}, headers=headers)).json()
        link = (await api.get(f"{url}/{form['id']}/link", headers=headers)).json()["link"]
        parts = urlsplit(link)
        address = f"{parts.path}?key={parse_qs(parts.query)['key'][0]}"
        booking = {"name": "Test Patient", "phone": "9000012345", "email": "t@example.com", "message": "Knee"}
        # As a Google Apps Script form sends it: JSON labelled text/plain. Off: only the fields are kept.
        sent = json.dumps(booking).encode()
        r = await api.post(address, content=sent, headers={"Content-Type": "text/plain;charset=utf-8"})
        assert r.status_code == 200 and r.json()["ok"] is False
        [listed] = (await api.get(url, headers=headers)).json()
        assert listed["fields"] == ["name", "phone", "email", "message"]
        assert listed["sample"][0] == "Test Patient"
        # Map and turn on; then a normal form post becomes a lead.
        mapping = {"name": "name", "phone": "phone", "email": "email", "message": "notes"}
        r = await api.put(f"{url}/{form['id']}", json={"active": True, "mapping": mapping}, headers=headers)
        assert r.status_code == 200 and r.json()[0]["active"]
        r = await api.post(address, data=booking)
        assert r.json()["ok"] is True and r.json()["result"].startswith("CL99-")
        lead = await pool.fetchrow(
            "select source, full_name, notes from app.leads where clinic_id = 'CL99' and phone_e164 = $1",
            phone,
        )
        assert lead["source"] == "website_form" and lead["full_name"] == "Test Patient"
        assert "Knee" in lead["notes"]
        assert (await api.post(f"{parts.path}?key=wrong", data=booking)).status_code == 403
        await api.delete(f"{url}/{form['id']}", headers=headers)
        assert (await api.post(address, data=booking)).status_code == 403  # removed: the address is dead
    finally:
        await pool.execute("delete from app.lead_forms where clinic_id = 'CL99'")
        ids = "select id from app.leads where clinic_id = 'CL99' and phone_e164 = $1"
        await pool.execute(f"delete from app.lead_events where lead_id in ({ids})", phone)
        await pool.execute("delete from app.leads where clinic_id = 'CL99' and phone_e164 = $1", phone)


@needs_db
async def test_auto_capture_sends_site_forms(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.chat import guard

    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    url = "/v1/crm/console/CL99/websites"
    site = "https://capture-test.example.com"
    phone = "+919000054321"
    form = {
        "fields": {"First Name": "Ravi", "Last Name": "Kumar", "Mobile Number": "90000 54321",
                   "Department": "Orthopaedics", "Message": "Knee pain"},
        "page": site + "/book-appointment",
        "utm": {"utm_source": "google", "utm_campaign": "knee"},
    }  # fmt: skip

    async def send() -> bool:
        guard._clinics.clear()
        r = await api.post("/v1/widget/form?clinic=CL99", content=json.dumps(form), headers={"Origin": site})
        return bool(r.json()["ok"])

    try:
        [s] = (await api.post(url, json={"address": site}, headers=headers)).json()
        await api.post(f"{url}/{s['id']}/decision", json={"status": "approved"}, headers=headers)
        assert not await send()  # approved, but capture is off
        r = await api.put(f"{url}/{s['id']}/capture", json={"on": True}, headers=headers)
        assert r.json()[0]["capture_forms"] is True
        shown = await api.get("/v1/widget/show?clinic=CL99&path=/", headers={"Origin": site})
        assert shown.json()["capture"] is True
        assert await send()
        lead = await pool.fetchrow(
            "select full_name, source, treatment, campaign, notes from app.leads "
            "where clinic_id = 'CL99' and phone_e164 = $1",
            phone,
        )
        assert lead["full_name"] == "Ravi Kumar" and lead["source"] == "website_form"
        assert lead["treatment"] == "Orthopaedics" and lead["campaign"] == "knee"
        assert "Knee pain" in lead["notes"] and "/book-appointment" in lead["notes"]
        other = await api.post(
            "/v1/widget/form?clinic=CL99",
            content=json.dumps(form),
            headers={"Origin": "https://evil.example"},
        )
        assert other.json()["ok"] is False  # not the clinic's approved site
    finally:
        await pool.execute("delete from app.clinic_websites where clinic_id = 'CL99'")
        await pool.execute("update app.clinics set allowed_origins = '{}' where id = 'CL99'")
        ids = "select id from app.leads where clinic_id = 'CL99' and phone_e164 = $1"
        await pool.execute(f"delete from app.lead_events where lead_id in ({ids})", phone)
        await pool.execute("delete from app.leads where clinic_id = 'CL99' and phone_e164 = $1", phone)
