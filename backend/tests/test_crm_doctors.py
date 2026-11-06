"""Dashboard → Doctors: add and save a doctor with all settings; in-clinic and online hours may overlap but
two rows of one kind may not; 5 / 10 minute slots; clinic defaults. Uses test clinic CL99 and cleans up."""

from typing import Any

import pytest
from httpx import AsyncClient

from app.core.db import close_pool, get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture

URL = "/v1/crm/console/CL99/doctors"


def _doctor(**over: Any) -> dict[str, Any]:
    return {
        "name": "Dr Test Doctor",
        "role_title": "Consultant",
        "qualifications": "MBBS",
        "photo": "https://example.com/dr.jpg",
        "about": "Test doctor.",
        "stats": [{"label": "Years experience", "value": "10+"}],
        "in_clinic_minutes": 10,
        "online_minutes": None,
        "in_clinic": [{"weekday": 1, "start": "10:00", "end": "13:00"}],
        "online": [{"weekday": 1, "start": "14:00", "end": "16:00"}],
        "leave": [{"from_date": "2030-01-05", "to_date": "2030-01-06", "reason": "Conference"}],
        **over,
    }


@needs_db
async def test_doctor_with_all_settings(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    before = await pool.fetchrow(
        "select slot_minutes, online_slot_minutes from app.clinics where id = 'CL99'"
    )
    made: str | None = None
    try:
        # Add: every setting comes back as saved.
        r = await api.post(URL, json=_doctor(), headers=headers)
        assert r.status_code == 200, r.text
        d = next(x for x in r.json()["doctors"] if x["name"] == "Dr Test Doctor")
        made = d["id"]
        assert d["in_clinic_minutes"] == 10 and d["online_minutes"] is None and not d["calcom"]
        assert d["in_clinic"] == [{"weekday": 1, "start": "10:00", "end": "13:00"}]
        assert d["online"] == [{"weekday": 1, "start": "14:00", "end": "16:00"}]
        assert d["leave"][0]["reason"] == "Conference" and d["stats"][0]["value"] == "10+"
        assert d["photo"] == "https://example.com/dr.jpg"

        # In-clinic and online hours may overlap (a booking in one hides that time in the other).
        both = _doctor(online=[{"weekday": 1, "start": "10:00", "end": "13:00"}])
        r = await api.put(f"{URL}/{made}", json=both, headers=headers)
        assert r.status_code == 200, r.text

        # Two rows of the same kind that overlap are refused, and nothing changes.
        bad = _doctor(
            online=[
                {"weekday": 1, "start": "10:00", "end": "13:00"},
                {"weekday": 1, "start": "12:00", "end": "14:00"},
            ]
        )
        r = await api.put(f"{URL}/{made}", json=bad, headers=headers)
        assert r.status_code == 422 and "overlap" in r.text
        rows = await pool.fetchval(
            "select count(*) from app.doctor_availability where doctor_id = $1::uuid", made
        )
        assert rows == 2

        # A length that is not offered is refused; 5 minutes is fine.
        r = await api.put(f"{URL}/{made}", json=_doctor(online_minutes=25), headers=headers)
        assert r.status_code == 422
        r = await api.put(
            f"{URL}/{made}",
            json=_doctor(online_minutes=5, active=False, online=[], about="Changed."),
            headers=headers,
        )
        assert r.status_code == 200, r.text
        d = next(x for x in r.json()["doctors"] if x["id"] == made)
        assert d["online_minutes"] == 5 and d["active"] is False
        assert d["online"] == [] and d["about"] == "Changed."

        # Clinic defaults.
        r = await api.put(
            "/v1/crm/console/CL99/doctors-defaults",
            json={"slot_minutes": 10, "online_slot_minutes": 20},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["defaults"] == {"slot_minutes": 10, "online_slot_minutes": 20}
        r = await api.put(
            "/v1/crm/console/CL99/doctors-defaults",
            json={"slot_minutes": 7, "online_slot_minutes": 20},
            headers=headers,
        )
        assert r.status_code == 422
    finally:
        if made:
            await pool.execute("delete from app.doctors where id = $1::uuid", made)
        await pool.execute(
            "update app.clinics set slot_minutes = $1, online_slot_minutes = $2 where id = 'CL99'",
            before["slot_minutes"], before["online_slot_minutes"],
        )  # fmt: skip
        await close_pool()


@needs_db
async def test_crm_edits_a_doctors_hours_and_leave(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    made: str | None = None
    try:
        r = await api.post(URL, json=_doctor(), headers=headers)
        made = next(x["id"] for x in r.json()["doctors"] if x["name"] == "Dr Test Doctor")
        url = f"/v1/crm/availability/{made}/schedule?clinic=CL99"
        got = (await api.get(url, headers=headers)).json()
        assert got["in_clinic"] == [{"weekday": 1, "start": "10:00", "end": "13:00"}] and not got["calcom"]

        body: dict[str, Any] = {
            "in_clinic": [{"weekday": 3, "start": "09:00", "end": "12:00"}],
            "online": [{"weekday": 3, "start": "11:00", "end": "14:00"}],  # may overlap in-clinic
            "leave": [{"from_date": "2030-02-01", "to_date": "2030-02-03", "reason": "Travel"}],
        }
        r = await api.put(url, json=body, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["online"] == body["online"] and r.json()["leave"][0]["reason"] == "Travel"
        # The profile set in the Dashboard is untouched.
        row = await pool.fetchrow(
            "select in_clinic_minutes, qualifications from app.doctors where id = $1::uuid", made
        )
        assert row["in_clinic_minutes"] == 10 and row["qualifications"] == "MBBS"

        bad = body | {"online": body["online"] * 2}  # the same online row twice
        r = await api.put(url, json=bad, headers=headers)
        assert r.status_code == 422 and "overlap" in r.text
        r = await api.get("/v1/crm/availability/not-a-doctor/schedule?clinic=CL99", headers=headers)
        assert r.status_code == 404
    finally:
        if made:
            await pool.execute("delete from app.doctors where id = $1::uuid", made)
        await close_pool()


@needs_db
async def test_staff_book_a_free_time(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    made: str | None = None
    try:
        # Monday 7 Jan 2030: in-clinic 10:00-13:00 (10-minute slots), online 10:00-13:00 (clinic's 30).
        both = _doctor(online=[{"weekday": 1, "start": "10:00", "end": "13:00"}], leave=[])
        r = await api.post(URL, json=both, headers=headers)
        made = next(x["id"] for x in r.json()["doctors"] if x["name"] == "Dr Test Doctor")
        url = f"/v1/crm/availability/{made}/book?clinic=CL99"
        new = {"name": "Test Booked Patient", "phone": "9000000777"}
        visit = {"date": "2030-01-07", "time": "10:00", "type": "in_clinic", "patient": new}

        r = await api.post(url, json=visit, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["tab"] == "book" and r.json()["request_id"]
        code = r.json()["lead_code"]
        # A pending booking request in the Inbox, with a pending appointment holding the 10-minute time.
        a = await pool.fetchrow(
            """select a.status, upper(a.slot) - lower(a.slot) len, r.type, r.status rstatus, l.stage
               from app.requests r join app.appointments a on a.request_id = r.id
               join app.leads l on l.id = r.lead_id where r.id = $1::uuid""",
            r.json()["request_id"],
        )
        assert a["status"] == "pending" and a["len"].seconds == 600
        assert a["type"] == "book" and a["rstatus"] == "pending" and a["stage"] == "new"
        # Booked by staff: the lead is theirs (not left in the Inbox) and the request waits on it in Leads.
        waiting = (await api.get(f"/v1/crm/leads/{r.json()['lead_code']}/requests", headers=headers)).json()
        assert r.json()["request_id"] in [w["id"] for w in waiting]

        r = await api.post(url, json=visit | {"patient": None, "lead_code": code}, headers=headers)
        assert r.status_code == 409  # held by the request

        # Online: an Online consults request; needs an email (for the Meet link on approval).
        online = {"date": "2030-01-07", "time": "11:00", "type": "online", "lead_code": code}
        r = await api.post(url, json=online, headers=headers)
        assert r.status_code == 422 and "email" in r.text
        r = await api.post(url, json=online | {"email": "Test.Patient@Example.com"}, headers=headers)
        assert r.status_code == 200 and r.json()["tab"] == "online", r.text
        a = await pool.fetchrow(
            """select a.status, upper(a.slot) - lower(a.slot) len, r.type, l.email
               from app.requests r join app.appointments a on a.request_id = r.id
               join app.leads l on l.id = r.lead_id where r.id = $1::uuid""",
            r.json()["request_id"],
        )
        assert a["status"] == "pending" and a["len"].seconds == 1800 and a["type"] == "online"
        assert a["email"] == "test.patient@example.com"
        r = await api.post(
            url, json=visit | {"time": "11:10", "patient": None, "lead_code": code}, headers=headers
        )
        assert r.status_code == 409  # inside the 30-minute online consult

        r = await api.post(url, json=visit | {"time": "15:00"}, headers=headers)
        assert r.status_code == 409  # the doctor does not work then
    finally:
        leads = [r["id"] for r in await pool.fetch(
            "select id from app.leads where clinic_id = 'CL99' and full_name = 'Test Booked Patient'"
        )]  # fmt: skip
        for t in ("appointments", "requests", "lead_events", "tasks"):
            await pool.execute(f"delete from app.{t} where lead_id = any($1::uuid[])", leads)
        await pool.execute("delete from app.leads where id = any($1::uuid[])", leads)
        if made:
            await pool.execute("delete from app.doctors where id = $1::uuid", made)
        await close_pool()
