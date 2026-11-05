"""Staff alerts that cannot wait: when a patient uses emergency words in the chatbot, the clinic's active
Clinic Managers are emailed at once, whether or not the patient gave a phone number. It runs in the background
during the chat turn, so it needs no worker. The email names the lead, never what the patient wrote.
"""

import asyncio
import logging
import time
from typing import Any

from app.core.config import get_settings
from app.core.db import get_pool
from app.crm import email

log = logging.getLogger(__name__)

KEEP_S = 1800  # one chat raises one alert in this time, however many messages repeat the words
_raised: dict[tuple[str, bool], float] = {}
_running: set[asyncio.Task[None]] = set()  # kept until done (asyncio holds tasks weakly)


def first_time(session_id: str, has_phone: bool) -> bool:
    """False when this chat already raised this alert. A phone number given later counts as new: staff can
    now call back."""
    now = time.monotonic()
    for key in [k for k, at in _raised.items() if now - at > KEEP_S]:
        del _raised[key]
    if (session_id, has_phone) in _raised:
        return False
    _raised[session_id, has_phone] = now
    return True


async def managers(conn: Any, clinic: str) -> list[str]:
    """The emails of the clinic's active Clinic Managers."""
    rows = await conn.fetch(
        """select distinct p.email from app.user_clinics uc join app.profiles p on p.id = uc.user_id
           where uc.clinic_id = $1 and uc.role = 'clinic_manager' and uc.active and p.active
             and nullif(p.email, '') is not null order by 1""",
        clinic,
    )
    return [r["email"] for r in rows]


def emergency_email(clinic_name: str, lead_code: str | None) -> tuple[str, str]:
    """The subject and text. No patient name, number or message: an inbox is not the place for them."""
    link = get_settings().crm_url.rstrip("/") + "/inbox?tab=callback"
    who = (
        f"Lead {lead_code} is waiting as an urgent call back. Call them now:\n{link}"
        if lead_code
        else "They did not give a phone number, so there is no one to call back yet."
    )
    return (
        f"Emergency in the {clinic_name} chatbot",
        f"A patient raised an emergency in the {clinic_name} chatbot and was shown the emergency message."
        f"\n\n{who}",
    )


async def _send(clinic: str, lead_code: str | None) -> None:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            to = await managers(conn, clinic)
            name = await conn.fetchval("select name from app.clinics where id = $1", clinic)
        if not to:
            log.warning("emergency in %s: no active Clinic Manager to email", clinic)
            return
        subject, text = emergency_email(name, lead_code)
        for address in to:
            try:
                await email.send(clinic, address, subject, text, "emergency_alert")
            except email.EmailError:
                pass  # logged already (email_log), and the next manager may still get it
    except Exception:
        log.exception("emergency alert for %s", clinic)


def emergency(clinic: str, lead_code: str | None) -> None:
    """Emails the managers in the background (never raises, never delays the patient's reply)."""
    task = asyncio.get_running_loop().create_task(_send(clinic, lead_code))
    _running.add(task)
    task.add_done_callback(_running.discard)
