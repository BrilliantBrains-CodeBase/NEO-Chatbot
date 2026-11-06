"""Lead & Booking API (migration 0042): an endpoint matched from a sample payload; calls with the
X-API-Key header make a lead (More information kept) or a lead and a booking request; repeats with the same
external id answer the first result. On the test clinic CL99; removes what it makes."""

import json
from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.api.v1.crm_api import flatten, parse_day, parse_time
from app.core.db import get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture

BASE = "/v1/crm/console/CL99/integrations/api"
SAMPLE = {
    "patient": {
        "full_name": "Api Test Patient",
        "contact": {"mobile": "9000000611", "mail": "api@example.com"},
    },
    "service": "PRP",
    "appointment": {"day": "", "slot": "", "mode": "video"},
    "utm": {"campaign": "Diwali"},
    "ref": "ext-1",
    "budget": "50k",
}
MAPPING = {
    "name": "patient.full_name", "phone": "patient.contact.mobile", "email": "patient.contact.mail",
    "treatment": "service", "campaign": "utm.campaign", "external_id": "ref",
}  # fmt: skip


def test_reading_payloads() -> None:
    assert flatten({"a": {"b": "x", "c": [{"d": 1}]}, "e": None, "f": ""}) == {"a.b": "x", "a.c.0.d": "1"}
    assert parse_day("2026-11-10") == date(2026, 11, 10) and parse_day("10/11/2026") == date(2026, 11, 10)
    assert parse_day("10 Nov 2026") == date(2026, 11, 10) and parse_day("someday") is None
    assert (
        parse_time("10:30") == "10:30" and parse_time("2 pm") == "14:00" and parse_time("10.30 AM") == "10:30"
    )
    assert parse_time("any") is None and parse_time("10") is None and parse_time("25:00") is None


async def _admin(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    return signed_in_as(monkeypatch, str(admin))


async def _post(api: AsyncClient, e: dict[str, Any], body: object, key: str | None = None) -> Any:
    path = e["url"].split("/v1/", 1)[1]
    headers = {"X-API-Key": key if key is not None else e["key"]}
    return await api.post(f"/v1/{path}", content=json.dumps(body), headers=headers)


@needs_db
async def test_leads_and_bookings_from_an_outside_system(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _admin(monkeypatch)
    pool = await get_pool()
    try:
        r = await api.post(BASE, json={"name": "Test partner", "creates": "lead"}, headers=headers)
        assert r.status_code == 200, r.text
        [e] = [x for x in r.json() if x["name"] == "Test partner"]
        assert e["key"].startswith("neo_") and e["url"].endswith(f"/v1/integrations/api/{e['id']}")
        url = f"{BASE}/{e['id']}"

        # Off, and not matched yet.
        assert (await _post(api, e, SAMPLE)).status_code == 403
        assert (await _post(api, e, SAMPLE, key="wrong")).status_code == 401
        assert (await api.put(url, json={"active": True}, headers=headers)).status_code == 422
        r = await api.put(url, json={"sample": SAMPLE, "mapping": MAPPING, "active": True}, headers=headers)
        assert r.status_code == 200, r.text
        [e] = [x for x in r.json() if x["id"] == e["id"]]
        assert "patient.contact.mobile" in e["paths"] and e["active"]

        preview = (await api.post(f"{url}/test", json={}, headers=headers)).json()
        assert preview["lead"]["phone"] == "9000000611" and preview["problems"] == []
        assert preview["extra"]["budget"] == "50k"

        r = await _post(api, e, SAMPLE)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["ok"] and out["duplicate"] is False and out["request_id"] is None
        lead = await pool.fetchrow(
            "select id, source, campaign, treatment, extra from app.leads where lead_code = $1",
            out["lead_code"],
        )
        assert (lead["source"], lead["campaign"], lead["treatment"]) == ("api", "Diwali", "PRP")
        assert json.loads(lead["extra"])["budget"] == "50k"  # More information
        again = (await _post(api, e, SAMPLE)).json()  # a retry with the same external id
        assert again["duplicate"] is True and again["lead_code"] == out["lead_code"]
        bad = await _post(api, e, {"patient": {"full_name": "No Phone"}})
        assert bad.status_code == 422 and not bad.json()["ok"]

        detail = (await api.get(f"/v1/crm/leads/{out['lead_code']}", headers=headers)).json()
        assert detail["extra"]["budget"] == "50k"

        # A booking: no date -> a call back request; a time that is not free -> the day kept, no time held.
        booking = MAPPING | {
            "date": "appointment.day",
            "time": "appointment.slot",
            "type": "appointment.mode",
        }
        await api.put(url, json={"creates": "booking", "mapping": booking}, headers=headers)
        no_date = SAMPLE | {"ref": "ext-2"}
        r = (await _post(api, e, no_date)).json()
        kind = await pool.fetchval("select type from app.requests where id = $1::uuid", r["request_id"])
        assert kind == "callback" and r["time_held"] is None
        day = (date.today() + timedelta(days=3)).isoformat()
        taken = SAMPLE | {"ref": "ext-3", "appointment": {"day": day, "slot": "03:00", "mode": "video"}}
        r = (await _post(api, e, taken)).json()
        req = await pool.fetchrow("select type, data from app.requests where id = $1::uuid", r["request_id"])
        assert req["type"] == "online" and r["time_held"] is False
        assert "not free" in json.loads(req["data"])["reason"]
        appt = await pool.fetchrow(
            "select preferred_date, slot from app.appointments where request_id = $1::uuid", r["request_id"]
        )
        assert (
            appt["preferred_date"].isoformat() == day and appt["slot"] is None
        )  # the front desk picks a time

        log = (await api.get(BASE, headers=headers)).json()
        [e] = [x for x in log if x["id"] == e["id"]]
        assert [c["status_code"] for c in e["log"]][:2] == [200, 200] and e["calls_7d"] >= 3
    finally:
        for (lead_id,) in await pool.fetch(
            "select id from app.leads where clinic_id = 'CL99' and phone_e164 = '+919000000611'"
        ):
            await pool.execute("select app.delete_patient_data($1)", lead_id)
        for x in (await api.get(BASE, headers=headers)).json():
            if x["name"] == "Test partner":
                await api.delete(f"{BASE}/{x['id']}", headers=headers)
