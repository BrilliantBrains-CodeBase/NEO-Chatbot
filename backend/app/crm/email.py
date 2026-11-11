"""Email through Gmail (migration 0030): each clinic's own Gmail, and the BB Gmail for Super Admin login codes
and as the fallback. Gmail address + Google App password (kept in Supabase Vault), sent through
smtp.gmail.com with Python's own smtplib (in a thread, never blocking the server). Every email is logged,
sent or not.
"""

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

from app.core.db import get_pool
from app.crm import failures, vault

HOST, PORT = "smtp.gmail.com", 465


class EmailError(Exception):
    """No Gmail connected, or Gmail refused (the message is shown to staff)."""


async def sender(conn: Any, clinic: str | None) -> Any:
    """The clinic's Gmail, else the BB Gmail (clinic None: the BB Gmail only)."""
    if clinic:
        row = await conn.fetchrow("select * from app.email_senders where clinic_id = $1", clinic)
        if row:
            return row
    return await conn.fetchrow("select * from app.email_senders where clinic_id is null")


def _send(address: str, password: str, from_name: str, to: str, subject: str, text: str) -> None:
    msg = EmailMessage()
    msg["From"] = f"{from_name} <{address}>" if from_name else address
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    with smtplib.SMTP_SSL(HOST, PORT, context=ssl.create_default_context(), timeout=20) as smtp:
        smtp.login(address, password)
        smtp.send_message(msg)


async def send(clinic: str | None, to: str, subject: str, text: str, kind: str) -> str:
    """Sends now from the clinic's Gmail (or the BB Gmail) and logs it: the Gmail it went from. EmailError
    when it was not sent."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await sender(conn, clinic)
        password = await vault.read(conn, row["secret"]) if row else None
    error = None
    if not row or not password:
        error = "No Gmail is connected (Integrations → Email, or the BB Gmail in Login & security)."
    else:
        try:
            await asyncio.to_thread(_send, row["address"], password, row["from_name"], to, subject, text)
        except smtplib.SMTPAuthenticationError:
            error = "Gmail refused the App password. Create a new App password and connect again."
        except (smtplib.SMTPException, OSError) as e:
            error = f"Gmail could not send: {type(e).__name__}"
    await pool.execute(
        "insert into app.email_log (clinic_id, to_email, kind, ok, error) values ($1, $2, $3, $4, $5)",
        clinic, to, kind, error is None, error,  # under the clinic it was for, even from the BB Gmail
    )  # fmt: skip
    if error:
        if kind != "test":  # someone testing already sees the answer
            await failures.report(clinic, "Email")
        raise EmailError(error)
    return str(row["address"])
