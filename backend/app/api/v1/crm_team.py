"""Team & access (migration 0028), JSON only.

- "Create an account" (public): the person's login and profile are made with no clinic role, plus a pending
  request; the CRM refuses them until it is approved.
- Dashboard → Team & access (Clinic Manager, BB Admin): approve (the role may be changed) or reject requests,
  invite by email with a role, change a role, disable or enable someone, send a password reset. Only BB Admin
  approves, invites or changes Clinic Managers. Nobody changes their own access.
- CRM → Team: everyone sees their own profile; Clinic Managers and BB Admin see everyone in the clinic.
Every change is logged (audit trigger).
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from app.api.v1.crm_security import main_email
from app.chat import guard
from app.core.db import get_pool
from app.crm import supabase_admin
from app.crm.auth import ROLE_LABEL, Staff, staff

router = APIRouter(tags=["crm"])
Role = Literal["clinic_manager", "front_desk", "doctor"]
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$"


class Member(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None
    role: str
    role_label: str
    active: bool  # can sign in to this clinic
    last_seen_at: str | None
    me: bool
    clinics: list[str]  # the clinics they can open (of those you manage)


class Request_(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None
    role: str
    status: str
    created_at: str
    decided_by: str | None
    decided_at: str | None


class Team(BaseModel):
    members: list[Member]
    requests: list[Request_]  # pending first, then the last 20 decided (managers only)
    can_manage: bool
    managed: dict[str, str]  # the clinics you can give access to: id -> name (BB Admin: every clinic)


def _can_manage(user: Staff, clinic: str) -> bool:
    return user.bb_admin or user.roles.get(clinic) == "clinic_manager"


async def _managed(user: Staff) -> dict[str, str]:
    """The clinics this person gives access to: every clinic for BB Admin, else the ones they manage."""
    rows = await (await get_pool()).fetch(
        "select id, name from app.clinics where active and ($1 or id = any($2::text[])) order by id",
        user.bb_admin, [c for c, r in user.roles.items() if r == "clinic_manager"],
    )  # fmt: skip
    return {r["id"]: r["name"] for r in rows}


def _may_give(user: Staff, role: str) -> None:
    """Only BB Admin gives (or takes away) the Clinic Manager role."""
    if role == "clinic_manager" and not user.bb_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only BB Admin can make someone a Clinic Manager.")


async def _team(user: Staff, clinic: str) -> Team:
    if not (user.bb_admin or clinic in user.roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not your clinic.")
    manage = _can_manage(user, clinic)
    pool = await get_pool()
    rows = await pool.fetch(
        """select p.id, p.full_name, p.email, p.phone, p.last_seen_at, uc.role, uc.active and p.active active,
             array(select c.clinic_id from app.user_clinics c where c.user_id = p.id) clinics  -- disabled too
           from app.user_clinics uc join app.profiles p on p.id = uc.user_id
           where uc.clinic_id = $1 and ($2 or p.id = $3::uuid)
           order by uc.active desc, uc.role, p.full_name""",
        clinic, manage, user.id,
    )  # fmt: skip
    asked = (
        await pool.fetch(
            """(select r.*, d.full_name decider from app.access_requests r
                  left join app.profiles d on d.id = r.decided_by
                where r.clinic_id = $1 and r.status = 'pending' order by r.created_at)
               union all
               (select r.*, d.full_name decider from app.access_requests r
                  left join app.profiles d on d.id = r.decided_by
                where r.clinic_id = $1 and r.status <> 'pending' order by r.decided_at desc limit 20)""",
            clinic,
        )
        if manage
        else []
    )
    managed = await _managed(user) if manage else {}
    return Team(
        can_manage=manage,
        managed=managed,
        members=[
            Member(id=str(r["id"]), name=r["full_name"], email=r["email"], phone=r["phone"], role=r["role"],
                   role_label=ROLE_LABEL.get(r["role"], r["role"]), active=r["active"],
                   last_seen_at=r["last_seen_at"].isoformat() if r["last_seen_at"] else None,
                   me=str(r["id"]) == user.id, clinics=[c for c in r["clinics"] if c in managed])
            for r in rows
        ],
        requests=[
            Request_(id=str(r["id"]), name=r["full_name"], email=r["email"], phone=r["phone"], role=r["role"],
                     status=r["status"], created_at=r["created_at"].isoformat(), decided_by=r["decider"],
                     decided_at=r["decided_at"].isoformat() if r["decided_at"] else None)
            for r in asked
        ],
    )  # fmt: skip


def _manager(user: Staff, clinic: str) -> None:
    if not _can_manage(user, clinic):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Team & access is for Clinic Managers and BB Admin.")


async def _admin(call: Any) -> Any:
    """A Supabase admin call; its refusal shown to staff."""
    try:
        return await call
    except supabase_admin.AdminError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None


# ---------- CRM → Team, Dashboard → Team & access ----------
@router.get("/crm/team/{clinic}", response_model=Team)
async def team(user: Annotated[Staff, Depends(staff)], clinic: str) -> Team:
    """Managers and BB Admin: everyone in the clinic and the access requests. Others: their own profile."""
    return await _team(user, clinic)


class Decision(BaseModel):
    status: Literal["approved", "rejected"]
    role: Role | None = None  # approve as another role than asked


@router.post("/crm/team/{clinic}/requests/{request_id}", response_model=Team)
async def decide(
    user: Annotated[Staff, Depends(staff)], clinic: str, request_id: str, body: Decision
) -> Team:
    """Approve: the role becomes active for this clinic. Reject: the request is closed, and the login is
    removed when the person has no access anywhere."""
    _manager(user, clinic)
    pool = await get_pool()
    req = await pool.fetchrow(
        "select * from app.access_requests where id::text = $1 and clinic_id = $2 and status = 'pending'",
        request_id, clinic,
    )  # fmt: skip
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This request is not waiting any more.")
    role = body.role or req["role"]
    _may_give(user, role)
    _may_give(user, req["role"])  # a Clinic Manager request is BB Admin's to decide
    remove_login = None
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        if body.status == "approved" and req["user_id"]:
            await conn.execute(
                """insert into app.user_clinics (user_id, clinic_id, role, in_round_robin)
                   values ($1, $2, $3, $3 = 'front_desk')
                   on conflict (user_id, clinic_id) do update set role = $3, active = true,
                     in_round_robin = $3 = 'front_desk'""",
                req["user_id"], clinic, role,
            )  # fmt: skip
        elif body.status == "rejected" and req["user_id"]:
            other = await conn.fetchval(
                "select 1 from app.user_clinics where user_id = $1 and active", req["user_id"]
            )
            remove_login = None if other else str(req["user_id"])
        await conn.execute(
            """update app.access_requests set status = $2, role = $3, decided_by = $4::uuid,
                 decided_at = now() where id = $1""",
            req["id"], body.status, role, user.id,
        )  # fmt: skip
    if remove_login:  # after the decision is saved; the profile goes with the login
        await _admin(supabase_admin.delete_user(remove_login))
    return await _team(user, clinic)


class Invite(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: str = Field(max_length=120, pattern=EMAIL)
    role: Role
    clinics: list[str] = Field(default=[], max_length=50)  # empty: this clinic

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


@router.post("/crm/team/{clinic}/invite", response_model=Team)
async def invite(user: Annotated[Staff, Depends(staff)], clinic: str, body: Invite) -> Team:
    """Someone new gets an email to set their password (then signs in with this role); someone who already
    has a login gets the role straight away."""
    _manager(user, clinic)
    _may_give(user, body.role)
    managed = await _managed(user)
    chosen = list(dict.fromkeys(body.clinics or [clinic]))
    if any(c not in managed for c in chosen):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only give access to clinics you manage.")
    pool = await get_pool()
    known = await pool.fetchval("select id from app.profiles where email = $1", body.email)
    new_id = None if known else await _admin(supabase_admin.invite(body.email, body.full_name.strip()))
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        if new_id:
            await conn.execute(
                """insert into app.profiles (id, full_name, email) values ($1::uuid, $2, $3)
                   on conflict do nothing""",
                new_id, body.full_name.strip(), body.email,
            )  # fmt: skip
        uid = str(known or new_id)
        has = "select clinic_id from app.user_clinics where user_id = $1::uuid and active"
        already = {r["clinic_id"] for r in await conn.fetch(has, uid)}
        if all(c in already for c in chosen):
            raise HTTPException(status.HTTP_409_CONFLICT, "This person already has access to these clinics.")
        for c in chosen:
            await _give(conn, uid, c, body.role)
    return await _team(user, clinic)


async def _give(conn: Any, uid: str, clinic: str, role: str) -> None:
    """Access to one clinic with this role (Front Desk joins its lead round robin)."""
    await conn.execute(
        """insert into app.user_clinics (user_id, clinic_id, role, in_round_robin)
           values ($1::uuid, $2, $3, $3 = 'front_desk')
           on conflict (user_id, clinic_id) do update set role = $3, active = true,
             in_round_robin = $3 = 'front_desk'""",
        uid, clinic, role,
    )  # fmt: skip


class Change(BaseModel):
    role: Role | None = None
    active: bool | None = None


@router.put("/crm/team/{clinic}/members/{member}", response_model=Team)
async def change(user: Annotated[Staff, Depends(staff)], clinic: str, member: str, body: Change) -> Team:
    """A new role, or access off / on for this clinic (their login stays)."""
    now = await _their_role(user, clinic, member)
    pool = await get_pool()
    if body.role:
        _may_give(user, body.role)
    role = body.role or now
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        await conn.execute(
            """update app.user_clinics set role = $3, active = coalesce($4, active),
                 in_round_robin = $3 = 'front_desk' and coalesce($4, active)
               where user_id::text = $1 and clinic_id = $2""",
            member, clinic, role, body.active,
        )  # fmt: skip
    return await _team(user, clinic)


async def _their_role(user: Staff, clinic: str, member: str) -> str:
    """Their role in this clinic, if you may change them (not yourself, not BB Admin; Clinic Managers by BB
    Admin only)."""
    _manager(user, clinic)
    if member == user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot change your own access.")
    role = await (await get_pool()).fetchval(
        "select role from app.user_clinics where user_id::text = $1 and clinic_id = $2", member, clinic
    )
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a member of this clinic.")
    if role == "bb_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "BB Admin access is not changed here.")
    email = await (await get_pool()).fetchval("select email from app.profiles where id::text = $1", member)
    if email and email == await main_email():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The main BB Admin's access is not changed here.")
    _may_give(user, str(role))
    return str(role)


class Clinics(BaseModel):
    clinics: list[str] = Field(max_length=50)


@router.put("/crm/team/{clinic}/members/{member}/clinics", response_model=Team)
async def set_clinics(
    user: Annotated[Staff, Depends(staff)], clinic: str, member: str, body: Clinics
) -> Team:
    """The clinics they can open, with their role here (BB Admin: which clinics a Clinic Manager manages).
    Only the clinics you manage change; their others stay."""
    role = await _their_role(user, clinic, member)
    managed = await _managed(user)
    wanted = {c for c in body.clinics if c in managed}
    if not wanted:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Keep at least one clinic, or use Remove.")
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        now = {r["clinic_id"] for r in await conn.fetch(
            "select clinic_id from app.user_clinics where user_id::text = $1", member  # disabled too
        )}  # fmt: skip
        for c in wanted - now:
            await _give(conn, member, c, role)
        gone = [c for c in now - wanted if c in managed]
        drop = "delete from app.user_clinics where user_id::text = $1 and clinic_id = any($2::text[])"
        await conn.execute(drop, member, gone)
    return await _team(user, clinic)


@router.delete("/crm/team/{clinic}/members/{member}", response_model=Team)
async def remove(user: Annotated[Staff, Depends(staff)], clinic: str, member: str) -> Team:
    """Takes them out of this clinic. With no clinic left anywhere, their login is deleted too."""
    await _their_role(user, clinic, member)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        await conn.execute(
            "delete from app.user_clinics where user_id::text = $1 and clinic_id = $2", member, clinic
        )
        left = await conn.fetchval("select 1 from app.user_clinics where user_id::text = $1", member)
    if not left:  # the profile goes with the login
        await _admin(supabase_admin.delete_user(member))
    return await _team(user, clinic)


@router.post("/crm/team/{clinic}/members/{member}/reset", response_model=Team)
async def reset(user: Annotated[Staff, Depends(staff)], clinic: str, member: str) -> Team:
    """Emails them a link to set a new password."""
    _manager(user, clinic)
    email = await (await get_pool()).fetchval(
        """select p.email from app.profiles p join app.user_clinics uc on uc.user_id = p.id
           where p.id::text = $1 and uc.clinic_id = $2""",
        member, clinic,
    )  # fmt: skip
    if email is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a member of this clinic.")
    await _admin(supabase_admin.reset_password(email))
    return await _team(user, clinic)


# ---------- "Create an account" (sign-in pages, no sign-in) ----------
class AccessRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    phone: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{6,14}$")
    email: str = Field(max_length=120, pattern=EMAIL)
    password: str = Field(min_length=8, max_length=72)
    clinic: str = Field(pattern=r"^CL\d{2}$")  # the clinic code the manager gives, e.g. CL01
    role: Role

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


@router.post("/auth/request-access", status_code=status.HTTP_201_CREATED)
async def request_access(request: Request, body: AccessRequest) -> dict[str, str]:
    """Creates the login (refused by the CRM until approved) and a pending request for the clinic."""
    ip = guard.client_ip(request.headers, request.client.host if request.client else None)
    if not guard.limiter.allow(f"access:{ip}", 3):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Please try in a minute.")
    pool = await get_pool()
    clinic = await pool.fetchval("select name from app.clinics where id = $1 and active", body.clinic)
    if clinic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No clinic has this code. Ask your clinic manager.")
    if await pool.fetchval("select 1 from app.profiles where email = $1", body.email):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This email already has an account. Sign in, or ask your clinic manager to add you.",
        )
    uid = await _admin(supabase_admin.create_user(body.email, body.password, body.full_name.strip()))
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", uid)
        await conn.execute(
            "insert into app.profiles (id, full_name, email, phone) values ($1::uuid, $2, $3, $4)",
            uid, body.full_name.strip(), body.email, body.phone,
        )  # fmt: skip
        await conn.execute(
            """insert into app.access_requests (user_id, clinic_id, role, full_name, email, phone)
               values ($1::uuid, $2, $3, $4, $5, $6)""",
            uid, body.clinic, body.role, body.full_name.strip(), body.email, body.phone,
        )  # fmt: skip
    return {"clinic": str(clinic), "role": ROLE_LABEL[body.role]}
