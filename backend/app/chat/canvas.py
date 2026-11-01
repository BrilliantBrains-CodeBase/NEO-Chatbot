"""The live chat on the clinic's published workflow canvas (Dashboard → Menu buttons, when "Chatbot runs on
this canvas" is on and published). Each message runs the canvas engine (app.crm.flow_run) exactly as the
canvas's test chat does, with the PUBLISHED settings: the same word rules, the approved Knowledge base
(words, then meaning), the approved phrases by meaning, real free slots and the returning-patient check.
Its reply becomes the widget's blocks (menu, buttons, typing mode); a finished booking, call back or
question is saved as a real lead and Inbox request (chat/leads.save_completed), with the webhook and
WhatsApp like the classic chat.
"""

import copy
import json
import time
from typing import Any

import asyncpg

from app.chat import context, leads, main_template
from app.chat.flows import normal_phone
from app.chat.schemas import BotMessage, ChatRequest, ChatResponse, Input
from app.chat.slots import doctors_today
from app.crm import webhooks, whatsapp
from app.crm.flow_run import send, start

SLOT_TAKEN = "Sorry, that time was just booked by someone else. Please choose another time."
SAVE_KINDS = {"book", "online", "cancel", "reschedule", "callback", "question"}


# The published setup changes only on Publish (and the Knowledge base switch): kept a minute per clinic, so a
# message does not read it again; forget() clears it at once after a change.
CACHE_S = 60
_published: dict[str, tuple[float, dict[str, Any] | None]] = {}


def forget(clinic: str | None = None) -> None:
    """Drops the kept setup (one clinic, or all: a main template's change reaches its followers)."""
    if clinic is None:
        _published.clear()
    else:
        _published.pop(clinic, None)


async def published(conn: asyncpg.Connection, clinic: str) -> dict[str, Any] | None:
    """The clinic's published settings when its chat runs on the canvas (switch on and a canvas published)."""
    hit = _published.get(clinic)
    if hit and time.monotonic() - hit[0] < CACHE_S:
        return copy.deepcopy(hit[1])  # a copy: a message never changes the kept one
    pub = await _load(conn, clinic)
    _published[clinic] = (time.monotonic(), pub)
    return copy.deepcopy(pub)


async def _load(conn: asyncpg.Connection, clinic: str) -> dict[str, Any] | None:
    from app.api.v1.crm_console import _add_live_phrases, _filled  # the Dashboard's own helpers

    row = await conn.fetchrow(
        """select published->'chat' chat, published->'flow' flow, published->'services' services,
             published->'contact' contact, published->'reviews' reviews,
             coalesce((published->>'kb_only')::boolean, false) kb_only
           from app.clinic_settings where clinic_id = $1""",
        clinic,
    )
    if row is None:
        return None
    raw = {k: json.loads(row[k]) for k in ("chat", "flow", "services", "contact", "reviews") if row[k]}
    await main_template.apply(conn, clinic, raw)  # a followed canvas: the main's, in this clinic's names
    if not (raw.get("chat") or {}).get("canvas") or not (raw.get("flow") or {}).get("nodes"):
        return None
    pub = _filled(raw)
    # The clinic's approved phrases (the same ones the classic chat matches, by words and by meaning) always
    # count on the canvas too, each to the block of its topic; in memory only, the canvas is never changed.
    rows = await conn.fetch(
        "select intent, example from app.intent_examples where clinic_id = $1 and status = 'approved'", clinic
    )
    _add_live_phrases(pub["flow"], [(r["intent"], r["example"]) for r in rows])
    pub["kb_only"] = row["kb_only"]  # Knowledge base → "Typed questions: Knowledge base only"
    return pub


async def turn(
    conn: asyncpg.Connection, req: ChatRequest, state: dict[str, Any], pub: dict[str, Any]
) -> tuple[ChatResponse, dict[str, Any], str]:
    """One patient message on the canvas: the reply, the new conversation state and who answered."""
    from app.api.v1.crm_console import _context, _free, _nearest_phrase, _upcoming, kb_hit

    flow, clinic = pub["flow"], req.client_id
    ctx = _context(pub, req.context.device)
    ctx.kb_only = bool(pub.get("kb_only"))
    if any(n["type"] == "doctor_card" for n in flow["nodes"]):  # the cards show each doctor's day
        ctx.doctor_today = await doctors_today(conn, clinic, ctx.today, ctx.minutes)
    run_state = state.get("canvas")
    tap = req.payload.value if req.event == "button" and req.payload.action == "canvas" else None
    text = req.payload.text if req.event == "text" else None
    wants = req.payload.value if req.event == "button" and req.payload.action == "start" else None
    if wants:  # the mobile contact row's Book: the taps from the opening to the canvas's booking block
        reply = start(flow, ctx)
        for exit_ in _path(flow, wants):
            reply = send(flow, ctx, reply["state"], tap=exit_)
    elif req.event in ("start", "restart") or run_state is None or (tap is None and not text):
        reply = start(flow, ctx)
    elif tap in _menu_ids(flow) and run_state.get("at") != _menu_ids(flow)[tap]:
        # A main menu tile (always on screen) tapped mid-way, e.g. while asked for a name or a time: that
        # option from the menu, never an answer to the question waiting.
        fresh = start(flow, ctx)["state"]
        fresh["fields"] = {
            **(run_state.get("fields") or {}),
            **(fresh.get("fields") or {}),
        }  # what was chosen
        reply = send(flow, ctx, fresh, tap=tap)
    else:
        # As the canvas test chat: what this message may need is looked up first (the engine is synchronous).
        waiting = (run_state.get("ask") or {}).get("kind")
        if text and waiting in (None, "knowledge", "lead", "question"):
            hit = await kb_hit(clinic, text)
            # Not answered alone: read with the last messages ("and Sunday?" after "what are your timings").
            again = None if hit else context.follow_up(text, state.get("canvas_history") or [])
            if again:
                hit = await kb_hit(clinic, again)
            found = hit[0] if hit else None
            ctx.kb = lambda q: found
            ctx.kb_source = hit[1] if hit else ""
        if waiting == "check" and text:
            booked = await _upcoming(clinic, text)
            ctx.appointments = lambda phone: booked
        if text and not waiting:
            near = await _nearest_phrase(flow, text)
            ctx.meaning = lambda t: near
        phone = (run_state.get("fields") or {}).get("phone") or normal_phone((text or "").strip(), None)
        if phone:
            ctx.returning = bool(
                await conn.fetchval(
                    "select 1 from app.leads where clinic_id = $1 and phone_e164 = $2 and deleted_at is null",
                    clinic, phone.replace(" ", ""),
                )
            )  # fmt: skip
        at = next((n for n in flow["nodes"] if n["id"] == run_state.get("at")), None)
        if at and at["type"] in ("book", "online", "reschedule", "follow_up"):
            ctx.slots = await _free(clinic, at["settings"].get("doctor") or "")
        reply = send(flow, ctx, run_state, tap=tap, text=text)
    lead = reply.get("lead")
    lead_note = await _save(conn, req, lead) if lead else None
    alert = reply.get("alert")
    if alert and alert.get("phone"):  # an emergency with the patient's number: an urgent call back for staff
        said = alert.get("said") or "emergency words"
        urgent = {"type": "callback", "name": "Patient (emergency)", "phone": alert["phone"],
                  "reason": f"EMERGENCY in chat: {said}"}  # fmt: skip
        await _save(conn, req, urgent)
    said = " ".join(m["text"] for m in reply["messages"] if m.get("text"))
    history = context.keep(state.get("canvas_history") or [], text, said)  # the last 3 messages each way
    new_state = {**state, "canvas": reply["state"], "canvas_history": history}
    return _widget(reply, pub, lead_note), new_state, "flow"


def _menu_ids(flow: dict[str, Any]) -> dict[str, str]:
    """The opening's buttons (the widget's main menu tiles): button id -> the opening block's id."""
    opening = next((n for n in flow["nodes"] if n["type"] == "opening"), None)
    if opening is None:
        return {}
    return {b["id"]: opening["id"] for b in (opening.get("settings") or {}).get("buttons") or []}


def _path(flow: dict[str, Any], kind: str) -> list[str]:
    """The buttons to tap from the opening to the first block of this kind (at most 3 taps), or none."""
    kinds = {n["id"]: n["type"] for n in flow["nodes"]}
    start_id = next((n["id"] for n in flow["nodes"] if n["type"] == "opening"), None)
    paths: list[tuple[str, list[str]]] = [(start_id, [])] if start_id else []
    seen = {start_id}
    while paths:
        at, taps = paths.pop(0)
        for e in flow["edges"]:
            if e["source"] != at or e["target"] in seen or len(taps) >= 3:
                continue
            if kinds.get(e["target"]) == kind:
                return [*taps, e["exit"]]
            seen.add(e["target"])
            paths.append((e["target"], [*taps, e["exit"]]))
    return []


async def _save(conn: asyncpg.Connection, req: ChatRequest, lead: dict[str, Any]) -> str | None:
    """A finished booking / call back / question as a real lead and Inbox request. A message for the patient
    when it could not be saved (the time was just taken, or no phone number)."""
    kind = "book" if lead.get("type") == "follow_up" else lead.get("type")
    if kind not in SAVE_KINDS:
        return None
    phone = str(lead.get("phone") or "").strip()  # the canvas keeps it as "+91 98765 43210" (normal_phone)
    if " " not in phone:
        phone = normal_phone(phone, None) or ""
    if not phone:
        return None  # the canvas did not ask for a phone: nothing to call back on
    f: dict[str, Any] = {
        "kind": kind, "name": lead.get("name") or "Patient", "phone": phone, "email": lead.get("email"),
        "treatment": lead.get("treatment"), "reason": lead.get("reason"), "date": lead.get("date"),
        "time": lead.get("time") or ("any" if lead.get("date") else None),
        "booked_date": lead.get("booked_date"),
    }  # fmt: skip
    if lead.get("doctor"):  # the canvas keeps the doctor's name; a booking needs their id
        f["doctor"] = await conn.fetchval(
            "select id::text from app.doctors where clinic_id = $1 and name = $2 and active",
            req.client_id, lead["doctor"],
        )  # fmt: skip
    if kind in ("book", "online") and not f["date"]:
        return None
    if kind in ("cancel", "reschedule") and not f["booked_date"]:
        return None
    try:
        async with conn.transaction():  # a savepoint: a taken slot undoes the save, not the chat turn
            code = await leads.save_completed(conn, req, f)
    except leads.SlotTaken:
        return SLOT_TAKEN
    if kind in ("book", "online", "callback"):
        webhooks.emit(req.client_id, "callback_request" if kind == "callback" else "booking_request", {
            "lead_code": code, "type": kind, "name": f["name"], "phone": phone, "email": f["email"],
            "treatment": f["treatment"], "date": f["date"], "time": f["time"], "reason": f["reason"],
        })  # fmt: skip
        whatsapp.notify(req.client_id, "request_received", phone, {
            "lead_code": code, "name": f["name"], "treatment": f["treatment"], "date": f["date"],
            "time": f["time"],
        })  # fmt: skip
    return None


def _choice(b: dict[str, Any], phone: str) -> dict[str, Any] | None:
    """A canvas button as the widget's: a link opens at once; the rest go back as the canvas's own id."""
    out: dict[str, Any] = {"label": b["label"]}
    if b.get("icon"):
        out["icon"] = b["icon"]
    if b.get("variant") in ("wa", "sos"):
        out["variant"] = b["variant"]
    action, value = b.get("action"), str(b.get("value") or "")
    if action == "call":
        number = value or phone
        return out | {"href": "tel:" + number} if number else None
    if action in ("link", "whatsapp"):
        return out | {"href": value} if value.startswith("https://") else None
    return out | {"action": "canvas", "value": str(b["id"])[:200]}


def _widget(reply: dict[str, Any], pub: dict[str, Any], note: str | None) -> ChatResponse:
    """The canvas's reply in the widget's blocks: its texts, then the last buttons it offered (the opening's
    as the menu, in the chosen Template), and the typing mode it asked for."""
    phone = pub["contact"].get("phone") or ""
    said = [m["text"] for m in reply["messages"] if m.get("text")]
    said = [t for i, t in enumerate(said) if i == 0 or t != said[i - 1]]  # greeting, then the opening
    texts = [BotMessage(text=t) for t in said] + ([BotMessage(text=note)] if note else [])
    last = next((m for m in reversed(reply["messages"]) if m.get("buttons") or m.get("open")), None)
    choices: list[dict[str, Any]] = []
    if last and last.get("open"):  # a link / call block: one button to open it
        o = last["open"]
        label = {"call": "Call now", "whatsapp": "Open WhatsApp"}.get(o.get("action"), "Open link")
        c = _choice({"id": "open", "label": label, "action": o.get("action"), "value": o.get("value")}, phone)
        choices = [c] if c else []
    elif last:
        choices = [c for b in last["buttons"] if (c := _choice(b, phone))]
    at = next((n for n in pub["flow"]["nodes"] if n["id"] == reply.get("at")), None)
    ui: dict[str, Any] | None = None
    if choices and at and at["type"] == "opening":
        ui = {"type": "menu", "layout": "cards3", "items": choices}
    elif choices:
        ui = {"type": "chips", "options": choices, "main": True}
    mode = next((m["input"]["mode"] for m in reversed(reply["messages"]) if m.get("input")), "text")
    mode = mode if mode in ("text", "phone", "email") else "text"
    placeholder = {"phone": "Your mobile number", "email": "Your email"}.get(mode, "Type your question")
    return ChatResponse(messages=texts, ui=ui, input=Input(mode=mode, placeholder=placeholder))
