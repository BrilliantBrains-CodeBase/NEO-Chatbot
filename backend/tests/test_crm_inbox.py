"""CRM Inbox: list, approve, reject and done, on a temporary lead in the test clinic (CL99)."""

from datetime import datetime

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture


@needs_db
async def test_inbox_approve_reject_and_done(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    lead = await pool.fetchval(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Inbox Test', '+919000000003', 'chatbot') returning id"""
    )
    try:
        ids = {}
        for kind in ("book", "callback", "online"):
            ids[kind] = str(
                await pool.fetchval(
                    """insert into app.requests (clinic_id, lead_id, type, data)
                       values ('CL99', $1, $2, '{"date": "2026-11-02", "time": "any"}')
                       returning id""",
                    lead,
                    kind,
                )
            )
        await pool.execute(
            """insert into app.appointments (clinic_id, lead_id, request_id, type, preferred_date)
               values ('CL99', $1, $2::uuid, 'in_clinic', '2026-11-02')""",
            lead,
            ids["book"],
        )
        r = await api.get("/v1/crm/inbox?clinic=CL99", headers=headers)
        assert r.status_code == 200
        pending = {c["key"]: c["count"] for c in r.json()["pending"]}
        assert pending["book"] >= 1 and pending["callback"] >= 1
        mine = [i for i in r.json()["items"] if i["id"] in ids.values()]
        assert {i["type"] for i in mine} == {"book", "callback", "online"}

        r = await api.post(f"/v1/crm/requests/{ids['book']}/approve", headers=headers)
        assert r.status_code == 200 and r.json()["status"] == "done"
        assert r.json()["appointment"]["status"] == "confirmed"
        assert await pool.fetchval("select stage from app.leads where id = $1", lead) == "booked"
        again = await api.post(f"/v1/crm/requests/{ids['book']}/approve", headers=headers)
        assert again.status_code == 409  # already handled

        wrong = await api.post(f"/v1/crm/requests/{ids['callback']}/approve", headers=headers)
        assert wrong.status_code == 422
        r = await api.post(
            f"/v1/crm/requests/{ids['callback']}/done", json={"outcome": "answered"}, headers=headers
        )
        assert r.json()["status"] == "done"
        r = await api.post(
            f"/v1/crm/requests/{ids['online']}/reject", json={"reason": "No slots"}, headers=headers
        )
        assert r.json()["status"] == "rejected"
        kinds = [k for (k,) in await pool.fetch("select kind from app.lead_events where lead_id = $1", lead)]
        assert kinds.count("request") == 3 and "call" in kinds
    finally:
        await pool.execute("select app.delete_patient_data($1)", lead)


@needs_db
async def test_online_approve_books_calcom_and_keeps_the_link(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.crm import calcom

    booked: list[tuple[str, str]] = []

    async def book(start, name, email, phone, note):  # type: ignore[no-untyped-def]
        booked.append((start.isoformat(), email))
        return calcom.Booking(uid="test-uid", meet_link="https://meet.google.com/abc-defg-hij")

    monkeypatch.setattr(calcom, "book", book)
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    lead = await pool.fetchval(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Online Test', '+919000000004', 'chatbot') returning id"""
    )
    doctor = await pool.fetchval(  # a doctor working online on Mondays, for this test only
        "insert into app.doctors (clinic_id, name, role_title)"
        " values ('CL99', 'Dr Test', 'Test') returning id"
    )
    await pool.execute(
        """insert into app.doctor_availability (doctor_id, clinic_id, weekday, mode, start_time, end_time)
           values ($1, 'CL99', 1, 'online', '10:00', '19:00')""",
        doctor,
    )
    try:
        req = str(
            await pool.fetchval(
                """insert into app.requests (clinic_id, lead_id, type, data)
                   values ('CL99', $1, 'online', '{"date": "2026-11-02", "time": "any"}') returning id""",
                lead,
            )
        )
        await pool.execute(
            """insert into app.appointments (clinic_id, lead_id, request_id, type, preferred_date)
               values ('CL99', $1, $2::uuid, 'online', '2026-11-02')""",
            lead,
            req,
        )
        url = f"/v1/crm/requests/{req}/approve"
        r = await api.post(url, json={"time": "11:30"}, headers=headers)
        assert r.status_code == 422 and "no email" in r.json()["detail"]
        await pool.execute("update app.leads set email = 'online@example.com' where id = $1", lead)
        r = await api.post(url, headers=headers)
        assert r.status_code == 422 and "Any time" in r.json()["detail"]
        r = await api.get(f"/v1/crm/slots?clinic=CL99&mode=online&doctor_id={doctor}", headers=headers)
        assert [d["name"] for d in r.json()["doctors"]] == ["Dr Test"]
        assert all(t >= "10:00" for times in r.json()["days"].values() for t in times)
        r = await api.post(url, json={"time": "09:00"}, headers=headers)
        assert r.status_code == 409  # before the doctor starts
        r = await api.post(url, json={"time": "11:30", "treatment": "Beard Transplant"}, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["treatment"] == "Beard Transplant"
        assert r.json()["appointment"]["doctor"] == "Dr Test"
        appt = r.json()["appointment"]
        assert appt["meet_link"] == "https://meet.google.com/abc-defg-hij" and appt["status"] == "confirmed"
        assert [(datetime.fromisoformat(t), e) for t, e in booked] == [
            (datetime.fromisoformat("2026-11-02T11:30:00+05:30"), "online@example.com")
        ]
        assert await pool.fetchval(
            "select calendar_event_id from app.appointments where lead_id = $1", lead
        ) == ("test-uid")
    finally:
        await pool.execute("select app.delete_patient_data($1)", lead)
        await pool.execute("delete from app.doctors where id = $1", doctor)


@needs_db
async def test_online_cancel_and_reschedule_update_calcom(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.crm import calcom

    calls: list[tuple[str, str]] = []

    async def cancel(uid, reason):  # type: ignore[no-untyped-def]
        calls.append(("cancel", uid))

    async def reschedule(uid, start, reason):  # type: ignore[no-untyped-def]
        calls.append(("reschedule", uid))
        return calcom.Booking(uid="moved-uid", meet_link=None)  # the link stays the same

    monkeypatch.setattr(calcom, "cancel", cancel)
    monkeypatch.setattr(calcom, "reschedule", reschedule)
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    lead = await pool.fetchval(
        """insert into app.leads (clinic_id, full_name, phone_e164, email, source)
           values ('CL99', 'Calcom Test', '+919000000007', 'c@example.com', 'chatbot') returning id"""
    )
    try:
        appts = []
        for day in ("2026-11-02", "2026-11-09"):  # two booked online consults with Cal.com bookings
            appts.append(
                await pool.fetchval(
                    """insert into app.appointments (clinic_id, lead_id, type, slot, status, meet_link,
                         calendar_event_id, confirmed_at)
                       values ('CL99', $1, 'online', tstzrange(($2 || ' 11:00+05:30')::timestamptz,
                         ($2 || ' 11:15+05:30')::timestamptz, '[)'), 'confirmed',
                         'https://meet.google.com/aaa-bbbb-ccc', 'uid-' || $2, now()) returning id""",
                    lead,
                    day,
                )
            )
        cancel_req = await pool.fetchval(
            """insert into app.requests (clinic_id, lead_id, type, data, match_status, matched_appointment_id)
               values ('CL99', $1, 'cancel', '{}', 'matched', $2) returning id""",
            lead,
            appts[0],
        )
        resch_req = await pool.fetchval(
            """insert into app.requests (clinic_id, lead_id, type, data, match_status, matched_appointment_id)
               values ('CL99', $1, 'reschedule', '{"date": "2026-11-16", "time": "any"}', 'matched', $2)
               returning id""",
            lead,
            appts[1],
        )
        r = await api.post(f"/v1/crm/requests/{cancel_req}/approve", headers=headers)
        assert r.status_code == 200 and calls == [("cancel", "uid-2026-11-02")]
        url = f"/v1/crm/requests/{resch_req}/approve"
        assert (await api.post(url, headers=headers)).status_code == 422  # online needs an exact time
        r = await api.post(url, json={"time": "12:00"}, headers=headers)
        assert r.status_code == 200, r.text
        assert calls[-1] == ("reschedule", "uid-2026-11-09")
        new = r.json()["appointment"]
        assert new["meet_link"] == "https://meet.google.com/aaa-bbbb-ccc" and new["status"] == "confirmed"
        uid = await pool.fetchval(
            "select calendar_event_id from app.appointments where id = $1::uuid", new["id"]
        )
        assert uid == "moved-uid"
    finally:
        await pool.execute("select app.delete_patient_data($1)", lead)


@needs_db
async def test_appointments_of_a_day(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    lead = await pool.fetchval(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Appt Test', '+919000000008', 'chatbot') returning id"""
    )
    try:
        await pool.execute(
            """insert into app.appointments (clinic_id, lead_id, type, slot) values ('CL99', $1, 'in_clinic',
                 tstzrange('2026-11-03 14:30+05:30', '2026-11-03 14:45+05:30', '[)'))""",
            lead,
        )
        await pool.execute(
            """insert into app.appointments (clinic_id, lead_id, type, preferred_date, status)
               values ('CL99', $1, 'online', '2026-11-03', 'cancelled')""",
            lead,
        )
        url = "/v1/crm/appointments?clinic=CL99&from=2026-11-03"
        mine = [a for a in (await api.get(url, headers=headers)).json()["items"] if a["name"] == "Appt Test"]
        assert [(a["time"], a["type"], a["status"]) for a in mine] == [("14:30", "in_clinic", "pending")]
        r = await api.get(url + "&status=all", headers=headers)
        assert len([a for a in r.json()["items"] if a["name"] == "Appt Test"]) == 2
        long = await api.get(
            "/v1/crm/appointments?clinic=CL99&from=2026-01-01&to=2026-12-31", headers=headers
        )
        assert long.status_code == 422
    finally:
        await pool.execute("select app.delete_patient_data($1)", lead)


@needs_db
async def test_appointment_move_visit_and_cancel(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.crm import calcom

    calls: list[str] = []

    async def cancel(uid, reason):  # type: ignore[no-untyped-def]
        calls.append("cancel " + uid)

    async def reschedule(uid, start, reason):  # type: ignore[no-untyped-def]
        calls.append("move " + uid)
        return calcom.Booking(uid="uid-moved", meet_link=None)

    monkeypatch.setattr(calcom, "cancel", cancel)
    monkeypatch.setattr(calcom, "reschedule", reschedule)
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    doctor = await pool.fetchval(
        "insert into app.doctors (clinic_id, name, role_title) values ('CL99', 'Dr Move', 'MD') returning id"
    )
    await pool.execute(
        """insert into app.doctor_availability (doctor_id, clinic_id, weekday, mode, start_time, end_time)
           values ($1, 'CL99', 1, 'online', '10:00', '19:00')""",
        doctor,
    )
    lead = await pool.fetchval(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Move Test', '+919000000009', 'chatbot') returning id"""
    )
    try:
        ids = []
        for kind, start, uid in (
            ("online", datetime.fromisoformat("2026-11-02T11:00+05:30"), "uid-1"),
            ("in_clinic", datetime.fromisoformat("2026-11-03T11:00+05:30"), None),
        ):
            ids.append(
                await pool.fetchval(
                    """insert into app.appointments (clinic_id, lead_id, doctor_id, type, slot, status,
                         confirmed_at, calendar_event_id)
                       values ('CL99', $1, $2, $3, tstzrange($4::timestamptz,
                         $4::timestamptz + interval '15 min', '[)'), 'confirmed', now(), $5) returning id""",
                    lead,
                    doctor,
                    kind,
                    start,
                    uid,
                )  # fmt: skip
            )
        online, inclinic = ids
        r = await api.post(
            f"/v1/crm/appointments/{online}/move",
            json={"date": "2026-11-09", "time": "12:00"},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert (r.json()["day"], r.json()["time"], r.json()["doctor"]) == ("2026-11-09", "12:00", "Dr Move")
        assert calls == ["move uid-1"]
        url = f"/v1/crm/appointments/{online}/status"
        assert (await api.post(url, json={"status": "cancelled"}, headers=headers)).status_code == 422
        r = await api.post(url, json={"status": "cancelled", "reason": "Patient travelling"}, headers=headers)
        assert r.json()["status"] == "cancelled" and calls[-1] == "cancel uid-moved"
        again = await api.post(url, json={"status": "visited"}, headers=headers)
        assert again.status_code == 409  # already closed
        r = await api.post(
            f"/v1/crm/appointments/{inclinic}/status", json={"status": "visited"}, headers=headers
        )
        assert r.json()["status"] == "visited" and r.json()["stage"] == "visited"
    finally:
        await pool.execute("select app.delete_patient_data($1)", lead)
        await pool.execute("delete from app.doctors where id = $1", doctor)
