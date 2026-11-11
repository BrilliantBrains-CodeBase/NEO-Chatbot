"""Supabase Auth's admin API, for Team & access only: create a requested login, invite by email, remove a
rejected login, send a password reset. Uses the project's secret key (SUPABASE_SECRET_KEY), server only.
Supabase only makes the invite and reset links (it sends nothing): app.crm.staff_email emails them from the
clinic's Gmail or the BB Gmail.
"""

from typing import Any

import httpx

from app.core.config import get_settings


class AdminError(Exception):
    """Supabase refused, or the secret key is not set (the message is shown to staff)."""


async def _call(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    s = get_settings()
    if not s.supabase_secret_key:
        raise AdminError("Team needs SUPABASE_SECRET_KEY on the server.")
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
    """Where the emailed link lands: the CRM's Set password page (must be in Supabase's Redirect URLs)."""
    return get_settings().crm_url.rstrip("/") + "/set-password"


async def _link(kind: str, email: str, name: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"type": kind, "email": email, "redirect_to": _redirect()}
    if name:
        body["data"] = {"full_name": name}
    return await _call("POST", "/admin/generate_link", body)


async def create_user(email: str, password: str, name: str) -> str:
    """A login that can sign in at once (the CRM still refuses it until a role is approved). Its id."""
    user = await _call("POST", "/admin/users", {
        "email": email, "password": password, "email_confirm": True, "user_metadata": {"full_name": name},
    })  # fmt: skip
    return str(user["id"])


async def invite(email: str, name: str) -> tuple[str, str]:
    """A new login and its one-time link to the CRM's Set password page: (login id, link). Nothing is sent."""
    made = await _link("invite", email, name)
    return str(made["id"]), str(made["action_link"])


async def delete_user(user_id: str) -> None:
    await _call("DELETE", f"/admin/users/{user_id}")


async def reset_password(email: str) -> str:
    """A one-time link to set a new password (the CRM's Set password page). Nothing is sent."""
    return str((await _link("recovery", email))["action_link"])


async def invite_again(email: str) -> str:
    """A fresh invite link for someone who has not set a password yet (the old link stops working). Supabase
    refuses an invite once the email is confirmed: then a password link, which opens the same page."""
    try:
        return str((await _link("invite", email))["action_link"])
    except AdminError:
        return await reset_password(email)
