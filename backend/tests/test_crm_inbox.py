"""CRM Inbox: list, approve, reject and done, on a temporary lead in the test clinic (CL99)."""

import csv
import io
import json
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture

# Real days ahead, never fixed ones: a time that has passed is refused, so a fixed date stops working the
# day it arrives. The doctors in these tests work on Mondays.
_today = date.today()
_monday = _today + timedelta(days=(7 - _today.weekday()) % 7 or 7)
MONDAY, TUESDAY = _monday.isoformat(), (_monday + timedelta(days=1)).isoformat()
NEXT_MONDAY = (_monday + timedelta(days=7)).isoformat()
THIRD_MONDAY = (_monday + timedelta(days=14)).isoformat()


@needs_db
async def test_inbox_search_dates_treatment_and_export(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    a, a_code = await pool.fetchrow(
        """insert into app.leads (clinic_id, full_name, phone_e164, source, treatment)
           values ('CL99', 'Searchable Almas', '+919000007101', 'chatbot', 'ZZ Rare Treatment')
           returning id, lead_code"""
    )
    b, b_code = await pool.fetchrow(
        """insert into app.leads (clinic_id, full_name, phone_e164, source, treatment)
           values ('CL99', 'Other Person', '+919000007102', 'chatbot', 'ZZ Other Treatment')
           returning id, lead_code"""
    )
    made = [
        (
            a,
            "book",
            {"name": "Faz Family", "treatment": "ZZ Rare Treatment", "date": "2031-03-10", "time": "any"},
        ),
        (b, "book", {"treatment": "ZZ Other Treatment", "date": "2031-03-20", "time": "10:00"}),
        (a, "cancel", {"booked_date": "2031-03-10", "treatment": "=Formula"}),
    ]
    try:
        ids = [
            str(
                await pool.fetchval(
                    "insert into app.requests (clinic_id, lead_id, type, data) "
                    "values ('CL99', $1, $2, $3::jsonb) returning id",
                    lead, kind, json.dumps(data),
                )
            )
            for lead, kind, data in made
        ]  # fmt: skip

        # The Inbox lists unassigned leads (one row each), with their waiting requests.
        ours = {a_code: "A", b_code: "B"}

        async def found(**params: str) -> set[str]:
            r = await api.get("/v1/crm/inbox", params={"clinic": "CL99", **params}, headers=headers)
            assert r.status_code == 200
            return {ours[i["code"]] for i in r.json()["items"] if i["code"] in ours}

        assert await found() == {"A", "B"}
        assert await found(q="almas") == {"A"}  # the lead's name
        assert await found(q="+91 90000-07102") == {"B"}  # the phone, typed with a space and a dash
        assert await found(q="zz rare") == {"A"}  # treatment
        assert await found(type="cancel") == {"A"}  # a cancellation waiting
        assert await found(type="none", q="zz") == set()  # both have a request waiting
        assert await found(treatment="ZZ Other Treatment") == {"B"}
        assert await found(**{"to": "2020-01-01"}) == set()  # by the day the lead came in
        assert await found(**{"from": date.today().isoformat()}) == {"A", "B"}
        for odd in ("-", "%", "_", "\\"):
            assert await found(q=odd) == set(), odd  # plain text, and never an error
        assert await found(source="chatbot", q="almas") == {"A"}
        assert await found(source="manual", q="almas") == set()

        async def order(**params: str) -> dict[str, Any]:
            r = await api.get(
                "/v1/crm/inbox", params={"clinic": "CL99", "q": "zz", **params}, headers=headers
            )
            assert r.status_code == 200
            shown: dict[str, Any] = r.json()
            return shown

        page = await order(limit="1")  # the two "ZZ" leads, latest contact first
        assert page["total"] == 2 and [i["code"] for i in page["items"]] == [b_code]
        second = await order(limit="1", offset="1")
        assert second["total"] == 2 and [i["code"] for i in second["items"]] == [a_code]  # the next page
        types = {c["key"]: c["count"] for c in page["types"]}
        assert types["book"] == 2 and types["cancel"] == 1 and types["none"] == 0  # follow the search
        asked = {r["type"] for r in second["items"][0]["requests"]}
        assert asked == {"book", "cancel"} and second["items"][0]["pending"] == 2
        # Not in Leads until assigned; an Admin can still list them there.
        leads = await api.get("/v1/crm/leads", params={"clinic": "CL99", "q": "zz"}, headers=headers)
        assert {i["code"] for i in leads.json()["items"]} & set(ours) == set()
        leads = await api.get(
            "/v1/crm/leads", params={"clinic": "CL99", "q": "zz", "owner": "unassigned"}, headers=headers
        )
        assert set(ours) <= {i["code"] for i in leads.json()["items"]}
        waiting = await api.get(f"/v1/crm/leads/{a_code}/requests", headers=headers)
        assert waiting.status_code == 200 and [r["id"] for r in waiting.json()] == [ids[0], ids[2]]

        one = await api.get(f"/v1/crm/requests/{ids[0]}", headers=headers)
        assert one.status_code == 200 and one.json()["id"] == ids[0]
        missing = "00000000-0000-0000-0000-000000000000"
        assert (await api.get(f"/v1/crm/requests/{missing}", headers=headers)).status_code == 404
        assert (await api.get("/v1/crm/requests/nope", headers=headers)).status_code == 422

        ticked = await api.post(
            "/v1/crm/inbox/export", json={"clinic": "CL99", "ids": [ids[1]]}, headers=headers
        )
        rows_out = list(csv.DictReader(io.StringIO(ticked.text.lstrip("\ufeff"))))
        assert [r["Treatment"] for r in rows_out] == ["ZZ Other Treatment"]
        elsewhere = await api.post(
            "/v1/crm/inbox/export", json={"clinic": "NFHT", "ids": [ids[1]]}, headers=headers
        )
        assert (
            elsewhere.text.lstrip("\ufeff").strip().count("\n") == 0
        )  # headings only: not that clinic's request

        r = await api.get("/v1/crm/inbox", params={"clinic": "CL99"}, headers=headers)
        assert "ZZ Rare Treatment" in r.json()["treatments"]  # the leads' treatments

        file = await api.get("/v1/crm/inbox/export", params={"clinic": "CL99", "q": "almas"}, headers=headers)
        assert file.status_code == 200 and file.headers["content-type"].startswith("text/csv")
        rows = list(csv.DictReader(io.StringIO(file.text.lstrip("\ufeff"))))
        assert len(rows) == 2 and {r["Type"] for r in rows} == {"Booking request", "Cancellation"}
        booked = next(r for r in rows if r["Type"] == "Booking request")
        assert booked["Phone"] == "+919000007101" or booked["Phone"] == "+91 9000007101"
        assert booked["Asked date"] == "2031-03-10" and booked["Asked time"] == "Any time"
        assert "Faz Family" in booked["Name"]
        cancel = next(r for r in rows if r["Type"] == "Cancellation")
        assert cancel["Booked date"] == "2031-03-10" and cancel["Treatment"] == "'=Formula"
    finally:
        await pool.execute("delete from app.requests where lead_id = any($1::uuid[])", [a, b])
        await pool.execute("delete from app.lead_events where lead_id = any($1::uuid[])", [a, b])
        await pool.execute("delete from app.leads where id = any($1::uuid[])", [a, b])


@needs_db
async def test_inbox_approve_reject_and_done(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
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
                    f"""insert into app.requests (clinic_id, lead_id, type, data)
                       values ('CL99', $1, $2, '{{"date": "{MONDAY}", "time": "any"}}')
                       returning id""",
                    lead,
                    kind,
                )
            )
        await pool.execute(
            f"""insert into app.appointments (clinic_id, lead_id, request_id, type, preferred_date)
               values ('CL99', $1, $2::uuid, 'in_clinic', '{MONDAY}')""",
            lead,
            ids["book"],
        )
        r = await api.get("/v1/crm/inbox?clinic=CL99&q=%2B919000000003", headers=headers)
        assert r.status_code == 200
        types = {c["key"]: c["count"] for c in r.json()["types"]}
        assert types["book"] == 1 and types["callback"] == 1
        mine = r.json()["items"][0]["requests"]
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

    async def book(start, name, email, phone, note, acc=None):  # type: ignore[no-untyped-def]
        booked.append((start.isoformat(), email))
        return calcom.Booking(uid="test-uid", meet_link="https://meet.google.com/abc-defg-hij")

    monkeypatch.setattr(calcom, "book", book)
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
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
                f"""insert into app.requests (clinic_id, lead_id, type, data)
                   values ('CL99', $1, 'online', '{{"date": "{MONDAY}", "time": "any"}}') returning id""",
                lead,
            )
        )
        await pool.execute(
            f"""insert into app.appointments (clinic_id, lead_id, request_id, type, preferred_date)
               values ('CL99', $1, $2::uuid, 'online', '{MONDAY}')""",
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
            (datetime.fromisoformat(f"{MONDAY}T11:30:00+05:30"), "online@example.com")
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

    async def cancel(uid, reason, acc=None):  # type: ignore[no-untyped-def]
        calls.append(("cancel", uid))

    async def reschedule(uid, start, reason, acc=None):  # type: ignore[no-untyped-def]
        calls.append(("reschedule", uid))
        return calcom.Booking(uid="moved-uid", meet_link=None)  # the link stays the same

    monkeypatch.setattr(calcom, "cancel", cancel)
    monkeypatch.setattr(calcom, "reschedule", reschedule)
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    lead = await pool.fetchval(
        """insert into app.leads (clinic_id, full_name, phone_e164, email, source)
           values ('CL99', 'Calcom Test', '+919000000007', 'c@example.com', 'chatbot') returning id"""
    )
    try:
        appts = []
        for day in (MONDAY, NEXT_MONDAY):  # two booked online consults with Cal.com bookings
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
            f"""insert into app.requests (clinic_id, lead_id, type, data, match_status,
                 matched_appointment_id)
               values ('CL99', $1, 'reschedule', '{{"date": "{THIRD_MONDAY}", "time": "any"}}', 'matched', $2)
               returning id""",
            lead,
            appts[1],
        )
        r = await api.post(f"/v1/crm/requests/{cancel_req}/approve", headers=headers)
        assert r.status_code == 200 and calls == [("cancel", f"uid-{MONDAY}")]
        url = f"/v1/crm/requests/{resch_req}/approve"
        assert (await api.post(url, headers=headers)).status_code == 422  # online needs an exact time
        r = await api.post(url, json={"time": "12:00"}, headers=headers)
        assert r.status_code == 200, r.text
        assert calls[-1] == ("reschedule", f"uid-{NEXT_MONDAY}")
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
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    lead = await pool.fetchval(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Appt Test', '+919000000008', 'chatbot') returning id"""
    )
    try:
        await pool.execute(
            f"""insert into app.appointments (clinic_id, lead_id, type, slot) values ('CL99', $1, 'in_clinic',
                 tstzrange('{TUESDAY} 14:30+05:30', '{TUESDAY} 14:45+05:30', '[)'))""",
            lead,
        )
        await pool.execute(
            f"""insert into app.appointments (clinic_id, lead_id, type, preferred_date, status)
               values ('CL99', $1, 'online', '{TUESDAY}', 'cancelled')""",
            lead,
        )
        url = f"/v1/crm/appointments?clinic=CL99&from={TUESDAY}"
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

    async def cancel(uid, reason, acc=None):  # type: ignore[no-untyped-def]
        calls.append("cancel " + uid)

    async def reschedule(uid, start, reason, acc=None):  # type: ignore[no-untyped-def]
        calls.append("move " + uid)
        return calcom.Booking(uid="uid-moved", meet_link=None)

    monkeypatch.setattr(calcom, "cancel", cancel)
    monkeypatch.setattr(calcom, "reschedule", reschedule)
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
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
            ("online", datetime.fromisoformat(f"{MONDAY}T11:00+05:30"), "uid-1"),
            ("in_clinic", datetime.fromisoformat(f"{TUESDAY}T11:00+05:30"), None),
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
            json={"date": NEXT_MONDAY, "time": "12:00"},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert (r.json()["day"], r.json()["time"], r.json()["doctor"]) == (NEXT_MONDAY, "12:00", "Dr Move")
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
