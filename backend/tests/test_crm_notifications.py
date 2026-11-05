"""The bell (migration 0036): requests make notifications, read and cleared are each person's own, permissions
and clinics are kept apart, and a patient data deletion takes them too. Test clinics CL98 and CL99."""

import json
from typing import Any
from uuid import UUID

import asyncpg
import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from app.crm import failures
from tests.test_chat_store import req
from tests.test_crm_access import world
from tests.test_crm_auth import api, needs_db, signed_in_as
from tests.test_db_access import person

__all__ = ["api", "world"]  # the fixtures

URL = "/v1/crm/notifications"
pytestmark = needs_db


async def _request(lead: Any, kind: str = "callback", clinic: str = "CL99", **data: Any) -> str:
    pool = await get_pool()
    return str(
        await pool.fetchval(
            """insert into app.requests (clinic_id, lead_id, type, data)
               values ($1, $2, $3, $4::jsonb) returning id""",
            clinic,
            lead,
            kind,
            json.dumps(data),
        )  # fmt: skip
    )


async def _clean(lead: Any) -> None:
    await (await get_pool()).execute("delete from app.requests where lead_id = $1", lead)


async def _list(api: AsyncClient, headers: dict[str, str], **params: Any) -> dict[str, Any]:
    r = await api.get(URL, params={"clinic": "CL99", **params}, headers=headers)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def _mine(body: dict[str, Any], request: str) -> dict[str, Any]:
    return next(i for i in body["items"] if i["request_id"] == request)


async def test_a_request_makes_a_notification_and_handling_resolves_it(tx: asyncpg.Connection) -> None:
    lead = await tx.fetchval(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Bell Test', '+919000008801', 'chatbot') returning id"""
    )
    plain = await tx.fetchval(
        "insert into app.requests (clinic_id, lead_id, type) values ('CL99', $1, 'book') returning id", lead
    )
    urgent = await tx.fetchval(
        """insert into app.requests (clinic_id, lead_id, type, data)
           values ('CL99', $1, 'callback', '{"urgent": true}') returning id""",
        lead,
    )
    one = await tx.fetchrow("select * from app.notifications where request_id = $1", plain)
    assert (one["kind"], one["severity"], one["resolved_at"]) == ("book", "normal", None)
    two = await tx.fetchrow("select * from app.notifications where request_id = $1", urgent)
    assert (two["kind"], two["severity"]) == ("emergency", "urgent")
    await tx.execute("update app.requests set status = 'done' where id = $1", plain)
    assert await tx.fetchval("select resolved_at from app.notifications where request_id = $1", plain)


async def test_a_problem_in_the_bell_never_fails_the_request(tx: asyncpg.Connection) -> None:
    lead = await tx.fetchval(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Bell Test', '+919000008802', 'chatbot') returning id"""
    )
    # "urgent" that is not true or false makes the trigger fail: the request is still saved.
    made = await tx.fetchval(
        """insert into app.requests (clinic_id, lead_id, type, data)
           values ('CL99', $1, 'book', '{"urgent": "maybe"}') returning id""",
        lead,
    )
    assert made is not None
    assert await tx.fetchval("select count(*) from app.notifications where request_id = $1", made) == 0


async def test_patient_data_deletion_takes_the_notifications(tx: asyncpg.Connection) -> None:
    lead = await tx.fetchval(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Bell Test', '+919000008803', 'chatbot') returning id"""
    )
    await tx.execute("insert into app.requests (clinic_id, lead_id, type) values ('CL99', $1, 'book')", lead)
    assert await tx.fetchval("select count(*) from app.notifications where lead_id = $1", lead) == 1
    await tx.execute("select app.delete_patient_data($1)", lead)
    assert await tx.fetchval("select count(*) from app.notifications where lead_id = $1", lead) == 0


async def test_read_and_clear_are_each_persons_own(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    lead = world["lead"]["id"]
    request = await _request(lead, name="Asha", treatment="Hair")
    try:
        desk = signed_in_as(monkeypatch, world["desk"]["id"])
        item = _mine(await _list(api, desk), request)
        assert item["read"] is False and item["name"] == "Asha" and item["tab"] == "callback"
        before = (await _list(api, desk))["unread"]

        r = await api.post(f"{URL}/{item['id']}/read", headers=desk)
        assert r.status_code == 200 and r.json()["unread"] == before - 1
        assert _mine(await _list(api, desk), request)["read"] is True
        assert request not in {i["request_id"] for i in (await _list(api, desk, show="unread"))["items"]}

        r = await api.post(f"{URL}/{item['id']}/unread", headers=desk)
        assert r.json()["unread"] == before

        assert (await api.post(f"{URL}/{item['id']}/dismiss", headers=desk)).status_code == 200
        assert request not in {i["request_id"] for i in (await _list(api, desk))["items"]}

        # A colleague still has it, unread, and the request is untouched.
        manager = signed_in_as(monkeypatch, world["manager"]["id"])
        assert _mine(await _list(api, manager), request)["read"] is False
        pool = await get_pool()
        assert (
            await pool.fetchval("select status from app.requests where id = $1::uuid", request) == "pending"
        )
    finally:
        await _clean(lead)


async def test_mark_all_read_then_one_unread_and_clear_read(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    lead = world["lead"]["id"]
    first, second = await _request(lead), await _request(lead)
    try:
        desk = signed_in_as(monkeypatch, world["desk"]["id"])
        r = await api.post(f"{URL}/read-all", params={"clinic": "CL99"}, headers=desk)
        assert r.status_code == 200 and r.json()["unread"] == 0
        one = _mine(await _list(api, desk), first)
        assert one["read"] is True

        r = await api.post(f"{URL}/{one['id']}/unread", headers=desk)
        assert r.json()["unread"] == 1

        third = await _request(lead)  # after "mark all read": new is unread
        assert _mine(await _list(api, desk), third)["read"] is False

        r = await api.post(f"{URL}/clear-read", params={"clinic": "CL99"}, headers=desk)
        assert r.status_code == 200
        left = {i["request_id"] for i in (await _list(api, desk))["items"]}
        assert second not in left and first in left and third in left  # only what was read
    finally:
        await _clean(lead)


async def test_handled_shows_who_and_stops_counting(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    lead = world["lead"]["id"]
    request = await _request(lead)
    try:
        desk = signed_in_as(monkeypatch, world["desk"]["id"])
        before = (await _list(api, desk))["unread"]
        manager = signed_in_as(monkeypatch, world["manager"]["id"])
        done = await api.post(
            f"/v1/crm/requests/{request}/done", json={"outcome": "answered"}, headers=manager
        )
        assert done.status_code == 200, done.text
        desk = signed_in_as(monkeypatch, world["desk"]["id"])
        body = await _list(api, desk)
        item = _mine(body, request)
        assert item["resolved"] is True and item["resolved_by"] and body["unread"] == before - 1
    finally:
        await _clean(lead)


async def test_an_emergency_comes_first_and_cannot_be_cleared_until_handled(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    lead = world["lead"]["id"]
    urgent = await _request(lead, urgent=True, reason="EMERGENCY in chat: bleeding")
    await _request(lead)  # newer, but an emergency still comes first
    try:
        desk = signed_in_as(monkeypatch, world["desk"]["id"])
        body = await _list(api, desk)
        assert body["items"][0]["request_id"] == urgent and body["urgent"] >= 1
        assert body["items"][0]["kind"] == "emergency" and "bleeding" in body["items"][0]["reason"]
        one = body["items"][0]["id"]
        assert (await api.post(f"{URL}/{one}/dismiss", headers=desk)).status_code == 409
        await api.post(f"{URL}/{one}/read", headers=desk)
        await api.post(f"{URL}/clear-read", params={"clinic": "CL99"}, headers=desk)
        assert _mine(await _list(api, desk), urgent)  # clear-read leaves it too
        # Turning callbacks off does not hide it.
        put = await api.put(f"{URL}/prefs", json={"off_kinds": ["callback"]}, headers=desk)
        assert put.status_code == 200
        assert _mine(await _list(api, desk), urgent)

        done = await api.post(f"/v1/crm/requests/{urgent}/done", json={"outcome": "answered"}, headers=desk)
        assert done.status_code == 200, done.text
        assert (await api.post(f"{URL}/{one}/dismiss", headers=desk)).status_code == 200
    finally:
        await _clean(lead)


async def test_an_emergency_with_no_phone_is_acknowledged_for_everyone(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    pool = await get_pool()
    made: UUID = await pool.fetchval(
        """insert into app.notifications (clinic_id, kind, severity, dedupe_key)
           values ('CL99', 'emergency', 'urgent', 'test:no-phone') returning id"""
    )
    try:
        desk = signed_in_as(monkeypatch, world["desk"]["id"])
        assert (await api.post(f"{URL}/{made}/dismiss", headers=desk)).status_code == 200
        manager = signed_in_as(monkeypatch, world["manager"]["id"])
        item = next(i for i in (await _list(api, manager))["items"] if i["id"] == str(made))
        assert item["resolved"] is True and item["resolved_by"]
    finally:
        await pool.execute("delete from app.notifications where id = $1", made)


async def test_kinds_turned_off_are_left_out_and_prefs_follow_the_person(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    lead = world["lead"]["id"]
    request = await _request(lead, "question")
    desk_id = world["desk"]["id"]
    try:
        desk = signed_in_as(monkeypatch, desk_id)
        assert (await api.get(f"{URL}/prefs", headers=desk)).json()["off_kinds"] == []
        r = await api.put(f"{URL}/prefs", json={"off_kinds": ["question"], "sound": True}, headers=desk)
        assert r.status_code == 200
        got = (await api.get(f"{URL}/prefs", headers=desk)).json()
        assert got["off_kinds"] == ["question"] and got["sound"] is True
        assert request not in {i["request_id"] for i in (await _list(api, desk))["items"]}
        refused = await api.put(f"{URL}/prefs", json={"off_kinds": ["emergency"]}, headers=desk)
        assert refused.status_code == 422
    finally:
        await _clean(lead)
        await (await get_pool()).execute(
            "delete from app.notification_prefs where user_id = $1::uuid", desk_id
        )


async def test_permissions_and_clinics_are_kept_apart(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    theirs = await _request(world["other_lead"]["id"], clinic="CL98")
    ours = await _request(world["lead"]["id"])
    try:
        doctor = signed_in_as(monkeypatch, world["doctor"]["id"])  # no Inbox
        assert (await api.get(URL, params={"clinic": "CL99"}, headers=doctor)).status_code == 403
        assert (await api.get(f"{URL}/summary", params={"clinic": "CL99"}, headers=doctor)).status_code == 403

        desk = signed_in_as(monkeypatch, world["desk"]["id"])  # only in CL99
        assert (await api.get(URL, params={"clinic": "CL98"}, headers=desk)).status_code == 403
        pool = await get_pool()
        other = await pool.fetchval("select id from app.notifications where request_id = $1::uuid", theirs)
        for action in ("read", "unread", "dismiss"):
            r = await api.post(f"{URL}/{other}/{action}", headers=desk)
            assert r.status_code == 403, action
        assert ours in {i["request_id"] for i in (await _list(api, desk))["items"]}
        assert (await api.post(f"{URL}/{UUID(int=1)}/read", headers=desk)).status_code == 404
    finally:
        await _clean(world["other_lead"]["id"])
        await _clean(world["lead"]["id"])


async def test_counts_per_clinic_only_cover_this_persons_clinics(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    await _request(world["other_lead"]["id"], clinic="CL98")
    await _request(world["lead"]["id"])
    try:
        both = signed_in_as(monkeypatch, world["both"]["id"])
        counts = (await api.get(f"{URL}/clinics", headers=both)).json()
        assert counts["CL98"]["unread"] >= 1 and counts["CL99"]["unread"] >= 1
        desk = signed_in_as(monkeypatch, world["desk"]["id"])
        assert set((await api.get(f"{URL}/clinics", headers=desk)).json()) == {"CL99"}
        doctor = signed_in_as(monkeypatch, world["doctor"]["id"])  # no Inbox
        assert (await api.get(f"{URL}/clinics", headers=doctor)).json() == {}
    finally:
        await _clean(world["other_lead"]["id"])
        await _clean(world["lead"]["id"])


async def _lead_in(tx: asyncpg.Connection, phone: str, source: str = "chatbot") -> Any:
    return await tx.fetchval(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Bell Test', $1, $2) returning id""",
        phone, source,
    )  # fmt: skip


async def test_open_minutes_skip_nights_closed_days_and_holidays(tx: asyncpg.Connection) -> None:
    await tx.execute(
        """update app.clinics set timezone = 'Asia/Kolkata', open_time = '10:00', close_time = '19:00',
             closed_weekdays = '{0}' where id = 'CL99'"""
    )
    await tx.execute("delete from app.clinic_holidays where clinic_id = 'CL99'")

    async def minutes(start: str, end: str) -> int:
        got: int = await tx.fetchval(
            "select app.open_minutes('CL99', $1::text::timestamptz, $2::text::timestamptz)", start, end
        )
        return got

    # 2031-03-10 is a Monday, 2031-03-09 a Sunday (closed).
    assert await minutes("2031-03-10 11:00+05:30", "2031-03-10 12:30+05:30") == 90
    assert await minutes("2031-03-10 18:30+05:30", "2031-03-11 10:30+05:30") == 60  # across the night
    assert await minutes("2031-03-08 18:00+05:30", "2031-03-10 11:00+05:30") == 120  # across a closed Sunday
    assert await minutes("2031-03-10 20:00+05:30", "2031-03-10 23:00+05:30") == 0  # after closing
    await tx.execute("insert into app.clinic_holidays (clinic_id, day) values ('CL99', '2031-03-10')")
    assert await minutes("2031-03-10 11:00+05:30", "2031-03-10 12:30+05:30") == 0


async def test_requests_left_waiting_are_flagged_once_and_resolve_when_handled(
    tx: asyncpg.Connection,
) -> None:
    await tx.execute(
        """update app.clinics set open_time = '00:00', close_time = '23:59', closed_weekdays = '{}'
           where id = 'CL99'"""
    )
    await tx.execute("delete from app.clinic_holidays where clinic_id = 'CL99'")
    lead = await _lead_in(tx, "+919000008811")

    async def made(kind: str, hours: int, data: str = "{}") -> Any:
        return await tx.fetchval(
            """insert into app.requests (clinic_id, lead_id, type, data, created_at)
               values ('CL99', $1, $2, $3::jsonb, now() - make_interval(hours => $4)) returning id""",
            lead, kind, data, hours,
        )  # fmt: skip

    callback, booking_soon = await made("callback", 2), await made("book", 1)
    booking, old = await made("book", 3), await made("callback", 24 * 8)
    emergency = await made("callback", 3, '{"urgent": true}')
    cancel = await made("cancel", 5)
    await tx.execute("select app.job_flag_late_requests()")
    await tx.execute("select app.job_flag_late_requests()")  # a second run adds nothing

    async def late(request: Any) -> list[str]:
        rows = await tx.fetch("select kind from app.notifications where dedupe_key = $1", f"late:{request}")
        return [r["kind"] for r in rows]

    assert await late(callback) == ["callback_late"]
    assert await late(booking) == ["booking_late"]
    for quiet in (booking_soon, old, emergency, cancel):
        assert await late(quiet) == []
    await tx.execute("update app.requests set status = 'done' where id = $1", callback)
    assert await tx.fetchval(
        "select resolved_at from app.notifications where dedupe_key = $1", f"late:{callback}"
    )


async def test_new_leads_group_into_one_and_show_as_new_again(tx: asyncpg.Connection) -> None:
    async def rollup() -> Any:
        return await tx.fetchrow(
            """select * from app.notifications where clinic_id = 'CL99' and kind = 'lead_new'
               order by created_at desc limit 1"""
        )

    await tx.execute("delete from app.notifications where clinic_id = 'CL99' and kind = 'lead_new'")
    await _lead_in(tx, "+919000008821")  # the chatbot's arrive as a request instead
    assert await rollup() is None
    first = await _lead_in(tx, "+919000008822", "manual")
    one = await rollup()
    assert (one["count"], one["lead_id"], one["screen"]) == (1, first, "leads")
    someone = await person(tx, "bell_read", "CL99", "front_desk")
    await tx.execute(
        "insert into app.notification_receipts (notification_id, user_id, read_at) values ($1, $2, now())",
        one["id"], someone,
    )  # fmt: skip
    await _lead_in(tx, "+919000008823", "meta_ads")
    two = await rollup()
    assert (two["id"], two["count"], two["lead_id"]) == (one["id"], 2, None)
    assert (
        await tx.fetchval(
            "select count(*) from app.notification_receipts where notification_id = $1", one["id"]
        )
        == 0
    )


async def test_assigning_tells_only_that_person_unless_they_took_it(tx: asyncpg.Connection) -> None:
    lead = await _lead_in(tx, "+919000008831")
    desk = await person(tx, "bell_desk", "CL99", "front_desk")
    await tx.execute("update app.leads set assigned_to = $2 where id = $1", lead, desk)
    row = await tx.fetchrow(
        "select * from app.notifications where kind = 'lead_assigned' and lead_id = $1", lead
    )
    assert (row["user_id"], row["screen"]) == (desk, "leads")
    await tx.execute("update app.leads set assigned_to = null where id = $1", lead)
    await tx.execute("select set_config('request.jwt.claim.sub', $1, true)", str(desk))
    await tx.execute("update app.leads set assigned_to = $2 where id = $1", lead, desk)
    count = await tx.fetchval(
        "select count(*) from app.notifications where kind = 'lead_assigned' and lead_id = $1", lead
    )
    assert count == 1


async def test_an_access_request_waits_until_decided(tx: asyncpg.Connection) -> None:
    made = await tx.fetchval(
        """insert into app.access_requests (clinic_id, role, full_name, email)
           values ('CL99', 'front_desk', 'New Person', 'bell-access@test.invalid') returning id"""
    )
    key = f"access:{made}"
    row = await tx.fetchrow("select * from app.notifications where dedupe_key = $1", key)
    assert (row["kind"], row["screen"], row["resolved_at"]) == ("access_request", "team", None)
    await tx.execute(
        "update app.access_requests set status = 'rejected', decided_at = now() where id = $1", made
    )
    assert await tx.fetchval("select resolved_at from app.notifications where dedupe_key = $1", key)


async def test_a_failing_service_shows_once_a_day_and_names_only_the_service(tx: asyncpg.Connection) -> None:
    await failures.record(tx, "CL99", "WhatsApp")
    await failures.record(tx, "CL99", "WhatsApp")
    rows = await tx.fetch(
        "select detail, screen from app.notifications where clinic_id = 'CL99' "
        "and kind = 'integration_failed' "
        "and detail = 'WhatsApp'"
    )
    assert [(r["detail"], r["screen"]) for r in rows] == [("WhatsApp", "dash_integrations")]


async def test_each_person_sees_only_what_their_role_and_name_allow(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    pool = await get_pool()

    async def make(key: str, kind: str, screen: str, user: Any = None) -> str:
        return str(
            await pool.fetchval(
                """insert into app.notifications (clinic_id, kind, screen, user_id, dedupe_key)
                   values ('CL99', $1, $2, $3::uuid, $4) returning id""",
                kind,
                screen,
                user,
                key,
            )  # fmt: skip
        )

    team = await make("test:team", "access_request", "team")
    failed = await make("test:failed", "integration_failed", "dash_integrations")
    mine = await make("test:mine", "lead_assigned", "leads", world["desk"]["id"])
    theirs = await make("test:theirs", "lead_assigned", "leads", world["manager"]["id"])
    try:

        async def seen(who: str, limit: int = 100) -> set[str]:
            h = signed_in_as(monkeypatch, world[who]["id"])
            return {i["id"] for i in (await _list(api, h, limit=limit))["items"]}

        desk = await seen("desk")
        assert mine in desk and not {team, failed, theirs} & desk  # Front Desk: no Team, no Dashboard
        manager = await seen("manager")
        assert {team, failed, theirs} <= manager and mine not in manager

        h = signed_in_as(monkeypatch, world["desk"]["id"])
        for hidden in (team, failed, theirs):
            assert (await api.post(f"{URL}/{hidden}/read", headers=h)).status_code == 404, hidden
        assert (await api.post(f"{URL}/{mine}/read", headers=h)).status_code == 200
        off = await api.put(f"{URL}/prefs", json={"off_kinds": ["lead_assigned"]}, headers=h)
        assert off.status_code == 200 and mine not in await seen("desk")
    finally:
        await pool.execute("delete from app.notifications where dedupe_key like 'test:%'")
        await pool.execute("delete from app.notification_prefs where user_id = $1::uuid", world["desk"]["id"])


async def test_a_no_phone_emergency_shows_once_per_chat(tx: asyncpg.Connection) -> None:
    from app.crm import alerts

    await alerts.record_no_phone(tx, "CL99", req().session_id)
    await alerts.record_no_phone(tx, "CL99", req().session_id)
    rows = await tx.fetch(
        "select kind, severity, lead_id from app.notifications where dedupe_key = $1",
        f"emergency:{req().session_id}",
    )
    assert [(r["kind"], r["severity"], r["lead_id"]) for r in rows] == [("emergency", "urgent", None)]
