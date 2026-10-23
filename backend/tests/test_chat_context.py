"""C1: the bot reads the conversation so far (last messages, topic, its own last reply) before deciding.
The turn runs as in the service (no database, no knowledge base)."""

from typing import Any

import pytest

from app.chat import context, engine, store, understand
from app.chat.content import content
from app.chat.schemas import ChatRequest


def _content() -> dict[str, Any]:
    c = content("CL01")
    assert c is not None
    return c


C = _content()


class Chat:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}

    def send(self, event: str, **payload: Any) -> str:
        req = ChatRequest.model_validate(
            {"client_id": "CL01", "session_id": "s_" + "a" * 32, "visitor_id": "v_" + "b" * 32,
             "event": event,
             "payload": payload, "context": {"page_url": "https://x.com/", "device": "desktop", "lang": "en"}}
        )  # fmt: skip
        said = store.patient_text(req, self.state)
        req = context.as_text(req)
        question = engine.asked(req, self.state)
        turn = engine.respond(req, self.state)
        turn.state["last_shown"] = turn.state["shown"] = engine.shown_choices(turn.reply.ui)
        bot = [m.text for m in turn.reply.messages]
        context.remember(self.state, turn.state, req, said, bot, turn.reply.ui, turn.answered_by, question, C)
        self.state, self.reply, self.by = turn.state, turn.reply, turn.answered_by
        return " | ".join(bot)

    def tap(self, action: str, value: str | None = None) -> str:
        return self.send("button", action=action, value=value)

    def type(self, text: str) -> str:
        return self.send("text", text=text)


@pytest.mark.parametrize(
    "text",
    ["I want more", "i want to know more", "tell me more", "Tell me more about it", "more please", "more?",
     "something else", "anything else?", "what else", "others", "explain", "aur batao", "details pls"],
)  # fmt: skip
def test_vague(text: str) -> None:
    assert context.is_vague(text)


@pytest.mark.parametrize(
    "text", ["I want more info on PRP", "more grafts", "tell me the cost", "other clinic"]
)
def test_not_vague(text: str) -> None:
    assert not context.is_vague(text)


@pytest.mark.parametrize(
    "text, state, want",
    [
        ("how long?", {"topic": "PRP Treatment"}, "how long? PRP Treatment"),
        ("cost", {"topic": "Beard Transplant"}, "cost Beard Transplant"),
        ("is it permanent", {"topic": "Hair Transplant for Men"}, "is it permanent Hair Transplant for Men"),
        ("kitna lagega", {"topic": "PRP Treatment"}, "kitna lagega PRP Treatment"),
        ("and for beard?", {"last_q": "cost of", "topic": "PRP Treatment"}, "cost of Beard Transplant"),
        ("what about eyebrows", {"last_q": "how long does take"}, "how long does take Eyebrow Restoration"),
        # unchanged: a general question, a treatment named, a full question, nothing before
        ("what time do you close", {"topic": "PRP Treatment"}, "what time do you close"),
        ("where is the clinic", {"topic": "PRP Treatment"}, "where is the clinic"),
        ("cost of beard transplant", {"topic": "PRP Treatment"}, "cost of beard transplant"),
        ("how long will the whole hair transplant procedure take for me", {"topic": "PRP Treatment"},
         "how long will the whole hair transplant procedure take for me"),
        ("how long?", {}, "how long?"),
        ("and for beard?", {}, "and for beard?"),
    ],
)  # fmt: skip
def test_resolve(text: str, state: dict[str, Any], want: str) -> None:
    assert context.resolve(text, state, C) == want


def test_more_after_a_list_shows_that_list_again() -> None:
    c = Chat()
    c.type("how much does it cost")  # a list of hair loss patterns
    cost_ui = c.reply.ui
    assert c.type("I want more") == engine.WHICH
    assert c.reply.ui == cost_ui


def test_more_after_the_treatment_list_shows_every_treatment() -> None:
    c = Chat()
    c.type("which treatments are there")
    treat_ui = c.reply.ui
    assert c.type("I want more").startswith("We offer 18 treatments:")
    assert c.reply.ui == treat_ui  # the same groups to tap
    assert c.type("Beard").startswith("**Beard Transplant**")  # its buttons still work by typing


def test_more_after_a_treatment_asks_what_about_it() -> None:
    c = Chat()
    c.tap("treat", "PRP Treatment")
    assert c.type("tell me more") == "What would you like to know about **PRP Treatment**?"
    labels = [o["label"] for o in c.reply.ui["options"]]  # type: ignore[index]
    assert labels == ["Cost", "Book for PRP Treatment", "Ask our team", "Read more on our website"]


def test_the_cost_button_asks_the_cost_of_the_topic() -> None:
    c = Chat()
    c.tap("treat", "PRP Treatment")
    c.type("tell me more")
    c.tap("ask", "cost of PRP Treatment")
    assert c.by == "rule"  # the cost answer, not a lead
    assert c.state["history"][-2] == {"who": "patient", "text": "Cost"}  # shown as the patient tapped it


def test_more_with_nothing_before_shows_the_menu() -> None:
    c = Chat()
    c.send("start")
    assert c.type("tell me more") == engine.WHICH  # the greeting's menu again
    assert Chat().type("tell me more") == engine.MAIN_MENU_TEXT


def test_more_about_an_old_topic_only_right_after_it() -> None:
    c = Chat()
    c.tap("treat", "PRP Treatment")
    c.type("where is the clinic")  # a new subject
    assert "PRP" not in c.type("tell me more")


def test_a_follow_up_detail_is_not_answered_with_the_card_again() -> None:
    c = Chat()
    c.tap("treat", "PRP Treatment")
    assert c.type("how long does it take?") == engine.NO_ANSWER  # no approved answer here: offer a call back
    assert c.state["pending_q"] == "how long does it take? PRP Treatment"  # the team sees what was meant
    assert c.type("yes") == "May I know your full name?"


def test_no_to_the_call_back_offer() -> None:
    c = Chat()
    c.type("do you have parking")
    assert c.type("no thanks") == engine.MAIN_MENU_TEXT  # typed, it taps the "No, thanks" button
    assert "pending_q" not in c.state
    c.type("do you have parking")
    assert c.type("nahi") == engine.STOPPED


def test_vague_inside_a_booking_asks_the_same_step() -> None:
    c = Chat()
    c.tap("start", "book")
    c.type("Asha Rao")
    c.type("9876543210")
    step = c.state["flow"]["step"]
    c.type("tell me more")
    assert c.state["flow"]["step"] == step


def test_a_name_in_a_form_is_never_read_as_a_follow_up() -> None:
    c = Chat()
    c.tap("treat", "PRP Treatment")
    c.tap("book_for", "PRP Treatment")
    c.type("Others")  # a (strange) name at the name step: taken as the name, not "show more"
    assert c.state["flow"]["step"] == "phone"


def test_history_keeps_the_last_five_messages_and_restart_forgets() -> None:
    c = Chat()
    for text in ("hi", "where is the clinic", "timings", "thanks"):
        c.type(text)
    assert len(c.state["history"]) == context.HISTORY
    assert c.state["history"][-1]["who"] == "bot"
    c.send("restart")
    assert "history" not in c.state and "topic" not in c.state


@pytest.mark.parametrize("text", ["clinic location", "what is the cost", "Book Now", "tell me more"])
def test_a_question_at_the_name_step_is_answered_and_the_name_asked_again(text: str) -> None:
    c = Chat()
    c.type("do you have parking")
    c.type("yes")
    c.type(text)
    assert c.state["flow"]["step"] == "name" and "name" not in c.state["flow"]


@pytest.mark.parametrize("name", ["Asha Rao", "Sandeep Kumar", "Mohammed Abid", "Priya"])
def test_real_names_are_still_names(name: str) -> None:
    c = Chat()
    c.type("do you have parking")
    c.type("yes")
    c.type(name)
    assert c.state["flow"]["step"] == "phone"


def test_a_knowledge_base_answer_shows_only_the_main_menu_link() -> None:
    req = ChatRequest.model_validate(
        {"client_id": "CL01", "session_id": "s_" + "a" * 32, "visitor_id": "v_" + "b" * 32, "event": "text",
         "payload": {"text": "clinic address"},
         "context": {"page_url": "https://x.com/", "device": "desktop", "lang": "en"}}
    )  # fmt: skip
    turn = engine.respond(req, {}, None, "We are at 1st floor, Scorpio House. Map: https://maps.app.goo.gl/x")
    assert turn.answered_by == "kb" and turn.reply.ui == engine.AFTER_ANSWER


@pytest.mark.parametrize(
    ("first", "then", "kind"),
    [("cancel my appointment", "reschudle my appointment", "reschedule"),
     ("reschedule my appointment", "no, i want to cancle it", "cancel"),
     ("call me back", "i want an online consultation", "online")],
)  # fmt: skip
def test_another_request_in_a_form_switches_to_it(first: str, then: str, kind: str) -> None:
    c = Chat()
    c.type(first)
    c.type(then)
    assert c.state["flow"]["kind"] == kind and c.state["flow"]["step"] == "name"


def test_a_name_is_still_a_name_and_cancer_is_not_cancel() -> None:
    c = Chat()
    c.type("cancel my appointment")
    c.type("Idress Khan")
    assert c.state["flow"]["kind"] == "cancel" and c.state["flow"]["step"] == "phone"
    assert understand.spelled("cancer treatment") == "cancer treatment"


@pytest.mark.parametrize(
    ("text", "treatment"),
    [("I want to book an appointment", None), ("book appointment", None), ("i need a slot", None),
     ("book for prp", "Non-Surgical Treatment (GFC, PRP, QR678)"),
     ("book beard transplant", "Beard Transplant")],
)  # fmt: skip
def test_a_booking_request_starts_the_booking_at_once(text: str, treatment: str | None) -> None:
    c = Chat()
    assert c.type(text) == "Sure, let's book your appointment. May I know your full name?"
    assert c.state["flow"]["kind"] == "book" and c.state["flow"]["treatment"] == treatment


def test_a_question_about_the_consultation_is_not_a_booking() -> None:
    c = Chat()
    c.type("what is included in the consultation")
    assert "flow" not in c.state


@pytest.mark.parametrize(
    ("first", "then"),
    [("what are the treatments", "only 4 or more ?"), ("what are the treatments", "is that all?"),
     ("which treatments are there", "more"), ("hi", "more treatments"), ("hi", "list of all your services")],
)  # fmt: skip
def test_asking_for_more_treatments_lists_every_one(first: str, then: str) -> None:
    c = Chat()
    c.type(first)
    reply = c.type(then)
    assert reply.startswith("We offer 18 treatments:")
    assert "PRP Treatment" in reply and "Eyebrow Restoration" in reply


def test_only_4_or_more_after_another_list_is_not_the_treatments() -> None:
    c = Chat()
    c.type("international patients")
    assert not c.type("only 4 or more?").startswith("We offer")
    assert Chat().type("all treatments cost").startswith("Hair transplant cost")  # cost, not the list
