"""C1: the bot reads the conversation so far (last messages, topic, its own last reply) before deciding.
The turn runs as in the service (no database, no knowledge base)."""

from typing import Any

import pytest

from app.chat import context, engine, store, understand
from app.chat.content import content
from app.chat.schemas import ChatRequest
from tests.test_chat_store import req as store_req


def _content() -> dict[str, Any]:
    c = content("NFHT")
    assert c is not None
    return c


C = _content()


class Chat:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}

    def send(self, event: str, **payload: Any) -> str:
        req = ChatRequest.model_validate(
            {"client_id": "NFHT", "session_id": "s_" + "a" * 32, "visitor_id": "v_" + "b" * 32,
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
        {"client_id": "NFHT", "session_id": "s_" + "a" * 32, "visitor_id": "v_" + "b" * 32, "event": "text",
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


@pytest.mark.parametrize(
    "text", ["laser hair removal", "do you do botox", "acne treatment", "teeth cleaning"]
)
def test_a_service_the_clinic_does_not_offer_gets_a_clear_reply(text: str) -> None:
    c = Chat()
    assert c.type(text) == engine.NOT_OFFERED and c.state["pending_q"] == text
    assert "Fertility" not in engine.NOT_OFFERED and "Derma" not in engine.NOT_OFFERED  # never another clinic


@pytest.mark.parametrize(
    ("text", "node"),
    [("bald patch at the crown, price?", "cost_crown"),
     ("i have very little hair left, cost?", "cost_advanced"),
     ("my hairline has moved back, what will it cost", "cost_receding"),
     ("front and crown both are thin, cost?", "cost_front_crown"), ("beard transplant cost", "cost_beard"),
     ("how much does a hair transplant cost", "cost")],
)  # fmt: skip
def test_cost_for_a_named_pattern_opens_that_cost_option(text: str, node: str) -> None:
    assert understand.route(text, C) == ("node", node)


def test_naming_a_treatment_opens_its_card_but_a_question_gets_the_answer() -> None:
    def respond(text: str) -> engine.Turn:
        return engine.respond(store_req("text", clinic="NFHT", text=text), {}, None, "Approved answer.")

    assert respond("fue hair transplant").reply.messages[0].text.startswith("**Direct Hair Transplant")
    assert respond("qr678 sessions needed").answered_by == "kb"
    assert respond("what is fue").answered_by == "kb"


@pytest.mark.parametrize(
    ("text", "first"),
    [("reviews", "Venkat A."), ("what do patients say about you", "Venkat A."), ("gfc reviews", "Satya R."),
     ("reviews from international patients", "Azhar K."), ("google rating?", "Venkat A.")],
)  # fmt: skip
def test_reviews_show_the_rating_and_three_fitting_quotes(text: str, first: str) -> None:
    c = Chat()
    c.type(text)
    texts = [m.text for m in c.reply.messages]
    assert texts[0].startswith("Neo Follicle Hair Transplant is rated **4.8") and len(texts) == 4
    assert texts[1].endswith(first)
    links = [o.get("href") for o in c.reply.ui["options"]]  # type: ignore[index]
    assert C["reviews"]["link"] in links


def test_follow_up_reviews_after_a_procedure_are_not_google_reviews() -> None:
    assert not understand.REVIEWS.search("do you have follow-up reviews after surgery")


@pytest.mark.parametrize(
    "text", ["is the clinic open on tuesday", "where is the clinic", "which area is the clinic in"]
)
def test_questions_about_the_clinic_are_not_reviews(text: str) -> None:
    assert not understand.REVIEWS.search(text)


def test_canvas_reads_the_last_messages_for_a_follow_up() -> None:
    from app.chat.context import TURNS, follow_up, keep

    h = keep([], "What are your clinic timings?", "We are open 10 AM to 7 PM.")
    assert follow_up("and sunday?", h) == "What are your clinic timings? sunday"
    assert follow_up("tell me more", h) == "What are your clinic timings?"
    assert follow_up("ok", h) is None and follow_up("thanks", h) is None  # small talk is not a follow-up
    assert follow_up("Do you have parking in the basement near the lift area?", h) is None  # stands alone
    assert follow_up("consultation fee", h) is None  # names its own subject: read on its own
    assert follow_up("how much is it?", h) == "What are your clinic timings?"  # no subject: the last one
    assert follow_up("and sunday?", []) is None  # nothing came before
    for i in range(5):
        h = keep(h, f"question {i}", f"answer {i}")
    assert len(h) == TURNS and h[-2]["text"] == "question 4"  # the last 3 each way
