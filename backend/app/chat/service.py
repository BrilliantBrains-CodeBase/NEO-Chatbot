"""One chat turn: load the session, work out the reply, save everything, in one transaction."""

from app.chat import engine, store
from app.chat.guard import Clinic
from app.chat.schemas import ChatRequest, ChatResponse
from app.core.db import get_pool


async def handle(req: ChatRequest, clinic: Clinic) -> ChatResponse:
    """Raises store.SessionMismatch when the session belongs to another clinic or visitor."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        state = await store.open_session(conn, req)
        said = store.patient_text(req, state)
        turn = engine.respond(req, state)
        # Recent buttons (newest first, at most 60) so the transcript can show the label of any tap.
        new = engine.shown_choices(turn.reply.ui)
        keep = [c for c in state.get("shown", []) if c not in new]
        turn.state["shown"] = (new + keep)[:60]
        turn.state["last_shown"] = new  # typed text is matched against these only
        await store.save_turn(
            conn, req, said, [m.text for m in turn.reply.messages], turn.answered_by, turn.state
        )
    return turn.reply
