"""The bell (migration 0036): requests make notifications, read and cleared are each person's own, permissions
and clinics are kept apart, and a patient data deletion takes them too. Test clinics CL98 and CL99."""

import json
from typing import Any
from uuid import UUID

import asyncpg
import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_chat_store import req
from tests.test_crm_access import world
from tests.test_crm_auth import api, needs_db, signed_in_as

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


async def test_a_no_phone_emergency_shows_once_per_chat(tx: asyncpg.Connection) -> None:
    from app.crm import alerts

    await alerts.record_no_phone(tx, "CL99", req().session_id)
    await alerts.record_no_phone(tx, "CL99", req().session_id)
    rows = await tx.fetch(
        "select kind, severity, lead_id from app.notifications where dedupe_key = $1",
        f"emergency:{req().session_id}",
    )
    assert [(r["kind"], r["severity"], r["lead_id"]) for r in rows] == [("emergency", "urgent", None)]
