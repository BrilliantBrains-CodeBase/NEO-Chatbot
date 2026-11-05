"""Emergencies in the chat: staff always hear about it. Real database, rolled back, test clinic CL99."""

import json
from typing import Any

import asyncpg
import pytest

from app.api.v1.crm_inbox import SELECT, _item
from app.chat import canvas, leads, service, store
from app.core.config import get_settings
from app.crm import alerts, email, webhooks, whatsapp
from tests.test_chat_store import req
from tests.test_db_access import person

needs_db = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")
PHONE = "+91 9800000077"


@pytest.fixture(autouse=True)
def quiet(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str | None]]:
    """No real email or WhatsApp: records each alert raised instead, and starts with no chat remembered."""
    raised: list[tuple[str, str | None]] = []
    monkeypatch.setattr(alerts, "_raised", {})
    monkeypatch.setattr(alerts, "emergency", lambda clinic, code: raised.append((clinic, code)))
    monkeypatch.setattr(webhooks, "emit", lambda *a, **k: None)
    monkeypatch.setattr(whatsapp, "notify", lambda *a, **k: None)
    return raised


def test_one_chat_raises_one_alert_until_a_phone_number_is_given() -> None:
    assert alerts.first_time("s1", False) is True
    assert alerts.first_time("s1", False) is False
    assert alerts.first_time("s2", False) is True  # another chat
    assert alerts.first_time("s1", True) is True  # now there is someone to call
    assert alerts.first_time("s1", True) is False


def test_the_email_names_the_lead_but_no_patient_details() -> None:
    subject, text = alerts.emergency_email("Neo", "CL99-0001")
    assert "Neo" in subject and "CL99-0001" in text and "/inbox?tab=callback" in text
    _, none = alerts.emergency_email("Neo", None)
    assert "did not give a phone number" in none and "/inbox" not in none


@needs_db
async def test_only_active_managers_of_this_clinic_are_emailed(tx: asyncpg.Connection) -> None:
    await person(tx, "alert_mgr", "CL99", "clinic_manager")
    await person(tx, "alert_off", "CL99", "clinic_manager", active=False)
    await person(tx, "alert_desk", "CL99", "front_desk")
    await tx.execute(
        """insert into app.clinics (id, name, bot_name, open_time, close_time, is_test)
           values ('CL98', 'Test Clinic 2', 'Test2 AI', '10:00', '19:00', true) on conflict do nothing"""
    )
    await person(tx, "alert_other", "CL98", "clinic_manager")
    to = await alerts.managers(tx, "CL99")
    assert "alert_mgr@test.invalid" in to
    assert not {"alert_off@test.invalid", "alert_desk@test.invalid", "alert_other@test.invalid"} & set(to)


@needs_db
async def test_clinic_settings_choose_who_is_emailed(tx: asyncpg.Connection) -> None:
    await person(tx, "alert_mgr2", "CL99", "clinic_manager")
    assert "alert_mgr2@test.invalid" in await alerts.recipients(tx, "CL99")  # nothing saved: the Admins
    await tx.execute(
        """insert into app.clinic_alerts (clinic_id, emergency_admins, emergency_emails)
           values ('CL99', true, '{desk@test.invalid}')"""
    )
    both = await alerts.recipients(tx, "CL99")
    assert "alert_mgr2@test.invalid" in both and both[-1] == "desk@test.invalid"
    await tx.execute("update app.clinic_alerts set emergency_admins = false where clinic_id = 'CL99'")
    assert await alerts.recipients(tx, "CL99") == ["desk@test.invalid"]


async def test_one_managers_failed_email_does_not_stop_the_next(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    async def send(clinic: str, to: str, subject: str, text: str, kind: str) -> None:
        sent.append(to)
        assert kind == "emergency_alert"
        raise email.EmailError("Gmail refused")

    class Conn:
        async def __aenter__(self) -> "Conn":
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def fetchval(self, *_: Any) -> str:
            return "Neo"

    class Pool:
        def acquire(self) -> Conn:
            return Conn()

    async def pool() -> Pool:
        return Pool()

    async def two(*_: Any) -> list[str]:
        return ["a@test.invalid", "b@test.invalid"]

    monkeypatch.setattr(alerts, "get_pool", pool)
    monkeypatch.setattr(alerts, "recipients", two)
    monkeypatch.setattr(email, "send", send)
    await alerts._send("CL99", None)
    assert sent == ["a@test.invalid", "b@test.invalid"]


async def _request(db: asyncpg.Connection) -> Any:
    return await db.fetchrow(
        f"{SELECT} where r.session_id = $1 order by r.created_at desc limit 1", req().session_id
    )


@needs_db
async def test_classic_chat_with_a_phone_makes_an_urgent_call_back(
    tx: asyncpg.Connection, quiet: list[tuple[str, str | None]]
) -> None:
    await store.open_session(tx, req())
    state = {"flow": {"kind": "book", "step": "date", "name": "Asha Rao", "phone": PHONE}}
    typed = req("text", text="there is heavy bleeding")
    await service.raise_emergency(tx, typed, state)
    row = await _request(tx)
    item = _item(row)
    assert item.urgent is True and item.type == "callback" and item.status == "pending"
    assert item.reason == "EMERGENCY in chat: there is heavy bleeding"
    assert quiet == [("CL99", item.lead_code)]
    await service.raise_emergency(tx, typed, state)  # the same words again
    assert len(quiet) == 1
    count = await tx.fetchval("select count(*) from app.requests where session_id = $1", typed.session_id)
    assert count == 1


@needs_db
async def test_classic_chat_without_a_phone_still_emails(
    tx: asyncpg.Connection, quiet: list[tuple[str, str | None]]
) -> None:
    await store.open_session(tx, req())
    await service.raise_emergency(tx, req("text", text="chest pain"), {})
    assert quiet == [("CL99", None)]
    assert await _request(tx) is None
    shown = await tx.fetchval(
        "select severity from app.notifications where dedupe_key = $1", f"emergency:{req().session_id}"
    )
    assert shown == "urgent"  # in the bell, with no request behind it


@needs_db
async def test_canvas_keeps_the_urgent_flag(tx: asyncpg.Connection) -> None:
    await store.open_session(tx, req())
    await canvas._save(
        tx, req(), {"type": "callback", "name": "Patient (emergency)", "phone": PHONE, "urgent": True}
    )
    assert _item(await _request(tx)).urgent is True


@needs_db
async def test_a_normal_request_is_not_urgent(tx: asyncpg.Connection) -> None:
    await store.open_session(tx, req())
    f = {"kind": "callback", "name": "Asha Rao", "phone": PHONE}
    await leads.save_completed(tx, req(), f)
    row = await _request(tx)
    data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
    assert "urgent" not in data and _item(row).urgent is False
