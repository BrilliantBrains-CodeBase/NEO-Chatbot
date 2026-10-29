"""Supabase Auth's admin API, for Team & access only: create a requested login, invite by email, remove a
rejected login, send a password reset. Uses the project's secret key (SUPABASE_SECRET_KEY), server only.
Supabase sends the invite and reset emails itself (its SMTP settings decide the sender).
"""

from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import get_settings


class AdminError(Exception):
    """Supabase refused, or the secret key is not set (the message is shown to staff)."""


async def _call(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    s = get_settings()
    if not s.supabase_secret_key:
        raise AdminError("Team & access needs SUPABASE_SECRET_KEY on the server.")
    headers = {"apikey": s.supabase_secret_key, "Authorization": f"Bearer {s.supabase_secret_key}"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.request(method, s.supabase_url.rstrip("/") + "/auth/v1" + path, json=body,
                                     headers=headers)  # fmt: skip
    except httpx.HTTPError as e:
        raise AdminError(f"Supabase could not be reached: {type(e).__name__}") from None
    if r.status_code >= 300:
        try:
            msg = r.json().get("msg") or r.json().get("message") or r.text
        except ValueError:
            msg = r.text
        raise AdminError(str(msg)[:200])
    return dict(r.json()) if r.content else {}


def _redirect() -> str:
    """Where the emailed link lands (the CRM's Set password page), for Supabase's redirect_to."""
    return quote(get_settings().crm_url.rstrip("/") + "/set-password", safe="")


async def create_user(email: str, password: str, name: str) -> str:
    """A login that can sign in at once (the CRM still refuses it until a role is approved). Its id."""
    user = await _call("POST", "/admin/users", {
        "email": email, "password": password, "email_confirm": True, "user_metadata": {"full_name": name},
    })  # fmt: skip
    return str(user["id"])


async def invite(email: str, name: str) -> str:
    """Emails an invite; the link opens the CRM's Set password page. The new login's id."""
    body = {"email": email, "data": {"full_name": name}}
    user = await _call("POST", f"/invite?redirect_to={_redirect()}", body)
    return str(user["id"])


async def delete_user(user_id: str) -> None:
    await _call("DELETE", f"/admin/users/{user_id}")


async def reset_password(email: str) -> None:
    """Emails a password reset link (to the CRM's Set password page)."""
    await _call("POST", f"/recover?redirect_to={_redirect()}", {"email": email})
