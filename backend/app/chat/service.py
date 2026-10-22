"""One chat turn: load the session, work out the reply, save everything, in one transaction."""

from datetime import timedelta

import asyncpg

from app.chat import engine, flows, leads, store
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
        turn = engine.respond(req, state, await _slots(conn, req, state))
        if turn.completed:
            try:
                async with conn.transaction():  # a savepoint: a taken slot undoes the save, not the turn
                    await leads.save_completed(conn, req, turn.completed)
            except leads.SlotTaken:
                again = {"flow": turn.completed}
                turn = engine.slot_taken(req, turn.completed, await _slots(conn, req, again))
        # Recent buttons (newest first, at most 60) so the transcript can show the label of any tap.
        new = engine.shown_choices(turn.reply.ui)
        keep = [c for c in state.get("shown", []) if c not in new]
        turn.state["shown"] = (new + keep)[:60]
        turn.state["last_shown"] = new  # typed text is matched against these only
        await store.save_turn(
            conn, req, said, [m.text for m in turn.reply.messages], turn.answered_by, turn.state
        )
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
    return await free_slots_range(conn, req.client_id, today, last, mode, today, now)
