"""Chat sessions and transcripts (B2), on the real database inside a rolled-back transaction (CL99)."""

from typing import Any

import asyncpg
import pytest

from app.chat import store
from app.chat.schemas import ChatRequest
from app.core.config import get_settings

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")

SID = "s_" + "d" * 32
VID = "v_" + "e" * 32


def req(event: str = "start", visitor: str = VID, clinic: str = "CL99", **payload: Any) -> ChatRequest:
    return ChatRequest.model_validate(
        {
            "client_id": clinic,
            "session_id": SID,
            "visitor_id": visitor,
            "event": event,
            "payload": payload,
            "context": {"page_url": "https://example.com/hair", "device": "mobile", "lang": "en"},
        }
    )


async def transcript(db: asyncpg.Connection) -> list[tuple[str, str]]:
    rows = await db.fetch("select role, text from app.chat_messages where session_id = $1 order by id", SID)
    return [(r["role"], r["text"]) for r in rows]


async def test_first_message_creates_the_session(tx: asyncpg.Connection) -> None:
    assert await store.open_session(tx, req()) == {}
    row = await tx.fetchrow(
        "select clinic_id, visitor_id, device, page_url from app.chat_sessions where id = $1", SID
    )
    assert tuple(row) == ("CL99", VID, "mobile", "https://example.com/hair")


async def test_state_is_saved_and_loaded_with_the_transcript(tx: asyncpg.Connection) -> None:
    r = req()
    state = await store.open_session(tx, r)
    state["shown"] = [{"label": "Book Consultation", "action": "go", "value": "book"}]
    await store.save_turn(tx, r, None, ["Hi, I'm Test. How can I help you today?"], "menu", state)

    tap = req("button", action="go", value="book")
    loaded = await store.open_session(tx, tap)
    assert loaded["shown"][0]["label"] == "Book Consultation"
    said = store.patient_text(tap, loaded)
    assert said == "Book Consultation"  # the label, not the code
    await store.save_turn(tx, tap, said, ["What would you like to do?"], "flow", loaded)

    typed = req("text", text="9876543210", cc="+91")
    await store.save_turn(tx, typed, store.patient_text(typed, loaded), ["Thanks."], "flow", loaded)
    assert await transcript(tx) == [
        ("bot", "Hi, I'm Test. How can I help you today?"),
        ("patient", "Book Consultation"),
        ("bot", "What would you like to do?"),
        ("patient", "+91 9876543210"),
        ("bot", "Thanks."),
    ]


async def test_a_session_cannot_be_taken_over(tx: asyncpg.Connection) -> None:
    await store.open_session(tx, req())
    with pytest.raises(store.SessionMismatch):
        await store.open_session(tx, req(visitor="v_" + "f" * 32))  # another visitor
    with pytest.raises(store.SessionMismatch):
        await store.open_session(tx, req(clinic="CL01"))  # another clinic


async def test_an_unknown_button_is_still_recorded(tx: asyncpg.Connection) -> None:
    assert store.patient_text(req("button", action="date", value="2026-10-28"), {}) == "date: 2026-10-28"
    assert store.patient_text(req("start"), {}) is None
