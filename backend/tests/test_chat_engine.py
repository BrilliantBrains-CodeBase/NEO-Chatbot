"""Conversation engine, step B3: greeting, menu, fixed answers, treatment cards. No database."""

from typing import Any

from app.chat import engine
from app.chat.schemas import ChatRequest


def req(event: str = "start", clinic: str = "CL01", **payload: Any) -> ChatRequest:
    return ChatRequest.model_validate(
        {
            "client_id": clinic,
            "session_id": "s_" + "a" * 32,
            "visitor_id": "v_" + "b" * 32,
            "event": event,
            "payload": payload,
            "context": {"page_url": "https://neofollicletransplant.com/", "device": "desktop", "lang": "en"},
        }
    )


def texts(turn: engine.Turn) -> list[str]:
    return [m.text for m in turn.reply.messages]


def test_start_greets_with_the_seven_card_menu() -> None:
    turn = engine.respond(req(), {})
    assert texts(turn) == ["Hi, I'm Arya, Neo Follicle's AI assistant. How can I help you today?"]
    ui = turn.reply.ui or {}
    assert ui["layout"] == "cards3"
    assert [i["label"] for i in ui["items"]] == [
        "Book Consultation",
        "Explore Treatments",
        "About Doctors",
        "International Patients",
        "Call Back",
        "WhatsApp",
        "Emergency",
    ]


def test_fixed_answers_word_for_word() -> None:
    book = engine.respond(req("button", action="go", value="book"), {})
    assert texts(book) == ["What would you like to do?"]
    assert [o["label"] for o in (book.reply.ui or {})["options"]][0] == "Book appointment (in-clinic)"
    emergency = engine.respond(req("button", action="go", value="emergency"), {})
    assert "call **108**" in texts(emergency)[0]


def test_treatment_card_with_book_for_and_website_link() -> None:
    turn = engine.respond(req("button", action="treat", value="PRP Treatment"), {})
    assert texts(turn)[0].startswith("**PRP Treatment**\nPlatelet rich plasma")
    options = (turn.reply.ui or {})["options"]
    assert options[0] == {
        "label": "Book for PRP Treatment",
        "action": "book_for",
        "value": "PRP Treatment",
        "primary": True,
    }
    assert options[1]["href"] == "https://neofollicletransplant.com/best-prp-hair-treatment-in-bangalore/"


def test_invented_buttons_get_the_menu_never_an_error() -> None:
    for action, value in [("go", "admin"), ("treat", "Nonsense"), ("drop_table", "x"), ("go", None)]:
        turn = engine.respond(req("button", action=action, value=value), {})
        assert texts(turn) == [engine.MAIN_MENU_TEXT]
        assert (turn.reply.ui or {})["type"] == "menu"


def test_shown_buttons_include_back_and_main_menu_but_not_links() -> None:
    card = engine.respond(req("button", action="treat", value="PRP Treatment"), {})
    labels = [c["label"] for c in engine.shown_choices(card.reply.ui)]
    assert labels == ["Book for PRP Treatment", "Back", "Main menu"]  # "Read more" is a link


def test_a_clinic_without_content_still_answers() -> None:
    assert texts(engine.respond(req(clinic="CL98"), {})) == [engine.MAIN_MENU_TEXT]
