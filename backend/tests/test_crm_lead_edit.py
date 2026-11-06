"""Editing a lead after the first call: its details, a waiting booking (saved without approving), and its
upcoming appointments. On temporary leads in the test clinic (CL99)."""

import json

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as
from tests.test_crm_inbox import MONDAY, TUESDAY

__all__ = ["api"]  # the client fixture


async def _admin(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    return signed_in_as(monkeypatch, str(admin))


@needs_db
async def test_details_are_edited_and_each_change_is_on_the_timeline(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _admin(monkeypatch)
    pool = await get_pool()
    a, a_code = await pool.fetchrow(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Edit Me', '+919000000501', 'chatbot') returning id, lead_code"""
    )
    b_code = await pool.fetchval(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Someone Else', '+919000000502', 'chatbot') returning lead_code"""
    )
    doctor = await pool.fetchval(
        "insert into app.doctors (clinic_id, name, role_title) "
        "values ('CL99', 'Dr Edit', 'Doctor') returning id"
    )
    url = f"/v1/crm/leads/{a_code}"
    try:
        r = await api.patch(
            url,
            json={"name": "  Edit   Done ", "email": "EDIT@Example.com", "treatment": "PRP", "type": "online",
                  "doctor_id": str(doctor)},
            headers=headers,
        )  # fmt: skip
        assert r.status_code == 200, r.text
        d = r.json()
        assert (d["name"], d["email"], d["treatment"], d["type"]) == (
            "Edit Done",
            "edit@example.com",
            "PRP",
            "online",
        )
        assert d["doctor"] == "Dr Edit" and d["doctor_id"] == str(doctor)
        changes = next(e["data"]["changes"] for e in d["events"] if "changes" in e["data"])
        assert changes["Treatment"] == ["—", "PRP"] and changes["Doctor"] == ["—", "Dr Edit"]
        assert changes["Type"] == ["—", "Online"]

        # Only what is sent changes; "" clears.
        r = await api.patch(url, json={"treatment": "", "type": ""}, headers=headers)
        assert (
            r.json()["treatment"] is None
            and r.json()["type"] is None
            and r.json()["email"] == "edit@example.com"
        )
        r = await api.patch(url, json={"phone": "9000000503", "phone_cc": "+91"}, headers=headers)
        assert r.json()["phone"] == "+919000000503"

        dup = await api.patch(url, json={"phone": "9000000502"}, headers=headers)
        assert dup.status_code == 409 and b_code in dup.json()["detail"]  # the other lead's code
        assert (await api.patch(url, json={"email": "not-an-email"}, headers=headers)).status_code == 422
        assert (await api.patch(url, json={"name": "x"}, headers=headers)).status_code == 422
        other_clinic_doctor = await pool.fetchval(
            "select id::text from app.doctors where clinic_id <> 'CL99' limit 1"
        )
        if other_clinic_doctor:
            bad = await api.patch(url, json={"doctor_id": other_clinic_doctor}, headers=headers)
            assert bad.status_code == 422
        same = await api.patch(url, json={"name": "Edit Done"}, headers=headers)  # nothing new: no event
        assert sum("changes" in e["data"] for e in same.json()["events"]) == 3
    finally:
        await pool.execute("select app.delete_patient_data($1)", a)
        await pool.execute("delete from app.leads where lead_code = $1", b_code)
        await pool.execute("delete from app.doctors where id = $1", doctor)


@needs_db
async def test_a_waiting_booking_is_changed_without_approving_it(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _admin(monkeypatch)
    pool = await get_pool()
    lead, code = await pool.fetchrow(
        """insert into app.leads (clinic_id, full_name, phone_e164, source, treatment)
           values ('CL99', 'Change Booking', '+919000000504', 'chatbot', 'Hair') returning id, lead_code"""
    )
    try:
        request = str(
            await pool.fetchval(
                f"""insert into app.requests (clinic_id, lead_id, type, data)
                   values ('CL99', $1, 'book', '{{"date": "{MONDAY}", "time": "any", "treatment": "Hair"}}')
                   returning id""",
                lead,
            )
        )
        appt = await pool.fetchval(
            f"""insert into app.appointments (clinic_id, lead_id, request_id, type, preferred_date)
               values ('CL99', $1, $2::uuid, 'in_clinic', '{MONDAY}') returning id""",
            lead, request,
        )  # fmt: skip
        url = f"/v1/crm/requests/{request}/change"
        assert (await api.post(url, json={}, headers=headers)).status_code == 422  # nothing to change
        r = await api.post(url, json={"treatment": "PRP Treatment", "date": TUESDAY}, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "pending" and r.json()["treatment"] == "PRP Treatment"  # still waiting
        assert r.json()["appointment"]["day"] == TUESDAY
        assert await pool.fetchval("select treatment from app.leads where id = $1", lead) == "PRP Treatment"
        assert await pool.fetchval("select status from app.appointments where id = $1", appt) == "pending"
        event = await pool.fetchval(
            "select data from app.lead_events where lead_id = $1 and kind = 'request' "
            "order by created_at desc",
            lead,
        )
        assert json.loads(event)["status"] == "changed"

        waiting = await api.get(f"/v1/crm/leads/{code}/appointments", headers=headers)
        assert waiting.status_code == 200
        assert [(a["id"], a["status"], a["day"]) for a in waiting.json()] == [(str(appt), "pending", TUESDAY)]
        callback = str(
            await pool.fetchval(
                "insert into app.requests (clinic_id, lead_id, type, data) "
                "values ('CL99', $1, 'callback', '{}') "
                "returning id",
                lead,
            )
        )
        wrong = await api.post(f"/v1/crm/requests/{callback}/change", json={"note": "x"}, headers=headers)
        assert wrong.status_code == 422  # only a booking
    finally:
        await pool.execute("select app.delete_patient_data($1)", lead)
