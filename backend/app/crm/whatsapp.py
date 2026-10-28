"""WhatsApp messages through the clinic's own Interakt account (migration 0025). WhatsApp lets a business
write first only with a template the clinic had approved in Interakt; for each message the Dashboard keeps
that template's name, language and what fills each blank ({{1}}, {{2}} ...). Sent in the background (never
slows the chat or the CRM); every message is logged, sent or not.
"""

import asyncio
import json
import logging
import re
from typing import Any

import httpx

from app.core.db import get_pool
from app.crm import vault

API = "https://api.interakt.ai/v1/public/message/"
# The messages the CRM sends, and when.
PURPOSES = {
    "request_received": "Request received (a booking or call back from the chat)",
    "inclinic_confirmed": "In-clinic appointment confirmed (date, time, doctor, address, map)",
    "online_confirmed": "Online consult confirmed (date, time, Google Meet link)",
    "reminder": "Reminder before the appointment",
    "otp": "OTP (Check my appointment)",
}
# What can fill a template's blanks.
VALUES = {
    "name": "Patient name",
    "date": "Date",
    "time": "Time",
    "doctor": "Doctor",
    "treatment": "Treatment",
    "clinic_name": "Clinic name",
    "address": "Clinic address",
    "maps_link": "Map link",
    "clinic_phone": "Clinic phone",
    "meet_link": "Google Meet link",
    "lead_code": "Lead code",
    "otp": "OTP code",
}
log = logging.getLogger(__name__)
_running: set[asyncio.Task[Any]] = set()


class WhatsAppError(Exception):
    """Interakt refused or could not be reached (the message is shown to staff)."""


def _obj(v: Any) -> dict[str, Any]:
    return dict(json.loads(v) if isinstance(v, str) else v or {})


def notify(clinic: str, purpose: str, phone: str | None, data: dict[str, Any]) -> None:
    """Sends the clinic's template for this purpose to the patient, in the background (never raises)."""
    if not phone:
        return
    task = asyncio.get_running_loop().create_task(_quiet(clinic, purpose, phone, data))
    _running.add(task)
    task.add_done_callback(_running.discard)


async def _quiet(clinic: str, purpose: str, phone: str, data: dict[str, Any]) -> None:
    try:
        await send(clinic, purpose, phone, data)
    except WhatsAppError:
        pass  # logged already
    except Exception:
        log.exception("whatsapp: %s for %s", purpose, clinic)


async def clinic_values(conn: Any, clinic: str) -> dict[str, str]:
    """The clinic's name, address, map link and phone (Clinic info → Contact & hours, published or draft)."""
    row = await conn.fetchrow(
        """select c.name, coalesce(nullif(s.published->'contact', 'null'::jsonb), s.draft->'contact') contact
           from app.clinics c left join app.clinic_settings s on s.clinic_id = c.id where c.id = $1""",
        clinic,
    )
    contact = _obj(row["contact"]) if row else {}
    return {
        "clinic_name": row["name"] if row else "",
        "address": ", ".join(x for x in (contact.get("address"), contact.get("landmark")) if x),
        "maps_link": contact.get("maps_link") or "",
        "clinic_phone": contact.get("phone") or "",
    }


def _number(phone: str) -> tuple[str, str]:
    """("+91", "9876543210") from "+91 98765 43210", "919876543210" or "9876543210"."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10 or (digits.startswith("91") and len(digits) == 12):
        return "+91", digits[-10:]
    return "+" + digits[:-10], digits[-10:]


async def send(clinic: str, purpose: str, phone: str, data: dict[str, Any]) -> None:
    """Sends now (and logs). WhatsAppError when the clinic has no Interakt, no template for this, or
    Interakt refuses."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        acc = await conn.fetchrow(
            "select key_secret, templates from app.whatsapp_accounts where clinic_id = $1", clinic
        )
        key = await vault.read(conn, acc["key_secret"]) if acc else None
        values = await clinic_values(conn, clinic) | {k: str(v) for k, v in data.items() if v is not None}
    tpl = _obj(_obj(acc["templates"] if acc else {}).get(purpose))
    cc, number = _number(phone)
    error = None
    if not key:
        error = "WhatsApp (Interakt) is not connected."
    elif not tpl.get("name") or not tpl.get("on", True):
        error = f"No template is set (or it is off) for: {PURPOSES.get(purpose, purpose)}."
    else:
        body = {
            "countryCode": cc,
            "phoneNumber": number,
            "callbackData": str(data.get("lead_code") or purpose),
            "type": "Template",
            "template": {
                "name": tpl["name"],
                "languageCode": tpl.get("language") or "en",
                "bodyValues": [values.get(v, "") or "-" for v in tpl.get("values", [])],
            },
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(API, json=body, headers={"Authorization": f"Basic {key}"})
            if r.status_code >= 300:
                error = f"Interakt: {r.text[:300] or r.status_code}"
        except httpx.HTTPError as e:
            error = f"Interakt could not be reached: {type(e).__name__}"
    await pool.execute(
        "insert into app.whatsapp_log (clinic_id, purpose, to_phone, ok, error) values ($1, $2, $3, $4, $5)",
        clinic, purpose, f"{cc} {number}", error is None, error,
    )  # fmt: skip
    if error:
        raise WhatsAppError(error)
