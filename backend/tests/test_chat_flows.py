"""Flows (B3b), word for word with frontend.md. Fixed clock: Wednesday 21 Oct 2026, 09:00 India time."""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.chat import engine, flows
from app.chat.schemas import ChatRequest


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(flows, "clock", lambda: datetime(2026, 10, 21, 3, 30, tzinfo=UTC))


class Chat:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}

    def send(self, event: str, **payload: Any) -> str:
        req = ChatRequest.model_validate(
            {
                "client_id": "CL01",
                "session_id": "s_" + "a" * 32,
                "visitor_id": "v_" + "b" * 32,
                "event": event,
                "payload": payload,
                "context": {
                    "page_url": "https://neofollicletransplant.com/",
                    "device": "desktop",
                    "lang": "en",
                },
            }
        )
        turn = engine.respond(req, self.state)
        self.state = turn.state
        self.last = turn.reply
        return " | ".join(m.text for m in turn.reply.messages)

    def tap(self, action: str, value: str | None = None) -> str:
        return self.send("button", action=action, value=value)

    def type(self, text: str, cc: str | None = None) -> str:
        return self.send("text", text=text, cc=cc)


def test_in_clinic_booking_with_the_invalid_inputs() -> None:
    c = Chat()
    assert c.tap("start", "book") == "Sure, let's book your appointment. May I know your full name?"
    assert c.type("P") == "Please enter your full name."
    assert c.type("Priya Sharma") == "Thanks, Priya. What is your contact number?"
    assert c.last.input.mode == "phone"
    assert c.type("12345") == "That number does not look right. Please check and enter it again."
    assert c.type("9876543210") == "What is your email address?"
    assert c.type("priya@") == "Please enter a valid email address."
    assert c.type("priya@example.com") == "Which treatment are you looking for?"
    assert c.tap("treatment", "Hair Transplant for Men") == "Which date works for you?"
    cal = c.last.ui or {}
    assert (cal["min"], cal["max"], cal["closed_weekdays"]) == ("2026-10-21", "2026-11-04", [2])
    assert c.tap("date", "2026-10-27") == (  # a Tuesday: asked again, saying why
        "That date is not available. Please choose another date. | Which date works for you?"
    )
    assert c.tap("date", "2026-10-23") == "What time would you prefer?"
    assert (c.last.ui or {})["slots"][:2] == ["10:00", "10:15"]
    assert c.tap("time", "20:00") == (  # not a slot: asked again, saying why
        "That time is not available. Please choose one of the times shown. | What time would you prefer?"
    )
    summary = c.tap("time", "10:30")
    assert "Hair Transplant for Men" in summary and "23 Oct 2026 at 10:30 AM" in summary
    assert c.tap("confirm") == (
        "Your appointment request for **Hair Transplant for Men** on 23 Oct 2026 at 10:30 AM is received."
    )
    assert "flow" not in c.state  # the flow has ended


def test_online_with_other_reason_any_time_and_switch() -> None:
    c = Chat()
    c.tap("start", "online")
    for t in ["Priya Sharma", "9876543210", "priya@example.com"]:
        c.type(t)
    assert c.tap("treatment", "Other") == "Please tell us briefly what you are looking for."
    assert c.type("Hi") == "Please add a few more words."
    assert c.type("Hairline correction") == "Which date works for you?"
    c.tap("date", "2026-10-24")
    assert "24 Oct 2026, any time" in c.tap("time", "any")
    assert "In-clinic visit" in c.tap("switch_inclinic")
    assert (
        c.tap("confirm")
        == "Your appointment request for **Hairline correction** on 24 Oct 2026 (any time) is received."
    )


def test_book_for_preselects_and_skips_the_treatment_step() -> None:
    c = Chat()
    c.tap("book_for", "PRP Treatment")
    for t in ["Priya Sharma", "9876543210"]:
        c.type(t)
    assert c.type("priya@example.com") == "Which date works for you?"
    c.tap("date", "2026-10-23")
    assert "Non-Surgical Treatment (GFC, PRP, QR678)" in c.tap("time", "10:00")


def test_cancel_and_reschedule() -> None:
    c = Chat()
    c.tap("start", "cancel")
    c.type("Priya Sharma")
    assert c.type("9876543210") == "Which date is your appointment booked for?"  # no email step
    assert c.tap("booked_date", "2026-08-21") == "Which date is your appointment booked for?"  # over 2 months
    assert c.tap("booked_date", "2026-10-02") == (
        "Thanks, Priya. Your request to cancel the appointment on **2 Oct 2026** is received. "
        "Our team will contact you on +91 9876543210 to confirm the cancellation."
    )
    r = Chat()
    r.tap("start", "reschedule")
    r.type("Priya Sharma")
    r.type("9876543210")
    assert r.tap("booked_date", "2026-10-02") == "Which new date would you prefer?"
    assert r.tap("date", "2026-10-28") == "And what new time would you prefer?"
    assert r.tap("time", "10:00") == (
        "Thanks, Priya. Your request to move your appointment from **2 Oct 2026** to **28 Oct 2026 at 10:00 AM** "
        "is received. Our team will contact you on +91 9876543210 to confirm the new slot."
    )


def test_callback_with_topic_and_question_lead() -> None:
    c = Chat()
    c.tap("callback", "International patient")
    c.type("Omar Khan")
    assert c.type("501234567", cc="+971") == (
        "Thanks, Omar. Our team will call you on +971 501234567 about **International patient** during clinic hours."
    )
    q = Chat()
    assert q.type("Do you have parking?") == engine.NO_ANSWER  # asked first: the form starts only on yes
    assert q.state["pending_q"] == "Do you have parking?"
    assert q.type("yes") == "May I know your full name?"
    assert q.state["flow"]["reason"] == "Do you have parking?"
    q.type("Priya Sharma")
    q.type("9876543210")
    assert q.type("priya@example.com") == "Thanks, Priya. Our team will contact you on +91 9876543210."


def test_a_date_tap_never_moves_a_callback_into_booking() -> None:
    c = Chat()
    c.tap("start", "callback")
    c.type("Rahul Verma")
    assert c.tap("date", "2026-10-23") == "Thanks, Rahul. What is your contact number?"  # asked again
    assert c.tap("confirm") == "Thanks, Rahul. What is your contact number?"
