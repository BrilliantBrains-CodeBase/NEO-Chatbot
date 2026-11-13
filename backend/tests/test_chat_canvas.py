"""The live chat on the published workflow canvas (chat.canvas on): only the canvas's buttons, its flow, and a
finished call back saved as a real lead. Real database, rolled back, test clinic CL99."""

import json
from typing import Any

import asyncpg
import pytest

from app.chat import canvas, store
from app.core.config import get_settings
from app.core.db import close_pool
from tests.test_chat_store import req

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")


@pytest.fixture(autouse=True)
async def _own_pool(monkeypatch: pytest.MonkeyPatch) -> Any:
    """The canvas looks things up through the shared pool: close it with this test's event loop. These tests
    change the settings in the database directly (no Publish), so the kept setup is not used here."""
    monkeypatch.setattr(canvas, "CACHE_S", 0)
    canvas.forget()
    yield
    await close_pool()


FLOW = {
    "nodes": [
        {"id": "opening", "type": "opening", "settings": {"message": "Hello from the canvas", "buttons": [
            {"id": "m1", "label": "Call me back", "icon": "phone"},
            {"id": "m2", "label": "Our website", "action": "link", "value": "https://example.com"},
        ]}},
        {"id": "cb", "type": "callback", "settings": {"fields": ["name", "phone"]}},
    ],
    "edges": [{"source": "opening", "exit": "m1", "target": "cb"}],
}  # fmt: skip


async def publish(tx: asyncpg.Connection, on: bool) -> None:
    settings = json.dumps({"chat": {"canvas": on}, "flow": FLOW})
    await tx.execute(
        """insert into app.clinic_settings (clinic_id, draft, published, version, published_at)
           values ('CL99', $1, $1, 1, now())
           on conflict (clinic_id) do update set draft = $1, published = $1, version = 1,
             published_at = now()""",
        settings,
    )


async def test_the_switch_decides(tx: asyncpg.Connection) -> None:
    await publish(tx, on=False)
    assert await canvas.published(tx, "CL99") is None  # off: the classic chat answers
    await publish(tx, on=True)
    assert await canvas.published(tx, "CL99") is not None


async def test_canvas_buttons_flow_and_a_saved_call_back(tx: asyncpg.Connection) -> None:
    await publish(tx, on=True)
    pub = await canvas.published(tx, "CL99")
    assert pub is not None
    await store.open_session(tx, req())
    state: dict[str, Any] = {}

    async def say(r: Any) -> Any:
        nonlocal state
        reply, state, _ = await canvas.turn(tx, r, state, pub)
        return reply

    first = await say(req("start"))
    assert first.ui["type"] == "menu"  # the opening's buttons are the menu
    items = first.ui["items"]
    assert [i["label"] for i in items] == ["Call me back", "Our website"]  # only the canvas's buttons
    assert items[0] == {"label": "Call me back", "icon": "phone", "action": "canvas", "value": "opening|m1"}
    assert items[1]["href"] == "https://example.com"  # a link opens at once
    await say(req("button", action="canvas", value="m1"))  # follows the line to the call back block
    await say(req("text", text="Asha Rao"))
    check = await say(req("text", text="9800000123"))
    assert check.messages[-1].text == "Is this correct?"  # the canvas reads back and asks to confirm
    await say(req("button", action="canvas", value="yes"))
    lead = await tx.fetchrow(
        "select l.source, r.type from app.leads l join app.requests r on r.lead_id = l.id "
        "where l.clinic_id = 'CL99' and l.phone_e164 = '+919800000123'"
    )
    assert lead is not None and (lead["source"], lead["type"]) == ("chatbot", "callback")


async def test_the_mobile_book_button_follows_the_canvas(tx: asyncpg.Connection) -> None:
    """The contact row sends "start book"; on a canvas it taps the way to the booking block."""
    assert canvas._path(FLOW, "callback") == ["m1"]
    assert canvas._path(FLOW, "book") == []  # no booking block on this canvas: the menu stays
    await publish(tx, on=True)
    pub = await canvas.published(tx, "CL99")
    assert pub is not None
    reply, _, _ = await canvas.turn(tx, req("button", action="start", value="callback"), {}, pub)
    assert "name" in reply.messages[-1].text.lower()  # straight into the call back's first question


async def test_a_menu_tile_mid_question_opens_that_option(tx: asyncpg.Connection) -> None:
    """The menu tiles stay on screen: a tap while a question waits (a name, a time) opens that option from the
    menu, never counts as the answer."""
    await publish(tx, on=True)
    pub = await canvas.published(tx, "CL99")
    assert pub is not None
    state: dict[str, Any] = {}
    for r in (req("start"), req("button", action="canvas", value="m1")):
        reply, state, _ = await canvas.turn(tx, r, state, pub)
    assert "name" in reply.messages[-1].text.lower()  # waiting for a name
    reply, state, _ = await canvas.turn(tx, req("button", action="canvas", value="m1"), state, pub)
    assert "name" in reply.messages[-1].text.lower()  # the call back again from its start, not a "name"
    assert "valid" not in " ".join(m.text or "" for m in reply.messages).lower()


async def test_a_booking_without_a_date_is_kept_as_a_call_back() -> None:
    """The patient was told the team will call: the request is never dropped, even without a date."""
    from app.core.db import get_pool

    pool = await get_pool()
    phone = "+919000000888"  # as saved; the chat keeps it as "+91 9000000888"
    try:
        async with pool.acquire() as conn:
            note = await canvas._save(
                conn,
                req("text", text="x"),
                {
                    "type": "book",
                    "name": "No Date Test",
                    "phone": "+91 9000000888",
                    "treatment": "FUE",
                },  # fmt: skip
            )
            assert note is None
            r = await conn.fetchrow(
                """select r.type, r.data->>'reason' reason from app.requests r
                   join app.leads l on l.id = r.lead_id
                   where l.clinic_id = 'CL99' and l.phone_e164 = $1""",
                phone,
            )
        assert r is not None and r["type"] == "callback" and r["reason"] == "Booking request: FUE"
    finally:
        ids = [
            x["id"]
            for x in await pool.fetch(
                "select id from app.leads where clinic_id = 'CL99' and phone_e164 = $1", phone
            )
        ]
        for t in ("appointments", "requests", "lead_events", "tasks", "outbox"):
            await pool.execute(f"delete from app.{t} where lead_id = any($1::uuid[])", ids)
        await pool.execute("update app.chat_sessions set lead_id = null where lead_id = any($1::uuid[])", ids)
        await pool.execute("delete from app.leads where id = any($1::uuid[])", ids)


JOURNEY = {
    "nodes": [
        {"id": "opening", "type": "opening", "settings": {"welcome": "Hello", "buttons": [
            {"id": "m1", "label": "About Doctors"}, {"id": "m2", "label": "Call back"},
        ]}},
        {"id": "doc", "type": "doctor_card", "settings": {
            "doctor": "Dr. Canvas Test", "title": "Consultant", "book_label": "Book with this doctor"}},
        {"id": "book", "type": "book", "settings": {"fields": ["name", "phone", "date", "time"]}},
        {"id": "cb", "type": "callback", "settings": {"fields": ["name", "phone", "reason"]}},
    ],
    "edges": [
        {"source": "opening", "exit": "m1", "target": "doc"},
        {"source": "doc", "exit": "book", "target": "book"},
        {"source": "opening", "exit": "m2", "target": "cb"},
    ],
}  # fmt: skip


async def test_a_patients_booking_and_call_back_reach_the_crm(
    tx: asyncpg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end on the live canvas code: Book with this doctor -> calendar -> time grid -> confirm, and an
    unanswered question -> call back. Each must reach the CRM: lead, stage, Inbox request, appointment with
    the doctor and time, a task, the webhook and the WhatsApp message."""
    from datetime import timedelta

    from app.api.v1 import crm_console
    from app.chat import slots
    from app.chat.flows import ist_now

    settings = json.dumps({"chat": {"canvas": True}, "flow": JOURNEY})
    await tx.execute(
        """insert into app.clinic_settings (clinic_id, draft, published, version, published_at)
           values ('CL99', $1, $1, 1, now())
           on conflict (clinic_id) do update
             set draft = $1, published = $1, version = 1, published_at = now()""",
        settings,
    )
    doctor = await tx.fetchval(
        "insert into app.doctors (clinic_id, name, role_title) "
        "values ('CL99', 'Dr. Canvas Test', 'Consultant') returning id"
    )
    for day in range(7):
        await tx.execute(
            """insert into app.doctor_availability (doctor_id, clinic_id, weekday, mode, start_time, end_time)
               values ($1, 'CL99', $2, 'in_clinic', '00:00', '23:45')""",
            doctor, day,
        )  # fmt: skip

    async def free(
        clinic: str, name: str
    ) -> dict[str, dict[str, list[str]]]:  # as _free, in this transaction
        today, now = ist_now()
        doc = await tx.fetchval(
            "select id::text from app.doctors where clinic_id = $1 and name = $2", clinic, name
        )
        last = today + timedelta(days=14)
        return {
            mode: await slots.free_slots_range(tx, clinic, today, last, mode, today, now, "", doc)
            for mode in ("in_clinic", "online")
        }

    from app.crm import webhooks, whatsapp

    monkeypatch.setattr(crm_console, "_free", free)
    hooks: list[tuple[str, dict[str, Any]]] = []
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(webhooks, "emit", lambda clinic, event, data: hooks.append((event, data)))
    monkeypatch.setattr(
        whatsapp, "notify", lambda clinic, purpose, phone, data: sent.append((purpose, phone))
    )

    pub = await canvas.published(tx, "CL99")
    assert pub is not None
    await store.open_session(tx, req())
    state: dict[str, Any] = {}

    async def say(r: Any) -> Any:
        nonlocal state
        reply, state, _ = await canvas.turn(tx, r, state, pub)
        return reply

    await say(req("start"))
    card = await say(req("button", action="canvas", value="m1"))
    assert card.ui["type"] == "doctor_card" and "Book with this doctor" in [
        o["label"] for o in card.ui["options"]
    ]
    await say(req("button", action="canvas", value="book"))
    await say(req("text", text="Asha Canvas"))
    calendar = await say(req("text", text="9800000177"))
    assert calendar.ui["type"] == "month_calendar", calendar
    day = calendar.ui["dates"][-1]  # a day well ahead: every time free
    grid = await say(req("button", action="canvas", value=day))
    assert grid.ui["type"] == "time_grid"
    time = grid.ui["slots"][0]
    check = await say(req("button", action="canvas", value=time))
    assert check.messages[-1].text == "Is this correct?"
    assert not calendar.done and not grid.done and not check.done  # still open: a day can still change
    saved = await say(req("button", action="canvas", value="yes"))
    assert saved.done  # saved: the widget locks the calendar and the times above

    lead = await tx.fetchrow(
        "select id, lead_code, stage, full_name, source from app.leads "
        "where clinic_id = 'CL99' and phone_e164 = '+919800000177'"
    )
    assert lead is not None and (lead["full_name"], lead["source"]) == ("Asha Canvas", "chatbot")
    request = await tx.fetchrow("select type, data from app.requests where lead_id = $1", lead["id"])
    assert request["type"] == "book" and json.loads(request["data"])["date"] == day
    appt = await tx.fetchrow(
        "select doctor_id, status, "
        "to_char(lower(slot) at time zone 'Asia/Kolkata', 'YYYY-MM-DD HH24:MI') at_ "
        "from app.appointments where lead_id = $1",
        lead["id"],
    )
    assert appt["doctor_id"] == doctor and appt["at_"] == f"{day} {time}" and appt["status"] == "pending"
    assert await tx.fetchval("select type from app.tasks where lead_id = $1", lead["id"]) == "confirm_booking"
    assert hooks[-1][0] == "booking_request" and hooks[-1][1]["lead_code"] == lead["lead_code"]
    assert sent[-1][0] == "request_received" and sent[-1][1].replace(" ", "") == "+919800000177"
    assert lead["stage"] == "follow_up"  # the canvas's "A booking request moves the lead to Follow Up"

    # A question with no answer: the call back about it reaches the Inbox with the question as its reason.
    state = {}
    await say(req("start"))
    offer = await say(req("text", text="do you accept insurance?"))
    assert [o["label"] for o in offer.ui["options"]][:1] == ["Yes, call me back"]
    kept = await tx.fetchval(  # kept at once, before any call back (CRM -> Lead questions)
        "select count(*) from app.unanswered_questions where clinic_id = 'CL99' and session_id = $1 "
        "and question_text = 'do you accept insurance?' and lead_id is null",
        req().session_id,
    )
    assert kept == 1
    await say(req("button", action="canvas", value="medical:yes"))
    await say(req("text", text="Ravi Canvas"))
    more = await say(req("text", text="9800000188"))
    assert more.messages[-1].text == "Is this your only question, or would you like to ask more?"
    await say(req("button", action="canvas", value="q:more"))
    await say(req("text", text="Do you have parking?"))
    await say(req("button", action="canvas", value="q:done"))
    await say(req("button", action="canvas", value="yes"))
    cb = await tx.fetchrow(
        "select r.type, r.data, l.id lead from app.requests r join app.leads l on l.id = r.lead_id "
        "where l.clinic_id = 'CL99' and l.phone_e164 = '+919800000188'"
    )
    assert cb is not None and cb["type"] == "callback"
    reason = json.loads(cb["data"])["reason"]
    assert (
        reason.startswith("do you accept insurance?") and "- Do you have parking?" in reason
    )  # for the call
    asked = await tx.fetch(
        "select question_text from app.unanswered_questions where lead_id = $1 order by created_at, id",
        cb["lead"],
    )
    assert [a["question_text"] for a in asked] == ["do you accept insurance?", "Do you have parking?"]
    assert hooks[-1][0] == "callback_request"


async def test_an_older_button_still_in_the_chat_does_what_it_says(tx: asyncpg.Connection) -> None:
    """Explore -> Hair transplant list, then the patient taps Eyebrow Restoration on the Explore list above
    it: that treatment's card, never "Please choose one of the options" or the list's own b2."""
    flow = {
        "nodes": [
            {"id": "opening", "type": "opening", "settings": {"welcome": "Hi", "buttons": [
                {"id": "m1", "label": "Explore"}]}},
            {"id": "treat", "type": "choice", "settings": {"message": "Which area?", "buttons": [
                {"id": "b1", "label": "Hair transplant"},
                {"id": "b2", "label": "Eyebrow Restoration", "action": "callback", "value": "Eyebrows"}]}},
            {"id": "ht", "type": "choice", "settings": {"message": "Pick one", "buttons": [
                {"id": "b2", "label": "Our website", "action": "link", "value": "https://example.com"}]}},
            {"id": "cb", "type": "callback", "settings": {"fields": ["name"]}},
        ],
        "edges": [
            {"source": "opening", "exit": "m1", "target": "treat"},
            {"source": "treat", "exit": "b1", "target": "ht"},
        ],
    }  # fmt: skip
    await tx.execute(
        """insert into app.clinic_settings (clinic_id, draft, published, version, published_at)
           values ('CL99', $1, $1, 1, now())
           on conflict (clinic_id) do update
             set draft = $1, published = $1, version = 1, published_at = now()""",
        json.dumps({"chat": {"canvas": True}, "flow": flow}),
    )
    pub = await canvas.published(tx, "CL99")
    assert pub is not None
    state: dict[str, Any] = {}

    async def say(r: Any) -> Any:
        nonlocal state
        reply, state, _ = await canvas.turn(tx, r, state, pub)
        return reply

    await say(req("start"))
    areas = await say(req("button", action="canvas", value="opening|m1"))
    eyebrow = next(o for o in areas.ui["options"] if o["label"] == "Eyebrow Restoration")
    assert eyebrow["value"] == "treat|b2"  # the button knows its screen
    listed = await say(req("button", action="canvas", value="treat|b1"))
    labels = [o["label"] for o in listed.ui["options"]]
    assert labels[:1] == ["Our website"]  # now on the list, whose own b2 is a link
    later = await say(req("button", action="canvas", value=eyebrow["value"]))  # the older Explore button
    said = " ".join(m.text for m in later.messages)
    assert (
        "Please choose" not in said and "name" in said.lower()
    )  # Eyebrow Restoration's own job: a call back
