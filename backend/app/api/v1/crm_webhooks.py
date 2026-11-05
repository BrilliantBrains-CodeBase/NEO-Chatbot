"""Dashboard → Integrations → Webhooks (migration 0024), JSON only. "send": CRM events to the clinic's address
(app.crm.webhooks). "receive": a private address an outside system POSTs leads to, as JSON."""

import hmac
import secrets
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.v1.crm_sheets import _lead_from_row
from app.core.config import get_settings
from app.core.db import get_pool
from app.crm import permissions as perm
from app.crm import vault, webhooks
from app.crm.auth import Staff, staff

router = APIRouter(tags=["crm"])


class LogLine(BaseModel):
    event: str
    attempt: int
    ok: bool
    status_code: int | None
    error: str | None
    at: str


class Hook(BaseModel):
    id: str
    direction: Literal["send", "receive"]
    name: str
    url: str | None  # send: their address; receive: our private address (with its key)
    events: list[str]
    active: bool
    log: list[LogLine]  # the last 10 attempts (send)


class NewHook(BaseModel):
    direction: Literal["send", "receive"]
    name: str = Field(min_length=1, max_length=80)
    url: str | None = Field(default=None, max_length=600, pattern=r"^https://\S+$")
    events: list[str] = Field(default=[], max_length=10)


def _manager(user: Staff, clinic: str) -> None:
    if not (user.bb_admin or user.roles.get(clinic) == "clinic_manager" or perm.granted(user, clinic)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Integrations are for admins and Super Admin.")


async def _list(clinic: str, request: Request) -> list[Hook]:
    pool = await get_pool()
    base = (get_settings().public_url or str(request.base_url)).rstrip("/")
    out = []
    async with pool.acquire() as conn:
        for h in await conn.fetch(
            "select * from app.webhooks where clinic_id = $1 order by created_at", clinic
        ):
            url = h["url"]
            if h["direction"] == "receive":
                url = f"{base}/v1/integrations/webhooks/{h['id']}?key={await vault.read(conn, h['secret'])}"
            log = await conn.fetch(
                "select * from app.webhook_log where webhook_id = $1 order by at desc limit 10", h["id"]
            )
            out.append(
                Hook(
                    id=str(h["id"]),
                    direction=h["direction"],
                    name=h["name"],
                    url=url,
                    events=list(h["events"]),
                    active=h["active"],
                    log=[
                        LogLine(
                            event=x["event"],
                            attempt=x["attempt"],
                            ok=x["ok"],
                            status_code=x["status_code"],
                            error=x["error"],
                            at=x["at"].isoformat(),
                        )
                        for x in log
                    ],
                )  # fmt: skip
            )
    return out


@router.get("/crm/console/{clinic}/integrations/webhooks", response_model=list[Hook])
async def hooks(user: Annotated[Staff, Depends(staff)], clinic: str, request: Request) -> list[Hook]:
    _manager(user, clinic)
    return await _list(clinic, request)


@router.get("/crm/console/integrations/webhook-events")
async def hook_events(user: Annotated[Staff, Depends(staff)]) -> dict[str, str]:
    return webhooks.EVENTS


@router.post("/crm/console/{clinic}/integrations/webhooks", response_model=list[Hook])
async def add_hook(
    user: Annotated[Staff, Depends(staff)], clinic: str, body: NewHook, request: Request
) -> list[Hook]:
    _manager(user, clinic)
    if body.direction == "send" and (not body.url or not body.events):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Add the https address and choose its events."
        )
    if any(e not in webhooks.EVENTS for e in body.events):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown event.")
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        secret = await vault.save(conn, secrets.token_urlsafe(32), f"webhook {clinic} {body.name[:40]}")
        await conn.execute(
            """insert into app.webhooks (clinic_id, direction, name, url, events, secret, created_by)
               values ($1, $2, $3, $4, $5, $6, $7::uuid)""",
            clinic, body.direction, body.name.strip(),
            body.url if body.direction == "send" else None,
            body.events if body.direction == "send" else [], secret, user.id,
        )  # fmt: skip
    return await _list(clinic, request)


@router.delete("/crm/console/{clinic}/integrations/webhooks/{hook}", response_model=list[Hook])
async def delete_hook(
    user: Annotated[Staff, Depends(staff)], clinic: str, hook: str, request: Request
) -> list[Hook]:
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        old = await conn.fetchval(
            "delete from app.webhooks where clinic_id = $1 and id = $2::uuid returning secret", clinic, hook
        )
        if old is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found.")
        await vault.delete(conn, old)
    return await _list(clinic, request)


@router.post("/crm/console/{clinic}/integrations/webhooks/{hook}/test", response_model=list[Hook])
async def test_hook(
    user: Annotated[Staff, Depends(staff)], clinic: str, hook: str, request: Request
) -> list[Hook]:
    """Sends a sample event now (and waits for the answer, retries included)."""
    _manager(user, clinic)
    h = await (await get_pool()).fetchrow(
        "select * from app.webhooks where clinic_id = $1 and id = $2::uuid and direction = 'send'",
        clinic,
        hook,
    )
    if h is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook not found.")
    sample = {"event": "test", "clinic": clinic, "lead_code": f"{clinic}-TEST", "name": "Test Patient"}
    await webhooks.send(h["id"], h["url"], h["secret"], clinic, "test", sample)
    return await _list(clinic, request)


SOURCES = ("meta_ads", "google_ads", "manual", "whatsapp", "referral", "walk_in", "phone_call")
# Keys an outside system may send; any other key is kept in the lead's notes.
RECEIVE = ("name", "phone", "email", "city", "treatment", "campaign", "ad_name", "notes", "date")


@router.post("/integrations/webhooks/{hook}")
async def receive(hook: str, key: str, body: dict[str, Any]) -> dict[str, str]:
    """An outside system sends one lead as JSON: {"name", "phone", "email", "treatment", "campaign", "notes",
    ...}. It becomes a CRM lead (one lead per phone, cleaned the CRM's way); answers its lead code."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        h = await conn.fetchrow(
            "select * from app.webhooks where id::text = $1 and direction = 'receive' and active", hook
        )
        real = await vault.read(conn, h["secret"]) if h else None
        if h is None or not real or not hmac.compare_digest(real, key):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This webhook address is not valid.")
        clinic = await conn.fetchrow(
            "select id, lead_assignment from app.clinics where id = $1 and active", h["clinic_id"]
        )
        values = {str(k): str(v) for k, v in body.items() if v not in (None, "")}
        source = str(body.get("source") or "manual")
        if source not in SOURCES:
            source = "manual"
        tab = {"tab": h["name"], "mapping": {k: k for k in RECEIVE if k in values}, "date_order": None}
        try:
            code = await _lead_from_row(conn, clinic, h["name"], tab, {"values": values}, source)
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    return {"lead_code": code}
