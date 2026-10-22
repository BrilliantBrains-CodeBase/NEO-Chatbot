"""One chat turn: load the session, work out the reply, save everything, in one transaction."""

from app.chat import store
from app.chat.guard import Clinic
from app.chat.schemas import BotMessage, ChatRequest, ChatResponse
from app.core.db import get_pool


async def handle(req: ChatRequest, clinic: Clinic) -> ChatResponse:
    """Raises store.SessionMismatch when the session belongs to another clinic or visitor."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        state = await store.open_session(conn, req)
        said = store.patient_text(req, state)

        # B2: a greeting only. Menus and flows come in B3.
        name = clinic.bot_name.removesuffix(" AI")
        reply = ChatResponse(messages=[BotMessage(text=f"Hi, I'm {name}. How can I help you today?")])

        await store.save_turn(conn, req, said, [m.text for m in reply.messages], "menu", state)
    return reply
