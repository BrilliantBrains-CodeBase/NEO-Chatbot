"""Invite and password reset emails for staff. Supabase makes the one-time link (app.crm.supabase_admin); it
is emailed from the clinic's Gmail, else the BB Gmail (app.crm.email). When neither can send, the link is
handed back to the person who asked, to pass on themselves (Copy link in Team).
"""

from pydantic import BaseModel

from app.core.config import get_settings
from app.crm import email


class Sent(BaseModel):
    """How the email went, shown in Team after an invite or a reset."""

    to: str
    by: str | None  # the Gmail it went from; None: not sent
    error: str | None
    link: str | None  # only when it was not sent: the person who asked passes it on (it works once)


def _sign_in() -> str:
    return get_settings().crm_url.rstrip("/") + "/sign-in"


def invite_text(name: str, role: str, where: str, link: str) -> tuple[str, str]:
    """Subject and text of an invite. `where`: the clinic names, or "all clinics" for Super Admin."""
    subject = f"You've been added to {where} on NEO CRM"
    text = (
        f"Hi {name},\n\n"
        f"You have been added to {where} on NEO CRM as {role}.\n\n"
        f"Set your password here:\n{link}\n\n"
        f"Then sign in with this email at {_sign_in()}\n\n"
        "The link works once. If it has expired, ask your admin to send a new one.\n"
        "If you were not expecting this email, you can ignore it."
    )
    return subject, text


def reset_text(name: str, link: str) -> tuple[str, str]:
    subject = "Set your NEO CRM password"
    text = (
        f"Hi {name},\n\n"
        "A link to set your NEO CRM password was asked for.\n\n"
        f"Set your password here:\n{link}\n\n"
        f"Then sign in at {_sign_in()}\n\n"
        "The link works once. If you did not ask for this, you can ignore this email: "
        "your password stays the same."
    )
    return subject, text


async def deliver(clinic: str | None, to: str, subject: str, text: str, link: str, kind: str) -> Sent:
    """Sends it (logged in email_log under the clinic); never raises, so the invite or reset still stands."""
    try:
        by = await email.send(clinic, to, subject, text, kind)
    except email.EmailError as e:
        return Sent(to=to, by=None, error=str(e), link=link)
    return Sent(to=to, by=by, error=None, link=None)
