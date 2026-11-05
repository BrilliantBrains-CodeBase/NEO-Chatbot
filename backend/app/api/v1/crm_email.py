"""Email senders (migration 0030), JSON only: a clinic's Gmail (Integrations → Email; Admin, BB
Admin) and the BB Gmail (Login & security; Super Admin). Connect with the Gmail address and a Google App
password (kept in Vault, never shown again), send a test, see the last emails. Connecting again replaces
the password.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.core.db import get_pool
from app.crm import email, vault
from app.crm import permissions as perm
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm", tags=["crm"])
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$"
ONE = "coalesce(clinic_id, 'BB') = coalesce($1, 'BB')"  # this clinic's row, or the BB Gmail's (clinic None)


class Sent(BaseModel):
    to: str
    kind: str
    ok: bool
    error: str | None
    at: str


class Sender(BaseModel):
    connected: bool
    address: str | None
    from_name: str
    log: list[Sent]  # the last 10


class Connect(BaseModel):
    address: str = Field(max_length=120, pattern=EMAIL)
    app_password: str = Field(min_length=16, max_length=40)  # Google shows it as 4 groups of 4 letters
    from_name: str = Field(default="", max_length=80)

    @field_validator("address")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("app_password")
    @classmethod
    def _spaces(cls, v: str) -> str:
        return v.replace(" ", "")


class Test(BaseModel):
    to: str = Field(max_length=120, pattern=EMAIL)


def _who(user: Staff, clinic: str | None) -> None:
    """A clinic's Gmail: its Admin or Super Admin. The BB Gmail: Super Admin."""
    if clinic is None and not user.bb_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The BB Gmail is for Super Admin.")
    allowed = user.bb_admin or user.roles.get(clinic or "") == "clinic_manager"
    if clinic and not (allowed or perm.granted(user, clinic)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Email is for admins and Super Admin.")


async def _state(clinic: str | None) -> Sender:
    pool = await get_pool()
    row = await pool.fetchrow(
        f"select address, from_name from app.email_senders where {ONE}",
        clinic,
    )
    log = await pool.fetch(
        """select to_email, kind, ok, error, at from app.email_log
           where coalesce(clinic_id, 'BB') = coalesce($1, 'BB') order by at desc limit 10""",
        clinic,
    )
    return Sender(
        connected=row is not None, address=row["address"] if row else None,
        from_name=row["from_name"] if row else "",
        log=[Sent(to=r["to_email"], kind=r["kind"], ok=r["ok"], error=r["error"], at=r["at"].isoformat())
             for r in log],
    )  # fmt: skip


async def _connect(user: Staff, clinic: str | None, body: Connect) -> Sender:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        old = await conn.fetchval(
            f"delete from app.email_senders where {ONE} returning secret",
            clinic,
        )
        secret = await vault.save(conn, body.app_password, f"gmail {clinic or 'BB'} {body.address}")
        await conn.execute(
            """insert into app.email_senders (clinic_id, address, from_name, secret, connected_by)
               values ($1, $2, $3, $4, $5::uuid)""",
            clinic, body.address, body.from_name.strip(), secret, user.id,
        )  # fmt: skip
        await vault.delete(conn, old)
    return await _state(clinic)


async def _disconnect(user: Staff, clinic: str | None) -> Sender:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        old = await conn.fetchval(
            f"delete from app.email_senders where {ONE} returning secret",
            clinic,
        )
        await vault.delete(conn, old)
    return await _state(clinic)


async def _test(clinic: str | None, to: str) -> Sender:
    try:
        await email.send(clinic, to, "NEO CRM test email", "Your Gmail is connected to NEO CRM.", "test")
    except email.EmailError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    return await _state(clinic)


# ---------- a clinic's Gmail: Dashboard → Integrations → Email ----------
@router.get("/console/{clinic}/integrations/email", response_model=Sender)
async def clinic_email(user: Annotated[Staff, Depends(staff)], clinic: str) -> Sender:
    _who(user, clinic)
    return await _state(clinic)


@router.put("/console/{clinic}/integrations/email", response_model=Sender)
async def clinic_connect(user: Annotated[Staff, Depends(staff)], clinic: str, body: Connect) -> Sender:
    _who(user, clinic)
    return await _connect(user, clinic, body)


@router.delete("/console/{clinic}/integrations/email", response_model=Sender)
async def clinic_disconnect(user: Annotated[Staff, Depends(staff)], clinic: str) -> Sender:
    _who(user, clinic)
    return await _disconnect(user, clinic)


@router.post("/console/{clinic}/integrations/email/test", response_model=Sender)
async def clinic_test(user: Annotated[Staff, Depends(staff)], clinic: str, body: Test) -> Sender:
    _who(user, clinic)
    return await _test(clinic, body.to)


# ---------- the BB Gmail: Dashboard → Login & security ----------
@router.get("/security/email", response_model=Sender)
async def bb_email(user: Annotated[Staff, Depends(staff)]) -> Sender:
    _who(user, None)
    return await _state(None)


@router.put("/security/email", response_model=Sender)
async def bb_connect(user: Annotated[Staff, Depends(staff)], body: Connect) -> Sender:
    _who(user, None)
    return await _connect(user, None, body)


@router.delete("/security/email", response_model=Sender)
async def bb_disconnect(user: Annotated[Staff, Depends(staff)]) -> Sender:
    _who(user, None)
    return await _disconnect(user, None)


@router.post("/security/email/test", response_model=Sender)
async def bb_test(user: Annotated[Staff, Depends(staff)], body: Test) -> Sender:
    _who(user, None)
    return await _test(None, body.to)
