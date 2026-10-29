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
async def _own_pool() -> Any:
    """The canvas looks things up through the shared pool: close it with this test's event loop."""
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
    assert items[0] == {"label": "Call me back", "icon": "phone", "action": "canvas", "value": "m1"}
    assert items[1]["href"] == "https://example.com"  # a link opens at once
    await say(req("button", action="canvas", value="m1"))  # follows the line to the call back block
    await say(req("text", text="Asha Rao"))
    check = await say(req("text", text="9800000123"))
    assert check.messages[-1].text == "May we save your details?"  # the canvas reads back and asks consent
    await say(req("button", action="canvas", value="yes"))
    lead = await tx.fetchrow(
        "select l.source, r.type from app.leads l join app.requests r on r.lead_id = l.id "
        "where l.clinic_id = 'CL99' and l.phone_e164 = '+919800000123'"
    )
    assert lead is not None and (lead["source"], lead["type"]) == ("chatbot", "callback")
