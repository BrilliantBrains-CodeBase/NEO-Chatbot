"""Running a canvas flow (app.crm.flow_run): taps and typed text, questions, logic, live data, triggers."""

from datetime import date
from typing import Any

from app.chat.content import content
from app.crm.flow import import_content, normalise
from app.crm.flow_run import Context, run_checks, send, start

FUE = {"name": "FUE", "category": "Hair transplant", "show": True, "price": 50000, "show_price": True}
WED = date(2026, 10, 28)  # a Wednesday


def ctx(**more: Any) -> Context:
    return Context(today=WED, minutes=11 * 60, services=[FUE], **more)


def line(source: str, exit_: str, target: str) -> dict[str, str]:
    return {"source": source, "exit": exit_, "target": target}


def opening(*buttons: tuple[str, str]) -> dict[str, Any]:
    return {
        "id": "opening",
        "type": "opening",
        "settings": {"welcome": "Hi!", "buttons": [{"id": i, "label": label} for i, label in buttons]},
    }


class Chat:
    """A patient: each message returns the bot's texts; .at is the block the chat is on."""

    def __init__(self, flow: dict[str, Any], c: Context | None = None) -> None:
        self.flow, self.ctx = normalise(flow), c or ctx()
        self.r = start(self.flow, self.ctx)

    def __call__(self, text: str | None = None, tap: str | None = None) -> list[str]:
        self.r = send(self.flow, self.ctx, self.r["state"], tap=tap, text=text)
        return [m["text"] for m in self.r["messages"]]

    @property
    def at(self) -> str | None:
        at: str | None = self.r["at"]
        return at

    def labels(self) -> list[str]:
        return [b["label"] for m in self.r["messages"] for b in m.get("buttons", [])]


def test_cl01_imported_flow_opens_and_follows_taps_and_typos() -> None:
    chat = Chat(import_content(content("CL01") or {}))
    assert chat.r["messages"][0]["text"].startswith("Hi, I'm Arya")
    chat(tap="m2")  # Explore Treatments
    assert chat.at != "opening" and chat.labels()
    chat("main menu")  # a global trigger, from anywhere
    assert chat.at == "opening"
    chat("explore treatmnts")  # a typo still finds the button
    assert chat.at != "opening"


def test_booking_step_by_step_with_a_wrong_answer_and_consent() -> None:
    book = {"id": "book", "type": "book", "settings": {"fields": ["name", "phone", "date"]}}
    done = {"id": "thanks", "type": "answer", "settings": {"text": "See you, {name}!"}}
    chat = Chat(
        {
            "nodes": [opening(("m1", "Book")), book, done],
            "edges": [line("opening", "m1", "book"), line("book", "done", "thanks")],
        }
    )
    assert chat("book") == ["May I know your full name?"]
    assert chat("Asha Rao") == ["Thanks, Asha Rao. What is your contact number?"]
    assert "valid phone" in chat("12345")[0]  # asked again
    chat("98765 43210")
    chat("tomorrow")
    assert chat.labels() == ["Yes", "No"]  # consent
    texts = chat(tap="yes")
    assert chat.r["lead"] == {
        "type": "book",
        "block": "book",
        "name": "Asha Rao",
        "phone": "+91 9876543210",
        "date": "2026-10-29",
    }
    assert texts[-1] == "See you, Asha Rao!" and chat.at == "thanks"


def test_too_many_wrong_answers_offer_a_call_back() -> None:
    book = {"id": "book", "type": "book", "settings": {"fields": ["phone"], "retries": 1}}
    cb = {"id": "cb", "type": "callback", "settings": {"fields": ["name"]}}
    chat = Chat({"nodes": [opening(("m1", "Book")), book, cb], "edges": [line("opening", "m1", "book")]})
    chat(tap="m1")
    chat("abc")
    texts = chat("abc")
    assert chat.at == "cb" and "call back" in texts[0]


def test_question_yes_no_choice_and_fields_in_messages() -> None:
    q1 = {
        "id": "q1",
        "type": "question",
        "settings": {"question": "Had a transplant before?", "kind": "yes_no", "field": "reason"},
    }
    opts = [{"label": "Crown"}, {"label": "Hairline"}]
    q2 = {
        "id": "q2",
        "type": "question",
        "settings": {"question": "Which area?", "kind": "choice", "field": "area", "options": opts},
    }
    end = {"id": "end", "type": "answer", "settings": {"text": "Noted: {area}."}}
    flow = {
        "nodes": [opening(("m1", "Start")), q1, q2, end],
        "edges": [line("opening", "m1", "q1"), line("q1", "no", "q2"), line("q2", "next", "end")],
        "fields": [{"key": "area", "label": "Area"}],
    }
    chat = Chat(flow)
    chat(tap="m1")
    assert chat.labels() == ["Yes", "No"]
    chat(tap="no")
    assert chat.at == "q2"
    assert chat("hairlne") == ["Noted: Hairline."]  # typed, with a typo


def test_logic_condition_clinic_open_set_field_goto() -> None:
    weekend = {
        "id": "c1",
        "label": "Weekend",
        "tests": [{"subject": "weekday", "op": "is", "value": "sat,sun"}],
    }
    nodes = [
        opening(("m1", "Go")),
        {"id": "if", "type": "condition", "settings": {"branches": [weekend]}},
        {"id": "set", "type": "set_field", "settings": {"field": "reason", "value": "weekday visit"}},
        {"id": "open", "type": "clinic_open", "settings": {}},
        {"id": "go", "type": "goto", "settings": {"target": "closed"}},
        {"id": "yes", "type": "answer", "settings": {"text": "Open: {reason}"}},
        {"id": "closed", "type": "answer", "settings": {"text": "Closed now: {reason}"}},
    ]
    edges = [
        line("opening", "m1", "if"),
        line("if", "else", "set"),
        line("set", "next", "open"),
        line("open", "open", "yes"),
        line("open", "closed", "go"),
    ]
    assert Chat({"nodes": nodes, "edges": edges})(tap="m1") == ["Open: weekday visit"]
    closed = ctx(open_now={"in_clinic": False, "online": True})
    assert Chat({"nodes": nodes, "edges": edges}, closed)(tap="m1") == ["Closed now: weekday visit"]


def test_live_treatments_card_and_book_skips_the_treatment_question() -> None:
    tl = {
        "id": "tl",
        "type": "treatment_list",
        "settings": {"message": "Pick one", "category": "Hair transplant"},
    }
    book = {"id": "book", "type": "book", "settings": {"fields": ["treatment", "name"]}}
    chat = Chat({"nodes": [opening(("m1", "Treatments")), tl, book], "edges": [line("opening", "m1", "tl")]})
    chat(tap="m1")
    assert chat.labels() == ["FUE"]  # live from Services
    assert chat(tap="t:FUE")[0].startswith("FUE\nFrom ₹50,000")
    assert chat(tap="book:FUE") == ["May I know your full name?"]  # treatment already known


def test_off_blocks_hide_their_buttons_and_global_emergency() -> None:
    off = {"id": "off", "type": "answer", "enabled": False, "settings": {"text": "Hidden"}}
    sos = {
        "id": "sos",
        "type": "emergency",
        "settings": {
            "text": "Call 108 now.",
            "buttons": [{"id": "b1", "label": "Call 108", "action": "call", "value": "108"}],
        },
    }
    flow = {
        "nodes": [
            opening(("m1", "Offer"), ("m2", "Other")),
            off,
            sos,
            {"id": "o", "type": "answer", "settings": {"text": "Other"}},
        ],
        "edges": [line("opening", "m1", "off"), line("opening", "m2", "o")],
        "globals": {"triggers": [{"kind": "emergency", "target": "sos"}]},
    }
    chat = Chat(flow)
    assert chat.labels() == ["Other"]  # the button to the off block is hidden
    assert chat("there is heavy bleeding") == ["Call 108 now."] and chat.labels() == ["Call 108"]


def test_knowledge_base_and_check_my_appointment() -> None:
    kb = {"id": "kb", "type": "knowledge", "settings": {}}
    chk = {"id": "chk", "type": "check_appointment", "settings": {}}
    found = {"id": "f", "type": "answer", "settings": {"text": "Anything else?"}}
    lost = {"id": "nf", "type": "callback", "settings": {"fields": ["name"]}}
    edges = [
        line("opening", "m1", "kb"),
        line("opening", "m2", "chk"),
        line("kb", "answered", "f"),
        line("kb", "not_found", "nf"),
        line("chk", "found", "f"),
    ]
    flow = {"nodes": [opening(("m1", "Ask"), ("m2", "My appointment")), kb, chk, found, lost], "edges": edges}
    c = ctx(
        kb=lambda q: "We are open 10 to 7." if "timing" in q else None,
        appointments=lambda p: ["Thu 29 Oct, 11:00 AM"],
    )
    chat = Chat(flow, c)
    chat(tap="m1")
    assert chat("clinic timings?") == ["We are open 10 to 7.", "Anything else?"]
    chat("menu")
    chat(tap="m1")
    chat("parking?")
    assert chat.at == "nf"  # not found → call back
    chat("menu")
    chat(tap="m2")
    assert chat("9876543210") == ["Thu 29 Oct, 11:00 AM", "Anything else?"]


def test_publish_checks_replay_saved_test_chats() -> None:
    book = {"id": "book", "type": "book", "settings": {"fields": ["name", "phone"]}}
    done = {"id": "thanks", "type": "answer", "settings": {"text": "Thanks!"}}
    steps = [{"tap": "m1"}, {"text": "Asha Rao"}, {"text": "9876543210"}, {"tap": "yes"}]
    check = {"name": "Booking works", "steps": steps, "expect_at": "thanks", "expect_lead": True}
    edges = [line("opening", "m1", "book"), line("book", "done", "thanks")]
    flow = normalise({"nodes": [opening(("m1", "Book")), book, done], "edges": edges, "checks": [check]})
    assert flow["checks"][0]["name"] == "Booking works"  # kept with the flow
    assert run_checks(flow, ctx()) == [{"name": "Booking works", "ok": True, "message": ""}]
    broken = flow | {"edges": edges[:1]}  # the line after the booking was removed
    [result] = run_checks(broken, ctx())
    assert not result["ok"] and "expected 'thanks'" in result["message"]
    unfinished = flow | {"checks": [check | {"steps": steps[:2], "expect_at": "book"}]}
    assert run_checks(unfinished, ctx())[0]["message"] == "the booking / call back was not finished"


def test_medical_questions_are_never_answered() -> None:
    kb = {"id": "kb", "type": "knowledge", "settings": {}}
    cb = {"id": "cb", "type": "callback", "settings": {"fields": ["name", "reason"]}}
    flow = {"nodes": [opening(("m1", "Ask")), kb, cb], "edges": [line("opening", "m1", "kb")]}
    chat = Chat(flow, ctx(kb=lambda q: "Take two tablets."))  # even a Knowledge base answer is not given
    chat(tap="m1")
    texts = chat("which tablets should I take after the transplant?")
    assert texts[0].startswith("I don't have a confirmed answer") and "Take two" not in " ".join(texts)
    assert chat.labels() == ["Yes, call me back", "No, thanks"]
    assert chat(tap="medical:yes") == ["May I know your full name?"]  # the reason is already known
    assert chat.r["state"]["fields"]["reason"].startswith("which tablets")
    chat("Asha Rao")
    assert chat.labels() == ["Yes", "No"]  # consent next: the reason was not asked again
    chat(tap="yes")
    assert chat.r["lead"]["reason"].startswith("which tablets")


def test_booking_offers_and_checks_live_free_slots() -> None:
    book = {"id": "book", "type": "book", "settings": {"fields": ["date", "time"], "consent": False}}
    free = {"in_clinic": {"2026-10-29": ["11:00", "11:15"]}, "online": {}}
    chat = Chat(
        {"nodes": [opening(("m1", "Book")), book], "edges": [line("opening", "m1", "book")]}, ctx(slots=free)
    )
    chat(tap="m1")
    assert chat.labels() == ["Thu 29 Oct"]  # only days with a free time
    assert "no free times on Fri 30 Oct" in chat("30 oct")[0]  # typed, not free: asked again
    chat(tap="2026-10-29")
    assert chat.labels() == ["11:00 AM", "11:15 AM", "Any time"]
    assert "11:30 AM is not free" in chat("11:30 am")[0]
    chat("11:15")
    assert chat.r["lead"] == {"type": "book", "block": "book", "date": "2026-10-29", "time": "11:15"}
    online = Chat(
        {
            "nodes": [opening(("m1", "Online")), book | {"id": "on", "type": "online"}],
            "edges": [line("opening", "m1", "on")],
        },
        ctx(slots=free),
    )
    online(tap="m1")
    assert online.labels() == []  # no free online time in the window: nothing to tap


def test_approved_phrases_lead_to_their_buttons() -> None:
    menu = {
        "id": "menu",
        "type": "choice",
        "settings": {"message": "Pick", "buttons": [{"id": "b1", "label": "Cost"}]},
    }
    cost = {"id": "cost", "type": "answer", "settings": {"text": "From ₹60 a graft."}}
    book = {"id": "book", "type": "book", "settings": {"fields": ["name"]}}
    timing = {"id": "t", "type": "typed", "settings": {"topic": "timing"}}
    hours = {"id": "hours", "type": "answer", "settings": {"text": "10 to 7."}}
    edges = [
        line("opening", "m1", "book"),
        line("opening", "m2", "menu"),
        line("menu", "b1", "cost"),
        line("t", "next", "hours"),
    ]
    phrases = [
        {"id": "p1", "target": "opening:m1", "text": "I want to book", "status": "approved"},
        {"id": "p2", "target": "menu:b1", "text": "how much does it cost", "status": "approved"},
        {"id": "p3", "target": "t", "text": "when are you open", "status": "approved"},
        {"id": "p4", "target": "opening:m1", "text": "kab aa sakta hoon", "status": "pending"},
    ]
    flow = {
        "nodes": [opening(("m1", "Book"), ("m2", "More")), menu, cost, book, timing, hours],
        "edges": edges,
        "phrases": phrases,
    }

    def fresh(**more: Any) -> Chat:
        chat = Chat(flow, ctx(**more))
        # approval is the API's job (a save sets pending); here the phrases are set as approved directly
        chat.flow["phrases"] = phrases
        return chat

    chat = fresh()
    assert chat("i want to bok") == ["May I know your full name?"]  # an approved phrase, with a typo
    assert chat.r["matched"] == {"how": "typo", "text": "I want to book"}
    chat = fresh()
    assert chat("hi, how much does it cost for me") == ["From ₹60 a graft."]  # another screen's button
    assert chat.r["matched"]["how"] == "phrase in message"
    chat = fresh()
    assert chat("when are you open") == ["10 to 7."]  # a Typed trigger
    chat = fresh()
    assert chat("kab aa sakta hoon")[0].startswith("Sorry")  # pending: never used
    near = {"target": "opening:m1", "text": "I want to book", "score": 88.0}
    chat = fresh(meaning=lambda t: near)
    assert chat("can i come in next week") == ["May I know your full name?"]  # by meaning
    assert chat.r["matched"] == {"how": "meaning", "text": "I want to book", "score": 88.0}


def test_typed_text_beside_the_flow() -> None:
    book = {"id": "book", "type": "book", "settings": {"fields": ["name", "phone"]}}
    cancel = {"id": "cancel", "type": "cancel", "settings": {"fields": ["name"]}}
    menu = {
        "id": "menu",
        "type": "choice",
        "settings": {"message": "More", "buttons": [{"id": "b1", "label": "Deep"}]},
    }
    deep = {"id": "deep", "type": "answer", "settings": {"text": "Deep page"}}
    edges = [line("opening", "m1", "book"), line("opening", "m2", "menu"), line("menu", "b1", "deep")]
    flow = {"nodes": [opening(("m1", "Book"), ("m2", "More")), book, cancel, menu, deep], "edges": edges}
    kb = ctx(kb=lambda q: "We are open 10 to 7." if "open" in q else None)

    chat = Chat(flow, kb)
    assert chat("hello") == ["Hi!", "Hi!"]  # small talk: the welcome, with the screen again
    assert chat.labels() == ["Book", "More"]
    chat(tap="m1")
    assert chat("thanks") == [
        "You're welcome! Is there anything else I can help you with?",
        "May I know your full name?",
    ]
    chat("Asha Rao")
    texts = chat("when are you open?")  # a side question mid-booking: answered, then the same question
    assert texts == ["We are open 10 to 7.", "Thanks, Asha Rao. What is your contact number?"]
    assert chat("is it painful?")[0].startswith(
        "I don't have a confirmed answer"
    )  # medical: noted, never answered
    assert chat("actually I want to cancel my appointment") == [
        "Shall I stop this and help you cancel instead?"
    ]
    chat("no")
    assert chat.at == "book" and chat.r["messages"][-1]["text"].endswith("contact number?")  # carries on
    chat("cancel my booking")
    chat(tap="yes")
    assert chat.at == "cancel"

    chat = Chat(flow, kb)
    chat(tap="m2")
    chat(tap="b1")
    assert chat.at == "deep"
    chat("back")
    assert chat.at == "menu"
    chat("back")
    assert chat.at == "opening"

    chat = Chat(flow, kb)
    assert chat("tell me about fue")[0].startswith("FUE")  # a treatment typed by name: its card
    assert chat.r["matched"] == {"how": "treatment name", "text": "FUE"}


def test_test_set_scoring() -> None:
    from app.crm.flow_eval import passed

    book = {"id": "book", "type": "book", "settings": {"fields": ["name"]}}
    sos = {"id": "sos", "type": "emergency", "settings": {"text": "Call 108."}}
    flow = normalise(
        {"nodes": [opening(("m1", "Book")), book, sos], "edges": [line("opening", "m1", "book")]}
    )

    def score(message: str, expected: str, word: str = "") -> tuple[bool, str]:
        r = start(flow, ctx())
        return passed(flow, send(flow, ctx(), r["state"], text=message), expected, word)

    assert score("i want to book an appointment", "start", "book your appointment") == (True, "start")
    assert score("hello", "menu") == (True, "menu")
    assert score("there is heavy bleeding", "emergency") == (True, "emergency")
    assert score("which tablets should i take", "medical") == (True, "medical")
    assert score("blah blah", "any") == (False, "lead")
