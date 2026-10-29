"""Who is calling the CRM API. Staff sign in with Supabase Auth in the browser (email and password); every CRM
request carries that sign-in token. Here the token is checked against Supabase's public signing keys, and the
person must have an active profile with at least one active clinic role. A valid password alone is not
enough: people waiting for approval, or disabled, get 403.
"""

import asyncio
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Header, HTTPException, status

from app.core.config import get_settings
from app.core.db import get_pool

log = logging.getLogger(__name__)

ROLE_LABEL = {
    "bb_admin": "BB Admin",
    "clinic_manager": "Clinic Manager",
    "front_desk": "Front Desk",
    "doctor": "Doctor",
}
NO_ACCESS = "Your account has no CRM access yet. Your clinic manager or BB Admin must approve it."
# 2-step login (migration 0031): the CRM shows its "Enter the code" page on this exact message.
CODE_NEEDED = "Enter the sign-in code sent to your email."


@dataclass(frozen=True)
class Staff:
    id: str
    name: str
    email: str
    roles: dict[str, str]  # clinic id -> role
    bb_admin: bool  # sees and manages every clinic
    session: str = ""  # Supabase's id of this sign-in (2-step login marks it verified)


@lru_cache
def _keys() -> jwt.PyJWKClient:
    url = get_settings().supabase_url.rstrip("/")
    return jwt.PyJWKClient(f"{url}/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=3600)


def verify(token: str) -> dict[str, Any]:
    """The token's claims, if Supabase signed it for a signed-in user and it has not expired."""
    issuer = get_settings().supabase_url.rstrip("/") + "/auth/v1"
    key = _keys().get_signing_key_from_jwt(token).key
    claims: dict[str, Any] = jwt.decode(
        token, key, algorithms=["ES256", "RS256"], audience="authenticated", issuer=issuer,
        leeway=30,  # a few seconds of clock difference between this server and Supabase
    )  # fmt: skip
    return claims


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, message, headers={"WWW-Authenticate": "Bearer"})


async def staff(authorization: str = Header(default="")) -> Staff:
    """FastAPI dependency for every CRM route: the signed-in staff member, or 401 / 403. When 2-step login is
    on for one of their roles, this sign-in's emailed code must have been verified (else 403 CODE_NEEDED)."""
    user = await signed_in(authorization)
    pool = await get_pool()
    row = await pool.fetchrow(
        """select (select two_step_roles from app.platform where id = 1) roles,
             exists (select 1 from app.login_sessions
                     where session_id::text = $1 and user_id::text = $2) ok""",
        user.session, user.id,
    )  # fmt: skip
    needed = set(row["roles"] or []) & set(user.roles.values()) if row else set()
    if needed and not row["ok"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, CODE_NEEDED)
    return user


async def signed_in(authorization: str = Header(default="")) -> Staff:
    """The password step only (valid sign-in, approved access): for sending and checking the 2-step code."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Sign in to use the CRM")
    try:
        # The signing keys are fetched over the network (cached for an hour): off the event loop.
        claims = await asyncio.to_thread(verify, token)
    except jwt.PyJWTError as e:
        log.warning("CRM token rejected: %s: %s", type(e).__name__, e)
        raise _unauthorized("Your sign-in has expired. Please sign in again.") from None
    pool = await get_pool()
    async with pool.acquire() as conn:
        profile = await conn.fetchrow(
            "select id, full_name, email, active from app.profiles where id = $1", claims["sub"]
        )
        roles = await conn.fetch(
            "select clinic_id, role from app.user_clinics where user_id = $1 and active", claims["sub"]
        )
    if profile is None or not profile["active"] or not roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NO_ACCESS)
    by_clinic = {r["clinic_id"]: r["role"] for r in roles}
    return Staff(
        id=str(profile["id"]),
        name=profile["full_name"],
        email=profile["email"],
        roles=by_clinic,
        bb_admin="bb_admin" in by_clinic.values(),
        session=str(claims.get("session_id") or ""),
    )
