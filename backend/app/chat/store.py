"""Chat sessions and transcripts in the database (Redis is Phase 2).

One request = one transaction: open (or create) the session, then save the patient's message, the bot's
reply and the new conversation state. Chat is deleted after 3 days by a database job.
"""

import json
from typing import Any

import asyncpg

from app.chat.schemas import ChatRequest

State = dict[str, Any]


class SessionMismatch(Exception):
    """The session id exists but belongs to another clinic or visitor."""


async def open_session(conn: asyncpg.Connection, req: ChatRequest) -> State:
    """The conversation state for this session; a new session starts empty. Locks the session row
    until the transaction ends, so two messages of one session are handled one after the other."""
    row = await conn.fetchrow(
        "select clinic_id, visitor_id, state from app.chat_sessions where id = $1 for update", req.session_id
    )
    if row is None:
        await conn.execute(
            """insert into app.chat_sessions (id, clinic_id, visitor_id, device, page_url)
               values ($1, $2, $3, $4, $5)""",
            req.session_id,
            req.client_id,
            req.visitor_id,
            req.context.device,
            req.context.page_url,
        )
        return {}
    if row["clinic_id"] != req.client_id or row["visitor_id"] != req.visitor_id:
        raise SessionMismatch
    state: State = json.loads(row["state"])
    return state


def patient_text(req: ChatRequest, state: State) -> str | None:
    """What the patient said, as the CRM transcript shows it. A tap is shown by its button label."""
    p = req.payload
    if req.event == "text" and p.text:
        return f"{p.cc} {p.text}" if p.cc else p.text
    if req.event == "button":
        for choice in state.get("shown", []):
            if choice.get("action") == p.action and choice.get("value") == p.value:
                return str(choice["label"])
        return f"{p.action}: {p.value}" if p.value else p.action
    return None  # start and restart are not messages


async def save_turn(
    conn: asyncpg.Connection,
    req: ChatRequest,
    said: str | None,
    replies: list[str],
    answered_by: str,
    state: State,
) -> None:
    if said:
        await conn.execute(
            """insert into app.chat_messages (session_id, clinic_id, role, text, event)
               values ($1, $2, 'patient', $3, $4)""",
            req.session_id,
            req.client_id,
            said,
            req.event,
        )
    for text in replies:
        await conn.execute(
            """insert into app.chat_messages (session_id, clinic_id, role, text, answered_by)
               values ($1, $2, 'bot', $3, $4)""",
            req.session_id,
            req.client_id,
            text,
            answered_by,
        )
    await conn.execute(
        """update app.chat_sessions set state = $2::jsonb, last_at = now(), device = $3, page_url = $4
           where id = $1""",
        req.session_id,
        json.dumps(state),
        req.context.device,
        req.context.page_url,
    )
