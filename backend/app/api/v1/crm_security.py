"""Dashboard → Login & security (migration 0029), JSON only. BB Admin only.

Main BB Admin: one email that always has full BB Admin power over every clinic. Setting it gives that person
an active BB Admin role (so the backend and the database's own rules agree); Team & access never disables,
removes or demotes them. Only the main BB Admin changes it; any BB Admin sets the first one.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.core.db import get_pool
from app.crm.auth import Staff, staff

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
