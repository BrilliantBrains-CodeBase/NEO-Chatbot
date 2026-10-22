"""One chat turn: load the session, work out the reply, save everything, in one transaction."""

import json
import time
from datetime import timedelta
from typing import Any

import asyncpg

from app.chat import embed, engine, flows, kb, leads, store, understand
from app.chat.content import content
from app.chat.guard import Clinic
from app.chat.schemas import ChatRequest, ChatResponse
from app.chat.slots import Mode, free_slots_range
from app.core.db import get_pool


async def handle(req: ChatRequest, clinic: Clinic) -> ChatResponse:
    """Raises store.SessionMismatch when the session belongs to another clinic or visitor."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        state = await store.open_session(conn, req)
        said = store.patient_text(req, state)
        started = time.perf_counter()
        steps: list[Step] = []
        hit = await _kb(conn, req, steps)
        turn = engine.respond(req, state, await _slots(conn, req, state), hit.answer if hit else None)
        if turn.completed:
            try:
                async with conn.transaction():  # a savepoint: a taken slot undoes the save, not the turn
                    await leads.save_completed(conn, req, turn.completed)
            except leads.SlotTaken:
                again = {"flow": turn.completed}
                turn = engine.slot_taken(req, turn.completed, await _slots(conn, req, again))
        f = turn.state.get("flow")
        if f and f["step"] == "summary" and f["kind"] in ("book", "online") and f.get("time") != "any":
            if not await leads.hold_slot(conn, req, f):
                turn = engine.slot_taken(req, f, await _slots(conn, req, turn.state))
        # Recent buttons (newest first, at most 60) so the transcript can show the label of any tap.
        new = engine.shown_choices(turn.reply.ui)
        keep = [c for c in state.get("shown", []) if c not in new]
        turn.state["shown"] = (new + keep)[:60]
        turn.state["last_shown"] = new  # typed text is matched against these only
        await store.save_turn(
            conn, req, said, [m.text for m in turn.reply.messages], turn.answered_by, turn.state
        )
        await _trace(conn, req, turn, hit, steps, started)
    return turn.reply


async def _slots(
    conn: asyncpg.Connection, req: ChatRequest, state: store.State
) -> dict[str, list[str]] | None:
    """Free slots for the booking window, loaded only while a booking or reschedule is open."""
    flow = state.get("flow")
    c = content(req.client_id)
    if not flow or c is None or flow.get("kind") not in ("book", "online", "reschedule"):
        return None
    today, now = flows.ist_now()
    last = today + timedelta(days=c["config"]["bookingWindowDays"])
    mode: Mode = "online" if flow["kind"] == "online" else "in_clinic"
    return await free_slots_range(conn, req.client_id, today, last, mode, today, now, req.session_id)


Step = dict[str, Any]


def _ms(since: float) -> int:
    return round((time.perf_counter() - since) * 1000)


async def _kb(conn: asyncpg.Connection, req: ChatRequest, steps: list[Step]) -> kb.Answer | None:
    """The approved knowledge base match for typed text, with each check noted in steps. Never for
    emergencies or medical questions, which the engine sends to the doctor and the team."""
    text = " ".join((req.payload.text or "").lower().split())
    if req.event != "text" or not text:
        return None
    t = time.perf_counter()
    for name, pattern in (("emergency", understand.EMERGENCY), ("medical", understand.MEDICAL)):
        if pattern.search(text):
            steps.append({"step": name, "result": "matched", "ms": _ms(t)})
            return None
    steps.append({"step": "emergency_medical", "result": "no match", "ms": _ms(t)})
    t = time.perf_counter()
    hit = await kb.search(conn, req.client_id, text)
    result = hit.question if hit else "no match"
    steps.append({"step": "kb_regular", "result": result, "score": hit.score if hit else None, "ms": _ms(t)})
    if hit:
        return hit
    t = time.perf_counter()
    hit, score = await kb.semantic(conn, req.client_id, text)
    result = hit.question if hit else ("model loading" if score is None and not embed.ready() else "no match")
    steps.append({"step": "kb_semantic", "result": result, "score": score, "ms": _ms(t)})
    return hit


async def _trace(
    conn: asyncpg.Connection, req: ChatRequest, turn: engine.Turn, hit: kb.Answer | None, steps: list[Step],
    started: float,
) -> None:  # fmt: skip
    """One row per typed question for the CRM "Bot quality" screen. Typed answers to a form step (a name,
    a date) are not questions and are not traced."""
    if not steps or turn.answered_by == "flow":
        return
    first = steps[0]["step"]
    answered = (
        first
        if first in ("emergency", "medical")
        else {"menu": "rule", "error": "lead"}.get(turn.answered_by, turn.answered_by)
    )
    if answered not in ("emergency", "medical"):
        steps.insert(1, {"step": "rules", "result": "matched" if answered == "rule" else "no match"})
    used = hit if answered == "kb" else None
    await conn.execute(
        """insert into app.rag_traces (clinic_id, session_id, question, answered_by, kb_qa_id, kb_score,
             steps, total_ms) values ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)""",
        req.client_id, req.session_id, (req.payload.text or "")[:500], answered, used.id if used else None,
        used.score if used else None, json.dumps(steps), _ms(started),
    )  # fmt: skip
