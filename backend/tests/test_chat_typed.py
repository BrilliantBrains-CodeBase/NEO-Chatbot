"""Typing = tapping and the keyword rules (B4). Same cases as the widget mock tests (typing.spec.ts,
typed.spec.ts). Fixed clock: Wednesday 21 Oct 2026, 09:00 India time. No database."""

from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.chat import engine, flows, understand
from app.chat.content import content
from app.chat.schemas import ChatRequest
from tests.test_chat_store import req as store_req

TODAY = date(2026, 10, 21)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(flows, "clock", lambda: datetime(2026, 10, 21, 3, 30, tzinfo=UTC))


@pytest.mark.parametrize(
    "text, want",
    [
        ("today", "2026-10-21"), ("tomorrow", "2026-10-22"), ("Friday", "2026-10-23"), ("wed", "2026-10-21"),
        ("28 Oct", "2026-10-28"), ("28th October", "2026-10-28"), ("Oct 28", "2026-10-28"), ("28/10", "2026-10-28"),
        ("28-10-2026", "2026-10-28"), ("2026-10-28", "2026-10-28"), ("2 Jan", "2027-01-02"), ("31/2", None),
        ("hello", None),
    ],
)  # fmt: skip
def test_dates(text: str, want: str | None) -> None:
    assert understand.parse_date(text, TODAY) == want


@pytest.mark.parametrize(
    "text, want",
    [("10:30", "10:30"), ("10.30 am", "10:30"), ("2 pm", "14:00"), ("2:15pm", "14:15"), ("14:15", "14:15"),
     ("3", "15:00"), ("noon", "12:00"), ("any time", "any"), ("25:00", None), ("13 pm", None)],
)  # fmt: skip
def test_times(text: str, want: str | None) -> None:
    assert understand.parse_time(text) == want


@pytest.mark.parametrize(
    "text, want",
    [
        ("I am bleeding after my procedure", ("emergency", "")), ("I fainted", ("emergency", "")),
        ("Is minoxidil safe for me?", ("lead", "")), ("Will PRP be painful?", ("lead", "")),
        ("How much does it cost?", ("node", "cost")), ("Where is the clinic?", ("node", "clinic")),
        ("Can I do a video call from Dubai?", ("start", "online")), ("I need to cancel", ("start", "cancel")),
        ("Please postpone my visit", ("start", "reschedule")), ("Who is the doctor?", ("node", "about")),
        ("Tell me about PRP", ("card", "PRP Treatment")), ("What is SMP?", ("card", "Scalp Micropigmentation")),
        ("what treatments do you have", ("node", "treat")), ("Do you have parking?", ("lead", "")),
    ],
)  # fmt: skip
def test_rules(text: str, want: tuple[str, str]) -> None:
    c = content("CL01")
    assert c is not None
    assert understand.route(text, c) == want


class Chat:
    """Like the service: the state carries the flow and the latest buttons (last_shown)."""

    def __init__(self) -> None:
        self.state: dict[str, Any] = {}

    def type(self, text: str, event: str = "text") -> str:
        payload: dict[str, Any] = {"text": text} if event == "text" else {}
        req = ChatRequest.model_validate(
            {"client_id": "CL01", "session_id": "s_" + "a" * 32, "visitor_id": "v_" + "b" * 32, "event": event,
             "payload": payload,
             "context": {"page_url": "https://neofollicletransplant.com/", "device": "desktop", "lang": "en"}}
        )  # fmt: skip
        turn = engine.respond(req, self.state)
        self.state = {**turn.state, "last_shown": engine.shown_choices(turn.reply.ui)}
        return " | ".join(m.text for m in turn.reply.messages)


def test_a_whole_booking_typed_with_typos_and_short_labels() -> None:
    c = Chat()
    c.type("", "start")
    assert c.type("Book Consultation") == "What would you like to do?"
    assert "let's book your appointment" in c.type("in clinic")
    c.type("Priya Sharma")
    c.type("9876543210")
    c.type("priya@example.com")
    assert c.type("hair transplant for man") == "Which date works for you?"  # one-letter typo
    assert "That date is not available" in c.type("Tuesday")
    assert c.type("tomorrow") == "What time would you prefer?"
    assert "That time is not available" in c.type("8 pm")
    assert "22 Oct 2026 at 10:30 AM" in c.type("10:30")
    assert (
        c.type("yes")
        == "Your appointment request for **Hair Transplant for Men** on 22 Oct 2026 at 10:30 AM is received."
    )


def test_a_typed_name_never_taps_an_old_button() -> None:
    c = Chat()
    c.type("", "start")
    c.type("Book Consultation")
    c.type("in clinic")
    # "Online" was a button two replies ago; at the name step it is just a (too short) name.
    assert c.type("Online") == "Thanks, Online. What is your contact number?"


def test_questions_mid_booking_and_emergency() -> None:
    c = Chat()
    c.type("", "start")
    c.type("Book Consultation")
    c.type("in clinic")
    reply = c.type("where is the clinic?")
    assert "Scorpio House" in reply and reply.endswith("May I know your full name?")
    c.type("Priya Sharma")
    c.type("9876543210")
    assert c.type("Is PRP painful?") == (
        "I don't have a confirmed answer for that yet. I have noted your question for our team. | What is your email address?"
    )
    assert c.state["flow"]["questions"] == ["Is PRP painful?"]
    assert "call **108**" in c.type("I fainted")  # emergency takes over
    assert "flow" not in c.state


def test_main_menu_typed_anywhere_and_medical_without_a_flow() -> None:
    c = Chat()
    c.type("", "start")
    c.type("Book Consultation")
    assert c.type("main menu") == engine.MAIN_MENU_TEXT
    reply = c.type("Is minoxidil safe for me?")
    assert reply.startswith("I don't have a confirmed answer for that yet.") and reply.endswith(
        "May I know your full name?"
    )


@pytest.mark.parametrize("text", ["no", "No thanks", "skip", "not now", "nahi", "I don't want to share"])
def test_no_at_a_form_step_stops_the_form_and_saves_nothing(text: str) -> None:
    turn = engine.respond(_r(text), {"flow": {"kind": "question", "step": "name", "reason": "x"}})
    assert (
        turn.reply.messages[0].text == engine.STOPPED and "flow" not in turn.state and turn.completed is None
    )


def test_a_real_answer_or_no_inside_a_number_is_not_a_refusal() -> None:
    name = engine.respond(_r("Asha Rao"), {"flow": {"kind": "question", "step": "name"}})
    assert name.state["flow"]["step"] == "phone"
    phone = engine.respond(_r("no 98765"), {"flow": {"kind": "question", "step": "phone", "name": "A B"}})
    assert phone.state["flow"]["step"] == "phone"


@pytest.mark.parametrize("text", ["Who are you ?", "are you a bot", "what is your name", "Are you human?"])
def test_questions_about_the_bot_get_the_greeting(text: str) -> None:
    turn = engine.respond(_r(text), {})
    assert "I'm Arya" in turn.reply.messages[0].text and turn.answered_by == "rule"


def _r(text: str) -> ChatRequest:
    return store_req("text", clinic="CL01", text=text)
