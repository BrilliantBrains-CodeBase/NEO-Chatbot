"""Dashboard → Integrations, JSON only: which outside services are connected and what they did lately.
Keys stay in the backend's settings (.env) and are never sent: only "connected" or not."""

import secrets
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.db import get_pool
from app.crm import calcom, vault
from app.crm import permissions as perm
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm/console", tags=["crm"])


class Integration(BaseModel):
    id: str
    name: str
    does: str  # what it is used for
    state: Literal["connected", "not_connected", "not_built"]
    detail: list[str]  # facts for staff (never a key)
    last: str | None  # the last time it was used (ISO)


@router.get("/{clinic}/integrations", response_model=list[Integration])
async def integrations(
    user: Annotated[Staff, Depends(staff)], clinic: str, request: Request
) -> list[Integration]:
    _manager(user, clinic)
    s, pool = get_settings(), await get_pool()
    own: Any = await pool.fetchrow(
        "select account_name, webhook_id, connected_at from app.calcom_accounts where clinic_id = $1", clinic
    )
    cal: Any = await pool.fetchrow(
        """select count(*) filter (where updated_at > now() - interval '30 days') n, max(updated_at) last
           from app.appointments where clinic_id = $1 and calendar_event_id is not null""",
        clinic,
    )
    sheet: Any = await pool.fetchrow(
        """select count(*) filter (where created_at > now() - interval '7 days') n, max(created_at) last
           from app.lead_events where clinic_id = $1 and kind = 'contact' and data->>'source' = 'meta_ads'""",
        clinic,
    )
    sheets_added = await pool.fetchval("select count(*) from app.lead_sheets where clinic_id = $1", clinic)
    wa = await pool.fetchval("select 1 from app.whatsapp_accounts where clinic_id = $1", clinic)
    gmail = await pool.fetchval("select address from app.email_senders where clinic_id = $1", clinic)
    forms = await pool.fetchrow(
        """select count(*) added, count(*) filter (where active) on_, max(last_seen_at) last,
             (select count(*) from app.lead_form_log where clinic_id = $1 and ok
              and at > now() - interval '7 days') n
           from app.lead_forms where clinic_id = $1""",
        clinic,
    )
    hooks = await pool.fetchrow(
        """select count(*) filter (where direction = 'send') sends,
             count(*) filter (where direction = 'receive') gets,
             (select max(at) from app.webhook_log where clinic_id = $1) last
           from app.webhooks where clinic_id = $1""",
        clinic,
    )
    return [
        Integration(
            id="calcom", name="Cal.com",
            does="Online consults: a Google Meet booking when staff approve them.",
            state="connected" if own or (s.calcom_api_key and s.calcom_event_type_id) else "not_connected",
            detail=[d for d in [
                f"Account: {own['account_name']}" if own else "The clinic's own account is not connected yet",
                ("Bookings sync back: yes" if own["webhook_id"] else
                 "Bookings sync back: set up once the backend is online (https)") if own else "",
                f"{cal['n']} online consults booked in the last 30 days",
            ] if d],
            last=cal["last"].isoformat() if cal["last"] else None,
        ),
        Integration(
            id="sheet", name="Google Sheet leads", does="Meta lead ads: each new row in the clinic's sheet "
            "becomes a lead (source Meta Ads).",
            state="connected" if sheets_added else "not_connected",
            detail=[f"{sheets_added} sheet(s) added", f"{sheet['n']} leads received in the last 7 days"],
            last=sheet["last"].isoformat() if sheet["last"] else None,
        ),
        Integration(
            id="forms", name="Website forms", does="The clinic's own forms on its website and landing pages: "
            "each submission comes straight in as a lead (source Website form).",
            state="connected" if forms["on_"] else "not_connected",
            detail=[f"{forms['added']} form(s) added, {forms['on_']} on",
                    f"{forms['n']} leads received in the last 7 days"],
            last=forms["last"].isoformat() if forms["last"] else None,
        ),
        Integration(
            id="webhooks", name="Webhooks",
            does="Send CRM events (new lead, booking, call back, confirmed) as JSON to another system, and "
            "receive leads as JSON from one.",
            state="connected" if hooks["sends"] or hooks["gets"] else "not_connected",
            detail=[f"{hooks['sends']} sending, {hooks['gets']} receiving"],
            last=hooks["last"].isoformat() if hooks["last"] else None,
        ),
        Integration(
            id="whatsapp", name="WhatsApp (Interakt)", does="Confirmations, reminders and the OTP for Check "
            "my appointment.",
            state="connected" if wa else "not_connected",
            detail=["Interakt connected" if wa else "Connect the clinic's Interakt and set its templates"],
            last=None,
        ),
        Integration(
            id="email", name="Email (Gmail)", does="The clinic's own Gmail: staff login codes now; patient "
            "emails and staff alerts next.",
            state="connected" if gmail else "not_connected",
            detail=[f"Sending from {gmail}" if gmail else "Connect the clinic's Gmail (App password)"],
            last=None,
        ),
    ]  # fmt: skip


def _manager(user: Staff, clinic: str) -> None:
    if not (user.bb_admin or user.roles.get(clinic) == "clinic_manager" or perm.granted(user, clinic)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Integrations are for clinic managers and BB Admin.")


class CalcomKey(BaseModel):
    api_key: str = Field(min_length=10, max_length=300)


@router.post("/{clinic}/integrations/calcom", response_model=list[Integration])
async def connect_calcom(
    user: Annotated[Staff, Depends(staff)], clinic: str, body: CalcomKey, request: Request
) -> list[Integration]:
    """Connects the clinic's own Cal.com: checks the key with Cal.com, keeps it in Vault, and (once the
    backend is online over https) creates the webhook that syncs bookings back. Connecting again replaces
    the key."""
    _manager(user, clinic)
    key = body.api_key.strip()
    try:
        name = await calcom.account(key)
    except calcom.CalcomError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    base = (get_settings().public_url or str(request.base_url)).rstrip("/")
    webhook_id, hook_secret = None, secrets.token_urlsafe(32)
    if base.startswith("https://"):  # Cal.com can only call a backend that is online over https
        try:
            webhook_id = await calcom.add_webhook(key, f"{base}/v1/integrations/calcom/{clinic}", hook_secret)
        except calcom.CalcomError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        old = await conn.fetchrow("select * from app.calcom_accounts where clinic_id = $1", clinic)
        key_id = await vault.save(conn, key, f"calcom key {clinic}")
        hook_id = await vault.save(conn, hook_secret, f"calcom webhook {clinic}") if webhook_id else None
        await conn.execute(
            """insert into app.calcom_accounts (clinic_id, key_secret, webhook_id, webhook_secret,
                 account_name, connected_by) values ($1, $2, $3, $4, $5, $6::uuid)
               on conflict (clinic_id) do update set key_secret = $2, webhook_id = $3, webhook_secret = $4,
                 account_name = $5, connected_by = $6::uuid, connected_at = now()""",
            clinic, key_id, webhook_id, hook_id, name[:120], user.id,
        )  # fmt: skip
        if old:  # the previous key and webhook are replaced
            await _drop_webhook(conn, old)
            await vault.delete(conn, old["key_secret"], old["webhook_secret"])
    return await integrations(user, clinic, request)


@router.delete("/{clinic}/integrations/calcom", response_model=list[Integration])
async def disconnect_calcom(
    user: Annotated[Staff, Depends(staff)], clinic: str, request: Request
) -> list[Integration]:
    """Disconnects the clinic's own Cal.com: its webhook is removed and its secrets deleted from Vault."""
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        old = await conn.fetchrow("delete from app.calcom_accounts where clinic_id = $1 returning *", clinic)
        if old:
            await _drop_webhook(conn, old)
            await vault.delete(conn, old["key_secret"], old["webhook_secret"])
    return await integrations(user, clinic, request)


async def _drop_webhook(conn: Any, row: Any) -> None:
    """Removes our webhook from the clinic's Cal.com (best effort: the account may be gone already)."""
    if not row["webhook_id"]:
        return
    key = await vault.read(conn, row["key_secret"])
    if key:
        try:
            await calcom.remove_webhook(key, row["webhook_id"])
        except calcom.CalcomError:
            pass
