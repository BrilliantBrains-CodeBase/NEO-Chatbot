"""Sending CRM events to a clinic's webhooks (migration 0024), in JSON, in the background: a slow or failing
outside system never slows the chat or the CRM. Each POST is signed (X-Neo-Signature: sha256=HMAC of the body
with the webhook's secret from Vault), retried up to 3 times (after 2, 10 and 30 seconds) and every attempt is
logged for staff (Dashboard → Integrations → Webhooks).
"""

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.db import get_pool
from app.crm import vault

EVENTS = {
    "lead_new": "New lead",
    "booking_request": "Booking request",
    "callback_request": "Call back request",
    "appointment_confirmed": "Appointment confirmed",
}
WAITS = (2, 10, 30)  # seconds before each retry
log = logging.getLogger(__name__)
_running: set[asyncio.Task[None]] = set()  # kept until done (asyncio holds tasks weakly)


def emit(clinic: str, event: str, data: dict[str, Any]) -> None:
    """Sends the event to the clinic's webhooks for it, in the background (never raises)."""
    task = asyncio.get_running_loop().create_task(_send_all(clinic, event, data))
    _running.add(task)
    task.add_done_callback(_running.discard)


async def _send_all(clinic: str, event: str, data: dict[str, Any]) -> None:
    try:
        pool = await get_pool()
        hooks = await pool.fetch(
            """select id, url, secret from app.webhooks where clinic_id = $1 and direction = 'send' and active
               and $2 = any(events)""",
            clinic, event,
        )  # fmt: skip
        body = {"event": event, "clinic": clinic, "at": datetime.now(UTC).isoformat()} | data
        await asyncio.gather(*(send(h["id"], h["url"], h["secret"], clinic, event, body) for h in hooks))
    except Exception:  # a webhook must never break what triggered it
        log.exception("webhooks: %s for %s", event, clinic)


async def send(hook: Any, url: str, secret_id: Any, clinic: str, event: str, body: dict[str, Any]) -> bool:
    """One webhook: up to 4 attempts, each logged. True when the outside system answered 2xx."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        secret = await vault.read(conn, secret_id) or ""
    raw = json.dumps(body, default=str).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Neo-Signature": sig, "X-Neo-Event": event}
    for attempt in range(1, len(WAITS) + 2):
        code, error = None, None
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                res = await client.post(url, content=raw, headers=headers)
            code = res.status_code
            if not 200 <= code < 300:
                error = res.text[:300] or f"HTTP {code}"
        except httpx.HTTPError as e:
            error = f"{type(e).__name__}: {e}"[:300]
        await pool.execute(
            """insert into app.webhook_log (webhook_id, clinic_id, event, attempt, ok, status_code, error)
               values ($1, $2, $3, $4, $5, $6, $7)""",
            hook, clinic, event, attempt, error is None, code, error,
        )  # fmt: skip
        if error is None:
            return True
        if attempt <= len(WAITS):
            await asyncio.sleep(WAITS[attempt - 1])
    return False
