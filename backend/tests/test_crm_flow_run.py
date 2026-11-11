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


def test_nfht_imported_flow_opens_and_follows_taps_and_typos() -> None:
    chat = Chat(import_content(content("NFHT") or {}))
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
    assert chat.labels() == ["Yes, that's correct", "Change details"]  # is this correct?
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
    assert chat.labels() == ["Yes, that's correct", "Change details"]  # the reason was not asked again
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
    assert chat("zxq soon please") == ["May I know your full name?"]  # by meaning (no rule, no answer)
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
    assert chat("hello") == ["Hi!"]  # small talk: the welcome once, the screen is not sent again
    assert chat.labels() == []  # the menu already on screen is not sent again
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


def test_helper_blocks_known_patient_follow_up_and_tag() -> None:
    nodes = [
        opening(("m1", "Book")),
        {"id": "tag", "type": "lead_tag", "settings": {"campaign": "Diwali offer"}},
        {"id": "known", "type": "known_patient", "settings": {}},
        {"id": "again", "type": "follow_up", "settings": {"fields": ["phone", "date"], "consent": False}},
        {"id": "new", "type": "book", "settings": {"fields": ["name"], "consent": False}},
    ]
    edges = [line("opening", "m1", "tag"), line("tag", "next", "known"), line("known", "known", "again")]
    edges.append(line("known", "new", "new"))
    flow = {"nodes": nodes, "edges": edges}
    chat = Chat(flow, ctx(returning=True))
    assert chat(tap="m1") == ["What is your contact number?"] and chat.at == "again"  # no "Thanks, ."
    chat("9876543210")
    chat("tomorrow")
    lead = chat.r["lead"]
    assert lead["type"] == "book" and lead["follow_up"] == "yes" and lead["campaign"] == "Diwali offer"
    new = Chat(flow, ctx(returning=False))
    new(tap="m1")
    assert new.at == "new"


def test_emergency_raises_a_staff_alert() -> None:
    sos = {"id": "sos", "type": "emergency", "settings": {"text": "Call 108 now."}}
    flow = {"nodes": [opening(("m1", "Hi")), sos]}
    chat = Chat(flow)
    chat("there is heavy bleeding")
    assert chat.r["alert"] == {"kind": "emergency", "said": "there is heavy bleeding", "phone": ""}
    quiet = Chat(flow | {"globals": {"emergency_alert": False}})
    quiet("there is heavy bleeding")
    assert quiet.at == "sos" and quiet.r["alert"] is None  # the alert is a setting; the reply is not


def test_booking_steps_like_the_live_chat() -> None:
    book = {"id": "book", "type": "book", "settings": {"fields": ["name", "phone", "treatment"]}}
    chat = Chat({"nodes": [opening(("m1", "Book")), book], "edges": [line("opening", "m1", "book")]},
                ctx(booking_options=["Hair Transplant for Men", "Not sure yet"]))  # fmt: skip
    chat(tap="m1")
    chat("Asha Rao")
    assert chat.r["messages"][0]["input"] == {"mode": "phone"}  # the country picker's box
    chat("+971 501234567")  # a UAE number from the picker
    assert chat.r["state"]["fields"]["phone"] == "+971 501234567"
    assert chat.labels() == ["Hair Transplant for Men", "Not sure yet"]  # the booking list
    texts = chat(tap="Not sure yet")
    assert (
        texts[0]
        == "Please check your details:\nName: Asha Rao\nPhone: +971 501234567\nTreatment: Not sure yet"
    )


def test_no_free_day_to_book_turns_into_a_call_back() -> None:
    """No free day in the window (e.g. no doctor yet): no dead end, the team calls back; the name and phone
    already given are not asked again."""
    book = {"id": "book", "type": "book", "settings": {"fields": ["name", "phone", "date", "time"]}}
    cb = {
        "id": "cb",
        "type": "callback",
        "settings": {"fields": ["name", "phone", "reason"], "consent": False},
    }
    chat = Chat(
        {"nodes": [opening(("m1", "Book")), book, cb], "edges": [line("opening", "m1", "book")]},
        ctx(slots={"in_clinic": {}, "online": {}}),
    )
    chat(tap="m1")
    assert "contact number" in chat("Asha Rao")[-1]  # the next question, in order
    said = chat("9800000123")
    assert "no free times to book online" in said[0] and chat.at == "cb"
    assert chat.r["lead"]["type"] == "callback" and chat.r["lead"]["reason"] == "Booking request"
    assert chat.r["lead"]["name"] == "Asha Rao"  # not asked again


def test_doctor_card_shows_today_and_books_a_free_time() -> None:
    card = {
        "id": "doc",
        "type": "doctor_card",
        "settings": {"doctor": "Dr. Asha", "title": "Consultant", "book_label": "Book with Dr. Asha"},
    }
    book = {
        "id": "book",
        "type": "book",
        "settings": {"fields": ["name", "date", "time"], "consent": False},
    }
    flow = {
        "nodes": [opening(("m1", "Doctors")), card, book],
        "edges": [line("opening", "m1", "doc"), line("doc", "book", "book")],
    }
    today = {
        "Dr. Asha": {
            "in_clinic": [("10:00", "13:00")], "online": [("18:00", "20:00")], "on_leave": False,
            "closed": False, "times": ["11:00", "11:10", "11:20"], "next": "2026-10-29",
        }
    }  # fmt: skip
    chat = Chat(flow, ctx(doctor_today=today))
    said = chat(tap="m1")
    assert "In the clinic today: 10:00 AM – 1:00 PM. Online today: 6:00 PM – 8:00 PM." in said[0]
    assert chat.labels()[:3] == ["11:00 AM", "11:10 AM", "11:20 AM"]
    assert chat(tap="slot:11:10") == ["May I know your full name?"]  # date and time are not asked
    chat("Asha Patient")
    assert chat.r["lead"] == {
        "type": "book", "block": "book", "name": "Asha Patient", "doctor": "Dr. Asha",
        "date": WED.isoformat(), "time": "11:10",
    }  # fmt: skip

    away = {"Dr. Asha": today["Dr. Asha"] | {"on_leave": True, "in_clinic": [], "online": [], "times": []}}
    chat = Chat(flow, ctx(doctor_today=away))
    assert "On leave today. Next free day: Thu 29 Oct." in chat(tap="m1")[0]
    assert not [x for x in chat.labels() if x.endswith("AM")]  # no times to tap


def test_a_knowledge_answer_on_the_main_menu_does_not_repeat_the_menu() -> None:
    flow = {"nodes": [opening(("m1", "Book"), ("m2", "Doctors"))], "edges": []}
    chat = Chat(flow, ctx(kb=lambda q: "Clinic email: info@example.com" if "email" in q else None))
    assert chat("email address") == ["Clinic email: info@example.com"]  # the answer only
    assert chat.labels() == []  # the menu already on screen is not shown again
    assert chat.at == "opening"  # and still works: a tile tap goes on as before


def test_an_answer_on_a_list_does_not_resend_it_and_the_clinic_screen_beats_a_fact() -> None:
    pick = {
        "id": "pick",
        "type": "choice",
        "settings": {
            "message": "Pick one",
            "buttons": [{"id": "b1", "label": "FUE"}, {"id": "b2", "label": "PRP"}],
        },
    }
    clinic = {
        "id": "page-clinic",
        "type": "answer",
        "settings": {"text": "1st floor, Example House. Map: link"},
    }
    flow = {
        "nodes": [opening(("m1", "Treatments"), ("m2", "Clinic")), pick, clinic],
        "edges": [
            line("opening", "m1", "pick"),
            line("opening", "m2", "page-clinic"),
            line("pick", "b1", "page-clinic"),
            line("pick", "b2", "page-clinic"),
        ],
    }
    city = "Bengaluru, Karnataka"
    chat = Chat(flow, ctx(kb=lambda q: city, kb_source="fact_meaning"))
    chat(tap="m1")
    assert chat.labels() == ["FUE", "PRP"]
    said = chat("send me the location")
    assert said == ["1st floor, Example House. Map: link"]  # the clinic screen beats a loose "city" fact
    via = Chat(flow, ctx(kb=lambda q: "Clinic email: info@example.com", kb_source="followup"))
    via(tap="m1")
    assert (
        via("where is the clinic")[0] == "1st floor, Example House. Map: link"
    )  # a follow-up never beats it
    email = Chat(flow, ctx(kb=lambda q: "Clinic email: info@example.com", kb_source="fact"))
    assert email("email address") == ["Clinic email: info@example.com"]  # by its words: the fact wins
    chat = Chat(flow, ctx(kb=lambda q: "Parking is free.", kb_source="fact"))
    chat(tap="m1")
    assert chat("is there parking") == ["Parking is free."]  # answered, and FUE / PRP are not sent again
    assert chat.labels() == [] and chat.at == "pick"
    written = Chat(flow, ctx(kb=lambda q: "Our address: 1st floor, Example House.", kb_source="qa"))
    written(tap="m1")
    assert written("where is the clinic located") == ["Our address: 1st floor, Example House."]  # a Q&A wins


def test_knowledge_base_only_answers_typed_questions_from_the_knowledge_base_alone() -> None:
    book = {"id": "book", "type": "book", "settings": {"fields": ["name"], "consent": False}}
    clinic = {"id": "page-clinic", "type": "answer", "settings": {"text": "Clinic screen"}}
    flow = {
        "nodes": [opening(("m1", "Book"), ("m2", "Clinic")), book, clinic],
        "edges": [line("opening", "m1", "book"), line("opening", "m2", "page-clinic")],
    }
    answers = {"where is the clinic": "We are at 1st floor, Example House."}
    chat = Chat(flow, ctx(kb=lambda q: answers.get(q), kb_only=True))
    assert chat("where is the clinic") == ["We are at 1st floor, Example House."]
    assert chat("clinic address please") == [
        "Sorry, I don't have an answer to that yet."
    ]  # no screen, no rule
    assert chat("Book") == ["Sorry, I don't have an answer to that yet."]  # typed: not taken as the button
    chat(tap="m1")  # buttons still work, and a booking question still takes its answer
    assert chat("Asha")[-1] == "Thank you, Asha. Our team will contact you shortly."


def test_answering_the_treatment_in_a_booking_does_not_skip_the_date() -> None:
    book = {
        "id": "book",
        "type": "book",
        "settings": {"fields": ["name", "treatment", "date", "time"], "consent": False},
    }
    free = {"in_clinic": {"2026-10-29": ["11:00", "11:15"]}, "online": {}}
    chat = Chat(
        {"nodes": [opening(("m1", "Book")), book], "edges": [line("opening", "m1", "book")]},
        ctx(slots=free, booking_options=["FUE", "PRP"]),
    )
    chat(tap="m1")
    chat("Asha")
    assert chat(tap="FUE") == ["Which date works for you?"]  # the date is asked, not skipped
    assert chat.labels() == ["Thu 29 Oct"]
    chat(tap="2026-10-29")
    assert chat.labels()[:2] == ["11:00 AM", "11:15 AM"]


def test_a_booking_choice_with_techniques_asks_which_one() -> None:
    book = {
        "id": "book",
        "type": "book",
        "settings": {"fields": ["name", "treatment", "date"], "consent": False},
    }
    free = {"in_clinic": {"2026-10-29": ["11:00"]}, "online": {}}
    techniques = {"Non-Surgical Treatment": ["PRP Treatment", "GFC Treatment", "QR678 Treatment"]}
    flow = {"nodes": [opening(("m1", "Book")), book], "edges": [line("opening", "m1", "book")]}
    c = ctx(slots=free, booking_options=["Hair Transplant", "Non-Surgical Treatment"], techniques=techniques)
    chat = Chat(flow, c)
    chat(tap="m1")
    chat("Asha")
    assert chat(tap="Non-Surgical Treatment") == ["Which treatment exactly?"]
    assert chat.labels() == ["PRP Treatment", "GFC Treatment", "QR678 Treatment", "Not sure"]
    assert chat(tap="GFC Treatment") == ["Which date works for you?"]
    chat(tap="2026-10-29")
    assert chat.r["lead"]["treatment"] == "GFC Treatment"  # the exact one is saved

    chat = Chat(flow, c)
    chat(tap="m1")
    chat("Asha")
    chat(tap="Non-Surgical Treatment")
    assert chat(tap="Not sure") == ["Which date works for you?"]
    chat(tap="2026-10-29")
    assert chat.r["lead"]["treatment"] == "Non-Surgical Treatment"  # not sure: the booking choice
    chat = Chat(flow, c)
    chat(tap="m1")
    chat("Asha")
    assert chat(tap="Hair Transplant") == ["Which date works for you?"]  # no techniques: straight on


def test_an_inbox_item_shows_the_name_typed_when_the_phone_has_another_lead() -> None:
    from datetime import UTC, datetime

    from app.api.v1.crm_inbox import _item

    row = {
        "id": "r1", "type": "book", "status": "pending", "created_at": datetime.now(UTC),
        "lead_code": "NFHT-00016", "full_name": "almas", "phone_e164": "+919875555552", "email": None,
        "data": {"name": "faz", "treatment": "FUE"}, "match_status": None, "a_id": None,
    }  # fmt: skip
    assert _item(row).name == "faz · existing lead almas (same phone)"
    row["data"] = {"name": "Almas"}
    assert _item(row).name == "almas"


def test_change_details_asks_which_and_the_next_request_starts_fresh() -> None:
    callback = {"id": "cb", "type": "callback", "settings": {"fields": ["name", "phone", "reason"]}}
    flow = {
        "nodes": [opening(("m1", "Call back"), ("m2", "Abroad")), callback],
        "edges": [line("opening", "m1", "cb")],
    }
    flow["nodes"][0]["settings"]["buttons"][1] |= {"action": "callback", "value": "International patient"}
    chat = Chat(flow)
    chat(tap="m2")  # "call back about: International patient"
    chat("Asha")
    chat("9876543210")
    assert chat.labels() == ["Yes, that's correct", "Change details"]
    said = chat(tap="change")  # nothing is lost or sent
    assert said == ["No problem. Which details would you like to change?"]
    assert chat.labels() == ["Name", "Contact number", "Reason"]  # only what this block asked (no email)
    assert chat(tap="Name") == ["May I know your full name?"]
    said = chat("Asha Rao")  # only that one question, then the check again
    assert said[0] == (
        "Please check your details:\nName: Asha Rao\nPhone: +91 9876543210\nAbout: International patient"
    )
    assert chat.labels() == ["Yes, that's correct", "Change details"]
    chat(tap="change")
    assert chat("the reason") == ["What would you like us to call you about?"]  # typed works too
    chat("about my visa")
    chat(tap="yes")
    assert chat.r["lead"]["name"] == "Asha Rao" and chat.r["lead"]["reason"] == "about my visa"
    assert chat.r["state"]["fields"] == {"name": "Asha Rao", "phone": "+91 9876543210"}  # only who it is
    chat("main menu")
    assert chat(tap="m1") == ["What would you like us to call you about?"]  # asked again, not "International"


def booking_chat(fields: list[str], free: dict[str, Any] | None = None) -> Chat:
    book = {"id": "book", "type": "book", "settings": {"fields": fields}}
    flow = {"nodes": [opening(("m1", "Book")), book], "edges": [line("opening", "m1", "book")]}
    return Chat(flow, ctx(slots=free, booking_options=["FUE", "PRP"]))


def test_change_details_offers_each_detail_asked_and_keeps_the_others() -> None:
    free = {"in_clinic": {"2026-10-29": ["11:00", "11:15"], "2026-10-30": ["11:15", "12:00"]}, "online": {}}
    chat = booking_chat(["name", "phone", "email", "treatment", "date", "time"], free)
    for answer in ("book", "Asha", "9876543210", "asha@example.com", "FUE"):
        chat(answer)
    chat(tap="2026-10-29")
    chat(tap="11:00")
    chat(tap="change")
    assert chat.labels() == ["Name", "Contact number", "Email", "Treatment", "Date", "Time"]

    assert chat(tap="Contact number") == ["What is your contact number?"]  # no "Thanks, Asha." here
    assert "valid phone" in chat("123")[0]  # its usual check, on the same question
    assert "Phone: +91 9876500000" in chat("98765 00000")[0]
    chat(tap="change")
    chat(tap="Email")
    assert "Email: new@example.com" in chat("new@example.com")[0]
    chat(tap="change")
    assert chat(tap="Treatment") == ["Which treatment are you looking for?"]
    assert chat.labels() == ["FUE", "PRP"]
    assert "Treatment: PRP" in chat(tap="PRP")[0]
    chat(tap="change")
    chat(tap="Time")
    assert chat.labels() == ["11:00 AM", "11:15 AM", "Any time"]  # that day's free times
    assert "Time: 11:15 AM" in chat(tap="11:15")[0]
    chat(tap="change")
    chat(tap="Date")
    assert "Date: Fri 30 Oct\nTime: 11:15 AM" in chat(tap="2026-10-30")[0]  # still free: kept

    chat(tap="yes")
    assert chat.r["lead"] == {
        "type": "book", "block": "book", "name": "Asha", "phone": "+91 9876500000",
        "email": "new@example.com", "treatment": "PRP", "date": "2026-10-30", "time": "11:15",
    }  # fmt: skip


def test_change_date_asks_the_time_again_when_it_is_not_free_that_day() -> None:
    free = {"in_clinic": {"2026-10-29": ["11:00"], "2026-10-30": ["12:00"]}, "online": {}}
    chat = booking_chat(["name", "date", "time"], free)
    chat("book")
    chat("Asha")
    chat(tap="2026-10-29")
    chat(tap="11:00")
    chat(tap="change")
    chat(tap="Date")
    said = chat(tap="2026-10-30")
    assert said == ["11:00 AM is not free on Fri 30 Oct.", "What time would you prefer?"]
    assert chat.labels() == ["12:00 PM", "Any time"]
    assert "Date: Fri 30 Oct\nTime: 12:00 PM" in chat(tap="12:00")[0]
    chat(tap="yes")
    assert chat.r["lead"]["date"] == "2026-10-30" and chat.r["lead"]["time"] == "12:00"


def test_change_details_typed_replies() -> None:
    chat = booking_chat(["name", "phone", "email"])
    for answer in ("book", "Asha", "9876543210", "asha@example.com"):
        chat(answer)
    chat("change details")
    assert chat("emal") == ["What is your email address?"]  # a typo
    chat("new@example.com")
    chat("change details")
    assert chat("my phone number please") == ["What is your contact number?"]  # named in a sentence
    chat("9876500000")
    chat("change details")
    assert chat("my date of birth") == ["Please choose which details to change."]  # not one of them
    assert chat("name and email") == ["Please choose which details to change."]  # two: asks which
    assert chat.labels() == ["Name", "Contact number", "Email"]
    assert chat("no")[0].startswith("Please check your details:")  # nothing to change after all
    assert chat.labels() == ["Yes, that's correct", "Change details"]


def test_change_details_never_offers_a_fixed_treatment_and_still_finishes() -> None:
    book = {"id": "book", "type": "book", "settings": {"fields": ["name", "treatment"], "treatment": "FUE"}}
    chat = Chat({"nodes": [opening(("m1", "Book")), book], "edges": [line("opening", "m1", "book")]})
    chat("book")
    chat("Asha")
    chat(tap="change")
    assert chat.labels() == ["Name"]
    chat(tap="Name")
    chat("Asha Rao")
    chat(tap="yes")
    assert chat.r["lead"]["treatment"] == "FUE" and chat.r["lead"]["name"] == "Asha Rao"


def test_change_details_treatment_with_techniques_asks_which_exactly() -> None:
    c = ctx(booking_options=["FUE", "Non-Surgical"], techniques={"Non-Surgical": ["PRP", "GFC"]})
    book = {"id": "book", "type": "book", "settings": {"fields": ["name", "treatment"]}}
    chat = Chat({"nodes": [opening(("m1", "Book")), book], "edges": [line("opening", "m1", "book")]}, c)
    chat("book")
    chat("Asha")
    chat(tap="FUE")
    chat(tap="change")
    chat(tap="Treatment")
    assert chat(tap="Non-Surgical") == ["Which treatment exactly?"]
    assert "Treatment: GFC" in chat(tap="GFC")[0]
    assert chat.labels() == ["Yes, that's correct", "Change details"]


def test_the_name_question_never_takes_a_question_or_a_topic_as_the_name() -> None:
    book = {"id": "book", "type": "book", "settings": {"fields": ["name", "phone"]}}
    page = {"id": "page-cost", "type": "choice", "settings": {"message": "The cost depends on your plan."}}
    flow = {"nodes": [opening(("m1", "Book")), book, page], "edges": [line("opening", "m1", "book")]}
    kb = ctx(kb=lambda q: "We are open 10 to 7." if "open" in q else None)

    chat = Chat(flow, kb)
    chat(tap="m1")
    # a question the Knowledge base knows: answered, then the name again
    assert chat("when are you open?") == ["We are open 10 to 7.", "May I know your full name?"]
    # a topic with the clinic's own page: that page's message, then the name again
    assert chat("price") == ["The cost depends on your plan.", "May I know your full name?"]
    for not_a_name in ("what is the price", "reviews", "I want to book an appointment please now ok"):
        texts = chat(not_a_name)
        assert not any(t.startswith("Thanks,") for t in texts), (not_a_name, texts)
        assert chat.at == "book"
    chat = Chat(flow, kb)
    chat(tap="m1")
    assert chat("Will Smith") == ["Thanks, Will Smith. What is your contact number?"]  # a real name
    chat = Chat(flow, kb)
    chat(tap="m1")
    assert chat("Mohammed Abid") == ["Thanks, Mohammed Abid. What is your contact number?"]


def test_the_live_chat_shows_free_dates_as_a_calendar_and_times_as_a_grid() -> None:
    from app.chat.canvas import _widget

    book = {"id": "book", "type": "book", "settings": {"fields": ["date", "time"], "consent": False}}
    free = {"in_clinic": {"2026-10-29": ["11:00", "11:15"], "2026-11-02": ["10:00"]}, "online": {}}
    flow = {"nodes": [opening(("m1", "Book")), book], "edges": [line("opening", "m1", "book")]}
    chat = Chat(flow, ctx(slots=free))
    pub = {"flow": chat.flow, "contact": {"phone": ""}}

    chat(tap="m1")
    ui = _widget(chat.r, pub, None).ui or {}
    assert ui["type"] == "month_calendar" and ui["action"] == "canvas"
    assert (ui["min"], ui["max"], ui["dates"]) == ("2026-10-29", "2026-11-02", ["2026-10-29", "2026-11-02"])
    assert "no free times" in chat("30 oct")[0]
    assert (_widget(chat.r, pub, None).ui or {})["type"] == "month_calendar"  # offered again
    chat(tap="2026-10-29")  # a calendar tap sends the date
    ui = _widget(chat.r, pub, None).ui or {}
    assert ui == {
        "type": "time_grid",
        "action": "canvas",
        "slots": ["11:00", "11:15"],
        "first": 8,
        "any_time": True,
    }
    chat(tap="11:15")
    assert chat.r["lead"]["date"] == "2026-10-29" and chat.r["lead"]["time"] == "11:15"


def test_the_live_chat_shows_the_doctor_card_with_photo_figures_and_profile() -> None:
    from app.chat.canvas import _widget

    settings = {
        "doctor": "Dr. Asha", "title": "Consultant", "qualifications": "MBBS, MD", "about": "20 years.",
        "photo": "https://example.com/asha.jpg", "profile_url": "https://example.com/asha",
        "stats": [{"value": "10,000+", "label": "Patients"}], "book_label": "Book with Dr. Asha",
    }  # fmt: skip
    card = {"id": "doc", "type": "doctor_card", "settings": settings}
    book = {"id": "book", "type": "book", "settings": {"fields": ["name"], "consent": False}}
    flow = {
        "nodes": [opening(("m1", "Doctors")), card, book],
        "edges": [line("opening", "m1", "doc"), line("doc", "book", "book")],
    }
    today = {
        "Dr. Asha": {
            "in_clinic": [("10:00", "13:00")], "online": [], "on_leave": False, "closed": False,
            "times": ["11:00"], "next": None,
        }
    }  # fmt: skip
    chat = Chat(flow, ctx(doctor_today=today))
    chat(tap="m1")
    res = _widget(chat.r, {"flow": chat.flow, "contact": {"phone": ""}}, None)
    ui = res.ui or {}
    assert res.messages == []  # the card says it all, no repeated text
    assert ui["type"] == "doctor_card" and ui["main"] is True  # always a way back to the menu
    assert (ui["name"], ui["title"], ui["quals"], ui["about"]) == (
        "Dr. Asha",
        "Consultant",
        "MBBS, MD",
        "20 years.",
    )
    assert ui["photo"] == "https://example.com/asha.jpg" and ui["profile_url"] == "https://example.com/asha"
    assert ui["stats"] == [{"value": "10,000+", "label": "Patients"}]
    assert ui["today"].endswith("Choose a time to book your appointment today:")
    assert [o["label"] for o in ui["options"]] == ["11:00 AM", "Book with Dr. Asha"]


def test_the_live_chat_shows_a_media_block_in_its_place_with_its_caption() -> None:
    from app.chat.canvas import _widget

    media = {
        "id": "pic", "type": "media",
        "settings": {"kind": "image", "url": "https://example.com/clinic.jpg", "caption": "Our clinic"},
    }  # fmt: skip
    after = {"id": "after", "type": "answer", "settings": {"text": "See you soon."}}
    flow = {
        "nodes": [opening(("m1", "Photo")), media, after],
        "edges": [line("opening", "m1", "pic"), line("pic", "next", "after")],
    }
    chat = Chat(flow)
    chat(tap="m1")
    res = _widget(chat.r, {"flow": chat.flow, "contact": {"phone": ""}}, None)
    shown = [(m.text, m.media.kind if m.media else None) for m in res.messages]
    assert shown == [
        ("Our clinic", "image"),
        ("See you soon.", None),
    ]  # the image first, then the chat goes on
    assert res.messages[0].media and res.messages[0].media.url == "https://example.com/clinic.jpg"


def test_carousel_cards_buttons_work_and_show_as_cards_in_the_live_chat() -> None:
    from app.chat.canvas import _widget

    cards = [
        {"title": "Offer A", "text": "10% off", "image": "https://example.com/a.jpg",
         "buttons": [{"id": "b1", "label": "Book this", "action": "book", "value": "FUE"}]},
        {"title": "Offer B",
         "buttons": [{"id": "b1", "label": "Call us", "action": "call", "value": "+919000000000"}]},
    ]  # fmt: skip
    carousel = {"id": "car", "type": "carousel", "settings": {"source": "custom", "cards": cards}}
    book = {"id": "book", "type": "book", "settings": {"fields": ["treatment", "name"], "consent": False}}
    flow = {"nodes": [opening(("m1", "Offers")), carousel, book], "edges": [line("opening", "m1", "car")]}
    chat = Chat(flow)
    chat(tap="m1")
    pub = {"flow": chat.flow, "contact": {"phone": ""}}
    ui = _widget(chat.r, pub, None).ui or {}
    assert ui["type"] == "carousel" and ui["main"] is True and ui["options"] == []
    assert [(c["title"], c["image"]) for c in ui["cards"]] == [
        ("Offer A", "https://example.com/a.jpg"),
        ("Offer B", ""),
    ]
    assert ui["cards"][0]["options"] == [{"label": "Book this", "action": "canvas", "value": "car|card0:b1"}]
    assert ui["cards"][1]["options"][0]["href"] == "tel:+919000000000"
    # the card's button does its own job: Book with the treatment filled in, so it is not asked
    assert chat(tap="card0:b1") == ["May I know your full name?"]
    assert chat.at == "book"

    live = {
        "id": "car",
        "type": "carousel",
        "settings": {"source": "treatments", "category": "Hair transplant"},
    }
    flow = {"nodes": [opening(("m1", "Treatments")), live], "edges": [line("opening", "m1", "car")]}
    chat = Chat(flow)
    chat(tap="m1")
    ui = _widget(chat.r, {"flow": chat.flow, "contact": {"phone": ""}}, None).ui or {}
    assert [(c["title"], c["text"]) for c in ui["cards"]] == [("FUE", "From ₹50,000")]
    assert ui["cards"][0]["options"] == [{"label": "View", "action": "canvas", "value": "car|t:FUE"}]
    assert ui["options"] == []  # its View is on the card, not again under the cards
    assert chat(tap="t:FUE")[0].startswith("FUE")


def test_a_doctor_card_without_buttons_is_still_shown_as_the_card() -> None:
    from app.chat.canvas import _widget

    card = {"id": "doc", "type": "doctor_card", "settings": {"doctor": "Dr. Asha", "title": "Consultant"}}
    flow = {"nodes": [opening(("m1", "Doctors")), card], "edges": [line("opening", "m1", "doc")]}
    chat = Chat(flow)
    chat(tap="m1")
    res = _widget(chat.r, {"flow": chat.flow, "contact": {"phone": ""}}, None)
    assert res.messages == [] and (res.ui or {})["type"] == "doctor_card" and (res.ui or {})["options"] == []


def test_a_treatment_shows_its_photo_duration_and_read_more_page() -> None:
    from app.chat.canvas import _widget

    prp = {
        "name": "PRP", "category": "Hair fall", "show": True, "description": "Platelet rich plasma.",
        "duration": "45 minutes", "photo": "https://example.com/prp.jpg", "page": "https://example.com/prp",
    }  # fmt: skip
    listed = {"id": "list", "type": "treatment_list", "settings": {"category": "Hair fall"}}
    book = {"id": "book", "type": "book", "settings": {"fields": ["name"], "consent": False}}
    flow = {"nodes": [opening(("m1", "Hair fall")), listed, book], "edges": [line("opening", "m1", "list")]}
    chat = Chat(flow, Context(today=WED, minutes=11 * 60, services=[FUE, prp]))
    chat(tap="m1")
    assert chat(tap="t:PRP") == ["PRP\nDuration: 45 minutes\nPlatelet rich plasma."]
    assert chat.labels() == ["Book", "Read more"]
    res = _widget(chat.r, {"flow": chat.flow, "contact": {"phone": ""}}, None)
    assert res.messages[0].media and res.messages[0].media.url == "https://example.com/prp.jpg"  # the photo
    options = (res.ui or {})["options"]
    assert options[1] == {"label": "Read more", "href": "https://example.com/prp"}  # opens the page at once
    assert chat(tap="read:PRP") == [""]  # the test chat: the page to open
    assert chat.r["messages"][0]["open"] == {"action": "link", "value": "https://example.com/prp"}


def test_the_location_block_shows_todays_hours_and_a_map_button_when_switched_on() -> None:
    where = {"id": "loc", "type": "location", "settings": {"message": "Find us here:"}}
    flow = {"nodes": [opening(("m1", "Location")), where], "edges": [line("opening", "m1", "loc")]}
    c = Context(
        today=WED, minutes=11 * 60, location="1st floor, Scorpio House", maps_link="https://maps.app.goo.gl/x",
        hours_today="Today: 10:00 AM – 7:00 PM (open now).",
    )  # fmt: skip
    chat = Chat(flow, c)
    assert chat(tap="m1") == [
        "Find us here:\n1st floor, Scorpio House\nToday: 10:00 AM – 7:00 PM (open now)."
    ]
    assert chat.r["messages"][-1]["buttons"][0] == {
        "id": "map", "label": "Open in Google Maps", "action": "link", "value": "https://maps.app.goo.gl/x"
    }  # fmt: skip
    off = {**where, "settings": {"message": "Find us here:", "map": False, "hours": False}}
    chat = Chat({"nodes": [opening(("m1", "Location")), off], "edges": flow["edges"]}, c)
    assert chat(tap="m1") == ["Find us here:\n1st floor, Scorpio House"]
    assert chat.labels() == []


def test_a_knowledge_block_limits_answers_to_its_topics() -> None:
    import pytest

    from app.chat.kb import _Row, _within, best
    from app.crm.flow import FlowError
    from app.crm.flow_run import kb_topics

    rows = [
        _Row("1", "what does it cost", "From Rs 50,000.", ("cost",), "cost"),
        _Row("2", "who is the doctor", "Dr. Asha.", ("doctor",), "doctor"),
    ]
    assert _within(rows, ()) == rows  # no topics: all
    assert [r.id for r in _within(rows, ("doctor",))] == ["2"]
    assert best(_within(rows, ("doctor",)), "cost") is None  # a cost answer is not given in a doctors block

    ask = {"id": "ask", "type": "knowledge", "settings": {"topics": ["doctor", "policy"]}}
    flow = normalise({"nodes": [opening(("m1", "Ask")), ask], "edges": [line("opening", "m1", "ask")]})
    chat = Chat(flow)
    chat(tap="m1")
    assert kb_topics(chat.flow, chat.r["state"]) == ("doctor", "policy")  # waiting for its question
    assert kb_topics(chat.flow, start(chat.flow, ctx())["state"]) == ()  # elsewhere: all topics
    with pytest.raises(FlowError, match="clinic_info"):
        normalise({"nodes": [opening(), {**ask, "settings": {"topics": ["anything"]}}], "edges": []})


def test_a_blocks_typing_delay_reaches_the_live_chat_and_plain_text_stays_plain() -> None:
    from app.chat.canvas import _widget

    slow = {"id": "slow", "type": "answer", "typing": 1.5, "settings": {"text": "Let me check."}}
    flow = {"nodes": [opening(("m1", "Ask")), slow], "edges": [line("opening", "m1", "slow")]}
    chat = Chat(flow)
    chat(tap="m1")
    res = _widget(chat.r, {"flow": chat.flow, "contact": {"phone": ""}}, None)
    assert [m.model_dump() for m in res.messages] == [
        {"type": "text", "text": "Let me check.", "typing": 1.5}
    ]
    chat = Chat(flow)
    res = _widget(chat.r, {"flow": chat.flow, "contact": {"phone": ""}}, None)
    assert res.messages[0].model_dump() == {"type": "text", "text": "Hi!"}  # no delay: as before


def test_book_with_this_doctor_keeps_the_doctor_and_offers_their_free_times() -> None:
    from app.api.v1.crm_console import slot_doctor

    card = {"id": "doc", "type": "doctor_card",
            "settings": {"doctor": "Dr. Asha", "book_label": "Book with this doctor"}}  # fmt: skip
    book = {"id": "book", "type": "book", "settings": {"fields": ["name", "date"], "consent": False}}
    flow = {
        "nodes": [opening(("m1", "Doctors")), card, book],
        "edges": [line("opening", "m1", "doc"), line("doc", "book", "book")],
    }
    chat = Chat(flow, ctx(slots={"in_clinic": {"2026-10-29": ["11:00"]}, "online": {}}))
    chat(tap="m1")
    assert "Book with this doctor" in chat.labels()
    assert chat(tap="book") == ["May I know your full name?"]
    assert slot_doctor(chat.flow["nodes"][2], chat.r["state"]) == "Dr. Asha"  # Dr. Asha's free times
    assert slot_doctor({"settings": {"doctor": "Dr. B"}}, chat.r["state"]) == "Dr. B"  # the block's own wins
    chat("Asha Patient")
    chat(tap="2026-10-29")
    assert chat.r["lead"]["doctor"] == "Dr. Asha"  # saved with the doctor chosen on the card


def test_an_unanswered_question_offers_a_call_back_about_it_not_a_dead_end() -> None:
    cb = {
        "id": "cb",
        "type": "callback",
        "settings": {"fields": ["name", "phone", "reason"], "consent": False},
    }
    flow = {"nodes": [opening(("m1", "Call back")), cb], "edges": [line("opening", "m1", "cb")]}
    chat = Chat(flow)
    assert chat("do you accept insurance?")[0].startswith("I don't have a confirmed answer for that yet.")
    assert chat.labels() == ["Yes, call me back", "No, thanks"]
    assert chat.r["matched"] == {"how": "no answer", "text": "do you accept insurance?"}
    assert chat(tap="medical:yes") == ["May I know your full name?"]
    chat("Asha Rao")
    chat("9876543210")
    assert chat.r["lead"]["reason"] == "do you accept insurance?"  # the team knows what to call about
    chat = Chat(flow)
    assert chat("zxqw blorp") == [
        "Sorry, I didn't get that. Please choose one of the options."
    ]  # no question
    no_cb = {"nodes": [opening(("m1", "Hi"))], "edges": []}
    assert Chat(no_cb)("do you accept insurance?") == [
        "Sorry, I didn't get that. Please choose one of the options."
    ]


def test_any_offers_counts_as_a_question_for_the_call_back_offer() -> None:
    cb = {"id": "cb", "type": "callback", "settings": {"fields": ["name"], "consent": False}}
    chat = Chat({"nodes": [opening(("m1", "Call back")), cb], "edges": [line("opening", "m1", "cb")]})
    assert chat("any offers or discounts")[0].startswith("I don't have a confirmed answer")


def test_a_success_rate_is_not_a_price_question_but_rates_still_are() -> None:
    from app.chat.understand import INTENTS

    cost = next(p for p, target in INTENTS if target == ("node", "cost"))
    for price in ("what are your rates", "rate for prp", "ivf rate kitna", "how much", "cost of fue"):
        assert cost.search(price), price
    for outcome in (
        "ivf success rate",
        "what is the pregnancy rate",
        "graft survival rate",
        "hair growth rate",
    ):
        assert not cost.search(outcome), outcome


def test_part_of_a_treatment_name_asks_did_you_mean_and_the_whole_of_it_opens_the_card() -> None:
    scar = {"name": "Acne Scar Treatment", "category": "Skin", "show": True, "description": "For old scars."}
    prp = {"name": "PRP Treatment", "category": "Hair", "show": True, "description": "Your own plasma."}
    c = Context(today=WED, minutes=11 * 60, services=[scar, prp])
    flow = {"nodes": [opening(("m1", "Hi"))], "edges": []}

    chat = Chat(flow, c)
    assert chat("acne treatment") == ["Did you mean Acne Scar Treatment?"]  # acne is not acne scars
    assert chat.labels() == ["Yes, show it", "No, main menu"]
    assert chat(tap="t:Acne Scar Treatment")[0].startswith("Acne Scar Treatment")
    chat = Chat(flow, c)
    assert chat("acne scar treatment")[0].startswith("Acne Scar Treatment")  # the whole name: the card
    chat = Chat(flow, c)
    assert chat("prp")[0].startswith("PRP Treatment")  # "treatment" need not be typed


def test_a_treatment_with_a_cost_or_other_question_answers_that_part_too() -> None:
    botox = {"name": "Botox", "category": "Skin", "show": True, "description": "Softens lines."}
    ivf = {
        "name": "In-Vitro Fertilization (IVF)",
        "category": "Fertility",
        "show": True,
        "description": "IVF.",
    }
    c = Context(today=WED, minutes=11 * 60, services=[FUE, botox, ivf])
    book = {"id": "book", "type": "book", "settings": {"fields": ["name"], "consent": False}}
    cb = {"id": "cb", "type": "callback", "settings": {"fields": ["name"], "consent": False}}
    flow = {"nodes": [opening(("m1", "Book")), book, cb], "edges": [line("opening", "m1", "book")]}

    chat = Chat(flow, c)
    said = chat("botox cost")
    assert said[0] == "Botox\nSoftens lines." and said[1].startswith(
        "The cost of Botox depends on your assessment"
    )
    assert chat.labels() == ["Get the exact cost", "Book", "No, thanks"]
    chat(tap="medical:yes")
    chat("Asha Rao")
    assert chat.r["lead"]["reason"] == "Cost of Botox" and chat.r["lead"]["treatment"] == "Botox"

    chat = Chat(flow, c)
    said = chat("ivf success rate")  # its short name in brackets, and a question about it
    assert said[0] == "In-Vitro Fertilization (IVF)\nIVF." and said[1].startswith(
        "I don't have a confirmed answer"
    )
    assert chat.labels() == ["Yes, call me back", "Book", "No, thanks"]

    chat = Chat(flow, c)
    assert chat("fue price")[0].startswith("FUE\nFrom ₹50,000")  # its price is shown: just its card
    assert "Book" in chat.labels()
    chat = Chat(flow, c)
    assert chat("ivf") == ["In-Vitro Fertilization (IVF)\nIVF."]  # the short name alone: its card


def test_asking_about_emergency_services_is_not_an_emergency_but_a_real_one_still_is() -> None:
    from app.chat.understand import is_emergency

    for info in (
        "what emergency services are available?",
        "do you have emergency services",
        "emergency number?",
    ):
        assert not is_emergency(info), info
    for real in (
        "emergency",
        "emergency! i am bleeding",
        "help emergency",
        "bleeding after surgery",
        "do you have emergency services? my father fainted",
        "is there an emergency doctor available now",
    ):
        assert is_emergency(real), real  # fmt: skip

    sos = {"id": "sos", "type": "emergency", "settings": {"text": "Call 108 now."}}
    flow = {"nodes": [opening(("m1", "Hi")), sos], "edges": []}
    kb = ctx(kb=lambda q: "No emergency services; call the clinic." if "emergency" in q else None)
    chat = Chat(flow, kb)
    assert chat("do you have emergency services?") == ["No emergency services; call the clinic."]
    assert chat.at != "sos" and not chat.r.get("alert")  # answered, no staff alert
    assert chat("emergency, I am bleeding")[0] == "Call 108 now." and chat.at == "sos"


def test_a_doctor_card_photo_is_a_link_or_a_small_uploaded_picture() -> None:
    import pytest

    from app.crm.flow import FlowError

    def card(photo: str) -> dict[str, Any]:
        doc = {"id": "doc", "type": "doctor_card", "settings": {"doctor": "Dr. Asha", "photo": photo}}
        return {"nodes": [opening(("m1", "Doctors")), doc], "edges": [line("opening", "m1", "doc")]}

    for ok in ("", "https://example.com/asha.jpg", "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ=="):
        normalise(card(ok))
    for bad in (
        "http://example.com/a.jpg",
        "data:text/html;base64,PHNjcmlwdD4=",
        "data:image/jpeg;base64," + "A" * 130_000,
    ):
        with pytest.raises(FlowError):
            normalise(card(bad))


def test_a_lead_block_says_its_own_message_before_the_first_question() -> None:
    intro = "Sure! Our team will call you back. Please share a few details."
    cb = {"id": "cb", "type": "callback", "settings": {"fields": ["name", "phone"], "intro": intro}}
    chat = Chat({"nodes": [opening(("m1", "Call Back")), cb], "edges": [line("opening", "m1", "cb")]})
    assert chat(tap="m1") == [intro, "May I know your full name?"]
    chat("Asha Rao")  # the message is said once, not before every question
    assert chat.r["messages"][-1]["text"] == "Thanks, Asha Rao. What is your contact number?"
    plain = {"id": "cb", "type": "callback", "settings": {"fields": ["name"]}}
    bare = Chat({"nodes": [opening(("m1", "Call Back")), plain], "edges": [line("opening", "m1", "cb")]})
    assert bare(tap="m1") == ["May I know your full name?"]  # no message set: as before


def test_comma_wordings_count_and_another_answers_word_counts_against_a_match() -> None:
    from app.chat.kb import _Row, best, wordings, words

    assert wordings("What is your email address?, email address; clinic email address\nmail id") == [
        "What is your email address?", "email address", "clinic email address", "mail id",
    ]  # fmt: skip
    address = _Row("1", "clinic address", "1st floor, Scorpio House", (words("clinic address"),))
    email = _Row("2", "clinic email", "info@clinic.com", (words("clinic email"), words("email address")))
    hit = best([address, email], "clinic email address")
    assert hit is not None and hit.answer == "info@clinic.com"  # not the address
    hit = best([address, email], "clinic address")
    assert hit is not None and hit.answer == "1st floor, Scorpio House"  # the address still is the address
