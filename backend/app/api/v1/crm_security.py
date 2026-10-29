"""Dashboard → Login & security (migration 0029), JSON only. BB Admin only.

Main BB Admin: one email that always has full BB Admin power over every clinic. Setting it gives that person
an active BB Admin role (so the backend and the database's own rules agree); Team & access never disables,
removes or demotes them. Only the main BB Admin changes it; any BB Admin sets the first one.
"""

import hashlib
import hmac
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.core.db import get_pool
from app.crm import email
from app.crm.auth import Staff, signed_in, staff

router = APIRouter(prefix="/crm/security", tags=["crm"])


class MainAdmin(BaseModel):
    email: str | None  # None: not set yet
    is_me: bool
    can_change: bool  # the main BB Admin, or any BB Admin while none is set


class NewMain(BaseModel):
    email: str = Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


async def main_email() -> str | None:
    """The main BB Admin's email, if one is set."""
    found = await (await get_pool()).fetchval("select main_bb_email from app.platform where id = 1")
    return str(found) if found else None


def _bb(user: Staff) -> None:
    if not user.bb_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Login & security is for BB Admin.")


async def _state(user: Staff) -> MainAdmin:
    main = await main_email()
    me = user.email.lower()
    return MainAdmin(email=main, is_me=main == me, can_change=main in (None, me))


@router.get("/main-admin", response_model=MainAdmin)
async def get_main(user: Annotated[Staff, Depends(staff)]) -> MainAdmin:
    _bb(user)
    return await _state(user)


@router.put("/main-admin", response_model=MainAdmin)
async def set_main(user: Annotated[Staff, Depends(staff)], body: NewMain) -> MainAdmin:
    """Hands full control to this email (an existing, active login), and makes sure it is BB Admin."""
    _bb(user)
    if not (await _state(user)).can_change:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the main BB Admin can change the main BB Admin.")
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        person = await conn.fetchval("select id from app.profiles where email = $1 and active", body.email)
        if person is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "No active login has this email. Invite them in Team & access first, then set it here.",
            )
        sql = "update app.platform set main_bb_email = $1, updated_by = $2::uuid where id = 1"
        await conn.execute(sql, body.email, user.id)
        if not await conn.fetchval(
            "select 1 from app.user_clinics where user_id = $1 and role = 'bb_admin' and active", person
        ):  # BB Admin in one clinic counts everywhere; their row in the first clinic, if they have none
            clinic = await conn.fetchval(
                """select coalesce(
                     (select clinic_id from app.user_clinics where user_id = $1 order by clinic_id limit 1),
                     (select id from app.clinics where active order by id limit 1))""",
                person,
            )
            await conn.execute(
                """insert into app.user_clinics (user_id, clinic_id, role) values ($1, $2, 'bb_admin')
                   on conflict (user_id, clinic_id) do update set role = 'bb_admin', active = true,
                     in_round_robin = false""",
                person, clinic,
            )  # fmt: skip
    return await _state(user)


# ---------- 2-step login (migration 0031) ----------
ROLES = ("bb_admin", "clinic_manager", "front_desk", "doctor")
CODE_MINUTES, MAX_TRIES, LOCK_MINUTES = 10, 5, 15
LOCKED = "Too many wrong codes. Try again in 15 minutes."
TOO_SOON = "A code was just sent. Wait a minute to ask again."


class TwoStep(BaseModel):
    roles: list[Literal["bb_admin", "clinic_manager", "front_desk", "doctor"]]


@router.get("/two-step", response_model=TwoStep)
async def get_two_step(user: Annotated[Staff, Depends(staff)]) -> TwoStep:
    _bb(user)
    found = await (await get_pool()).fetchval("select two_step_roles from app.platform where id = 1")
    return TwoStep(roles=list(found or []))


@router.put("/two-step", response_model=TwoStep)
async def set_two_step(user: Annotated[Staff, Depends(staff)], body: TwoStep) -> TwoStep:
    """Which roles need an emailed code after the password. Needs the BB Gmail (it sends BB Admin codes and is
    every clinic's fallback). Your own sign-in counts as verified, so you are not sent out now."""
    _bb(user)
    pool = await get_pool()
    roles = [r for r in ROLES if r in body.roles]
    if roles and not await pool.fetchval("select 1 from app.email_senders where clinic_id is null"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect the BB Gmail first, so the codes can be sent.")
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        await conn.execute(
            "update app.platform set two_step_roles = $1, updated_by = $2::uuid where id = 1", roles, user.id
        )
        if user.session:
            await conn.execute(
                """insert into app.login_sessions (session_id, user_id) values ($1::uuid, $2::uuid)
                   on conflict do nothing""",
                user.session, user.id,
            )  # fmt: skip
    return TwoStep(roles=roles)


codes = APIRouter(prefix="/auth/code", tags=["auth"])


def _hash(user_id: str, code: str) -> str:
    return hashlib.sha256(f"{user_id}:{code}".encode()).hexdigest()


@codes.post("/send")
async def send_code(user: Annotated[Staff, Depends(signed_in)]) -> dict[str, str]:
    """Emails a new 6-digit code (one a minute at most): the clinic's Gmail, or the BB Gmail."""
    pool = await get_pool()
    sql = "select sent_at, locked_until from app.login_codes where user_id::text = $1"
    row = await pool.fetchrow(sql, user.id)
    now = await pool.fetchval("select now()")
    if row and row["locked_until"] and row["locked_until"] > now:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, LOCKED)
    if row and (now - row["sent_at"]).total_seconds() < 60:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_SOON)
    code = f"{secrets.randbelow(1_000_000):06d}"
    await pool.execute(
        """insert into app.login_codes (user_id, code_hash, sent_at, expires_at, tries)
           values ($1::uuid, $2, now(), now() + make_interval(mins => $3), 0)
           on conflict (user_id) do update set code_hash = $2, sent_at = now(),
             expires_at = now() + make_interval(mins => $3), tries = 0, locked_until = null""",
        user.id, _hash(user.id, code), CODE_MINUTES,
    )  # fmt: skip
    clinic = None if user.bb_admin else sorted(user.roles)[0]
    text = (f"Your NEO CRM sign-in code is {code}.\n\nIt works for {CODE_MINUTES} minutes. If you did not "
            "try to sign in, change your password and tell your clinic manager.")  # fmt: skip
    try:
        await email.send(clinic, user.email, f"Your sign-in code: {code}", text, "login_code")
    except email.EmailError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None
    return {"sent_to": user.email}


class Code(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


@codes.post("/verify")
async def verify_code(user: Annotated[Staff, Depends(signed_in)], body: Code) -> dict[str, bool]:
    """The right code marks this sign-in as verified. Wrong 5 times: locked for 15 minutes."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "select *, now() now_ from app.login_codes where user_id::text = $1 for update", user.id
        )
        if row is None:
            raise HTTPException(status.HTTP_410_GONE, "Ask for a code first.")
        if row["locked_until"] and row["locked_until"] > row["now_"]:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, LOCKED)
        if row["expires_at"] < row["now_"]:
            raise HTTPException(status.HTTP_410_GONE, "This code has expired. Send a new one.")
        if not hmac.compare_digest(row["code_hash"], _hash(user.id, body.code)):
            tries = row["tries"] + 1
            lock = tries >= MAX_TRIES
            await conn.execute(
                """update app.login_codes set tries = $2,
                     locked_until = case when $3 then now() + make_interval(mins => $4) end
                   where user_id::text = $1""",
                user.id, tries, lock, LOCK_MINUTES,
            )  # fmt: skip
            left = MAX_TRIES - tries
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                LOCKED if lock else f"Wrong code. {left} tries left.",
            )
        await conn.execute("delete from app.login_codes where user_id::text = $1", user.id)
        if not user.session:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sign in again, then enter a new code.")
        await conn.execute(
            """insert into app.login_sessions (session_id, user_id) values ($1::uuid, $2::uuid)
               on conflict do nothing""",
            user.session, user.id,
        )  # fmt: skip
    return {"ok": True}
