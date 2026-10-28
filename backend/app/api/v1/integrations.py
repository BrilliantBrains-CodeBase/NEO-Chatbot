"""Leads from outside the chatbot (JSON only).

POST /v1/integrations/sheet-leads: a Google Sheet that Meta lead ads fill sends its rows here (an Apps Script
in the sheet, see docs/google-sheet-leads.gs). Each row becomes a New lead with source Meta Ads, or updates
the lead it was sent as before (the code the script wrote in the sheet's CRM column) or the lead with the
same phone. Protected by SHEET_WEBHOOK_SECRET."""

import hashlib
import hmac
import json
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.chat.leads import _assignee
from app.core.config import get_settings
from app.core.db import get_pool
from app.crm import calcom, vault

router = APIRouter(prefix="/integrations", tags=["integrations"])


class SheetRow(BaseModel):
    clinic: str = Field(pattern=r"^CL\d{2}$")
    secret: str = Field(max_length=200)
    sheet: str = Field(default="", max_length=200)  # the sheet's name, for the timeline
    row_number: int = Field(default=0, ge=0)
    lead_code: str | None = Field(default=None, max_length=20)  # from the CRM column when sent before
    row: dict[str, Any]  # header -> cell value, as in the sheet


class SheetResult(BaseModel):
    lead_code: str
    created: bool


# Meta's column names (and common variants) for the fields a lead has; everything else goes in the note.
NAME = ("full_name", "full name", "name")
PHONE = ("phone_number", "phone number", "phone", "mobile", "mobile_number", "whatsapp_number")
EMAIL = ("email", "email_address", "e-mail")
CAMPAIGN = ("campaign_name", "campaign")
SKIP = {"id", "created_time", "ad_id", "adset_id", "campaign_id", "form_id", "is_organic", "platform", "crm"}


def _pick(row: dict[str, str], keys: tuple[str, ...]) -> str:
    return next((row[k] for k in keys if row.get(k)), "")


def _phone(raw: str) -> tuple[str, str] | None:
    """Meta writes phones like "p:+919876543210". Returns (E.164, country code) or None."""
    digits = re.sub(r"\D", "", raw)
    if re.fullmatch(r"[6-9]\d{9}", digits):
        return "+91" + digits, "+91"
    if re.fullmatch(r"91[6-9]\d{9}", digits):
        return "+" + digits, "+91"
    if raw.strip().lstrip("p:").startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits, ""
    return None


@router.post("/sheet-leads", response_model=SheetResult)
async def sheet_lead(body: SheetRow) -> SheetResult:
    secret = get_settings().sheet_webhook_secret
    if not secret or not hmac.compare_digest(body.secret, secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong secret.")
    row = {str(k).strip().lower(): str(v).strip() for k, v in body.row.items() if str(v).strip()}
    name = " ".join(_pick(row, NAME).split())[:100]
    phone = _phone(_pick(row, PHONE))
    email = _pick(row, EMAIL).lower()
    email = email if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", email) else ""
    if len(name) < 2 or not (phone or email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Row needs a name and a phone or email.")
    campaign = (_pick(row, CAMPAIGN) or row.get("ad_name", ""))[:100] or None
    known = set(NAME + PHONE + EMAIL + CAMPAIGN) | SKIP
    answers = {k: v for k, v in row.items() if k not in known}  # the form's own questions, ad and form name
    e164, cc = phone or (None, "")
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        clinic = await conn.fetchrow(
            "select id, timezone, slot_minutes, lead_assignment from app.clinics where id = $1 and active",
            body.clinic,
        )
        if clinic is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown clinic.")
        lead = None
        if body.lead_code:  # sent before: update that lead, even if the phone was corrected
            lead = await conn.fetchrow(
                """select id, lead_code from app.leads
                   where lead_code = $1 and clinic_id = $2 and deleted_at is null""",
                body.lead_code, body.clinic,
            )  # fmt: skip
        if lead is None:
            lead = await conn.fetchrow(
                """select id, lead_code from app.leads where clinic_id = $1 and deleted_at is null
                   and (phone_e164 = $2 or ($2::text is null and email = $3)) for update""",
                body.clinic, e164, email or None,
            )  # fmt: skip
        data = {"via": "google_sheet", "sheet": body.sheet, "row": body.row_number, "answers": answers}
        if lead is not None:
            await conn.execute(
                """update app.leads set full_name = $2, phone_e164 = coalesce($3, phone_e164),
                     phone_cc = coalesce(nullif($4, ''), phone_cc), email = coalesce($5, email),
                     campaign = coalesce($6, campaign), contact_count = contact_count + 1,
                     last_contact_at = now(), updated_at = now()
                   where id = $1""",
                lead["id"], name, e164, cc, email or None, campaign,
            )  # fmt: skip
            created = False
        else:
            lead = await conn.fetchrow(
                """insert into app.leads (clinic_id, full_name, phone_e164, phone_cc, email, source, campaign,
                     assigned_to, notes)
                   values ($1, $2, $3, nullif($4, ''), $5, 'meta_ads', $6, $7, $8) returning id, lead_code""",
                body.clinic, name, e164, cc, email or None, campaign, await _assignee(conn, clinic),
                "\n".join(f"{k}: {v}" for k, v in answers.items())[:2000],
            )  # fmt: skip
            created = True
        await conn.execute(
            """insert into app.lead_events (clinic_id, lead_id, kind, data)
               values ($1, $2, 'contact', $3::jsonb)""",
            body.clinic, lead["id"], json.dumps({"source": "meta_ads", **data}),
        )  # fmt: skip
    return SheetResult(lead_code=lead["lead_code"], created=created)


# ---------- Cal.com: bookings changed in the clinic's Cal.com come back to the CRM ----------
@router.post("/calcom/{clinic}")
async def calcom_event(clinic: str, request: Request) -> dict[str, str]:
    """Cal.com's webhook (created when the clinic connected its Cal.com). Signed with the webhook's secret
    (Vault): X-Cal-Signature-256 = HMAC-SHA256 of the body. A booking cancelled or moved in Cal.com updates
    its appointment; a booking made by the CRM is already known (the same uid)."""
    raw = await request.body()
    pool = await get_pool()
    async with pool.acquire() as conn:
        secret_id = await conn.fetchval(
            "select webhook_secret from app.calcom_accounts where clinic_id = $1", clinic
        )
        secret = await vault.read(conn, secret_id)
    sent = request.headers.get("x-cal-signature-256", "")
    good = hmac.new((secret or "").encode(), raw, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(sent, good):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong signature.")
    event = json.loads(raw or b"{}")
    kind, p = event.get("triggerEvent", ""), event.get("payload") or {}
    uid = str(p.get("uid") or "")
    async with pool.acquire() as conn, conn.transaction():
        if kind == "BOOKING_CANCELLED":
            done = await conn.execute(
                """update app.appointments set status = 'cancelled', updated_at = now()
                   where clinic_id = $1 and calendar_event_id = $2 and status in ('pending', 'confirmed')""",
                clinic, uid,
            )  # fmt: skip
            return {"ok": "cancelled" if done.endswith(" 1") else "not ours"}
        if kind == "BOOKING_RESCHEDULED":
            old = str(p.get("rescheduleUid") or p.get("fromReschedule") or "")
            link = (p.get("videoCallData") or {}).get("url") or (p.get("metadata") or {}).get("videoCallUrl")
            done = await conn.execute(
                """update app.appointments set slot = tstzrange($3::timestamptz, $4::timestamptz, '[)'),
                     calendar_event_id = $5, meet_link = coalesce($6, meet_link), updated_at = now()
                   where clinic_id = $1 and calendar_event_id = $2""",
                clinic, old, _time(p.get("startTime")), _time(p.get("endTime")), uid, link,
            )  # fmt: skip
            return {"ok": "moved" if done.endswith(" 1") else "not ours"}
        if kind == "BOOKING_CREATED" and not (p.get("metadata") or {}).get("lead"):
            # Made in Cal.com, not by the chatbot / CRM (every CRM booking carries its lead code): cancelled,
            # and Cal.com's own email tells the patient why.
            key = await vault.read(
                conn,
                await conn.fetchval(
                    "select key_secret from app.calcom_accounts where clinic_id = $1", clinic
                ),
            )
            try:
                await calcom.cancel(
                    uid, "Please book your online consultation through the clinic's website chat.",
                    calcom.Account(key=key),
                )  # fmt: skip
            except calcom.CalcomError:
                return {"ok": "could not cancel"}
            return {"ok": "cancelled: not booked through the chat or CRM"}
    return {"ok": "ignored"}  # a booking the CRM made (its lead code is on it): already known


def _time(text: Any) -> datetime | None:
    """Cal.com's times ("2030-01-02T05:00:00Z") as real times."""
    return datetime.fromisoformat(str(text).replace("Z", "+00:00")) if text else None
