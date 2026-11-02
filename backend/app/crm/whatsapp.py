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

from app.chat import main_template
from app.core.db import get_pool
from app.crm import vault

API = "https://api.interakt.ai/v1/public/message/"
# The messages the CRM sends, and when.
PURPOSES = {
    "request_received": "Request received (a booking or call back from the chat)",
    "inclinic_confirmed": "Appointment booked, in-clinic (sent when staff confirm it in the CRM)",
    "online_confirmed": "Online consult booked (sent when staff confirm it in the CRM)",
    "imported_lead": "Imported lead (sent to each new lead when a manager imports a list)",
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
    "lead_code": "Booking ID (lead code)",
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


async def template_on(clinic: str, purpose: str) -> bool:
    pool = await get_pool()
    saved = await pool.fetchval("select templates from app.whatsapp_accounts where clinic_id = $1", clinic)
    tpl = _obj(_obj(saved).get(purpose))
    return bool(tpl.get("name")) and bool(tpl.get("on", True))


def notify_each(clinic: str, purpose: str, items: list[tuple[str, dict[str, Any]]]) -> None:
    """The template for many patients (an import): one after another in the background, so Interakt is not
    flooded. With no template on for this purpose nothing is sent (and nothing is logged per patient)."""

    async def in_turn() -> None:
        try:
            if not await template_on(clinic, purpose):
                return
        except Exception:
            log.exception("whatsapp: %s for %s", purpose, clinic)
            return
        for phone, data in items:
            await _quiet(clinic, purpose, phone, data)

    task = asyncio.get_running_loop().create_task(in_turn())
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
        body: dict[str, Any] = {
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
        buttons = [b for b in tpl.get("buttons", []) if b]
        if buttons:  # each URL button's {{1}}: what it opens, through /v1/r/
            code = str(data.get("lead_code") or "")
            keys = [f"{clinic}/meet/{code}" if b == "meet" else f"{clinic}/{b}" for b in buttons]
            body["template"]["buttonValues"] = {str(i): [k] for i, k in enumerate(keys)}
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


# ---------- template buttons ----------
# WhatsApp allows only the buttons of the approved template. A "Visit website" button there points to
# <backend>/v1/r/{{1}}; we fill {{1}} with what it opens (the clinic's map, its website, a menu button's link,
# the patient's Meet link), and /v1/r/ sends the patient on. Change a link in the CRM: every button follows.
async def link_options(conn: Any, clinic: str) -> dict[str, str]:
    """What a template button can open: key -> label for staff."""
    out = {
        "map": "Location (Google Maps)",
        "website": "Clinic website",
        "meet": "Google Meet link (the patient's)",
    }
    for node, button, label in await _menu_links(conn, clinic):
        out[f"menu/{node}/{button}"] = f"Menu button: {label}"
    return out


async def _menu_links(conn: Any, clinic: str) -> list[tuple[str, str, str]]:
    """The chat's menu buttons that open a link (Dashboard → Menu buttons), published flow first."""
    flow = await main_template.live_flow(conn, clinic)
    return [
        (n["id"], b["id"], b["label"])
        for n in flow.get("nodes", [])
        for b in (n.get("settings") or {}).get("buttons") or []
        if b.get("action") in ("link", "whatsapp") and str(b.get("value", "")).startswith("https://")
    ]


async def resolve(conn: Any, clinic: str, key: str) -> str | None:
    """The address a button opens (https only), or None."""
    url: Any
    if key == "map":
        url = (await clinic_values(conn, clinic))["maps_link"]
    elif key == "website":
        url = await conn.fetchval("select website from app.clinics where id = $1", clinic)
    elif key.startswith("meet/"):  # the patient's latest online consult
        url = await conn.fetchval(
            """select a.meet_link from app.appointments a join app.leads l on l.id = a.lead_id
               where a.clinic_id = $1 and l.lead_code = $2 and a.meet_link is not null
               order by a.created_at desc limit 1""",
            clinic, key[5:],
        )  # fmt: skip
    elif key.startswith("menu/"):
        _, node, button = (key.split("/") + ["", ""])[:3]
        flow = await main_template.live_flow(conn, clinic)
        url = next(
            (
                b.get("value")
                for n in flow.get("nodes", []) if n["id"] == node
                for b in (n.get("settings") or {}).get("buttons") or [] if b["id"] == button
            ),
            None,
        )  # fmt: skip
    else:
        url = None
    return url if url and str(url).startswith("https://") else None
