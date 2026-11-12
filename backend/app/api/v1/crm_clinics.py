"""Login & security → Clinics (Super Admin only), JSON only. All clinics live in the one project: a new clinic
is a new row with a code from its name (first letter of each word: NFHT; a number added if taken). It copies
another clinic's working setup (hours, slots, booking window, lead assignment) and its chat (canvas,
Appearance, Templates, Menu wording), published and running on the canvas; never its contact details,
services, reviews, doctors, websites or keys. The first Admin can be invited at once. Clinics are
deactivated, never deleted.
"""

import json
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.api.v1.crm_team import give_role
from app.chat import main_template
from app.core.codes import CLINIC_CODE, RENAMED, code_from_name
from app.core.db import get_pool
from app.crm import staff_email, supabase_admin
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm/clinics", tags=["crm"])
COPIED = ("flow", "appearance", "template", "menu")  # the chat; contact, services, reviews stay its own
SETUP = (
    "timezone", "open_time", "close_time", "closed_weekdays", "slot_minutes", "last_slot_before_close_min",
    "booking_window_days", "booked_date_back_days", "lead_assignment", "notifications", "widget_config",
)  # fmt: skip


class Clinic(BaseModel):
    id: str
    name: str
    bot_name: str
    active: bool
    is_test: bool
    members: int


class NewClinic(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    # The short name (user, 2026-11-12): the clinic code staff choose, e.g. NF, DS, NFHT. Left out: made
    # from the name's first letters.
    code: str | None = Field(default=None, pattern=CLINIC_CODE)
    bot_name: str = Field(min_length=2, max_length=40)
    copy_from: str = Field(pattern=CLINIC_CODE)
    phone: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{6,14}$")
    whatsapp: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{6,14}$")
    website: str | None = Field(default=None, max_length=200, pattern=r"^https://\S+$")
    manager_name: str | None = Field(default=None, max_length=100)
    manager_email: str | None = Field(default=None, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

    @field_validator("manager_email")
    @classmethod
    def _lower(cls, v: str | None) -> str | None:
        return v.strip().lower() if v else None


class Active(BaseModel):
    active: bool


def _bb(user: Staff) -> None:
    if not user.bb_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Clinics are managed by Super Admin.")


async def _list() -> list[Clinic]:
    rows = await (await get_pool()).fetch(
        """select c.id, c.name, c.bot_name, c.active, c.is_test,
             (select count(*) from app.user_clinics u where u.clinic_id = c.id and u.active) members
           from app.clinics c order by length(c.id), c.id"""
    )
    return [Clinic(**dict(r)) for r in rows]


def next_code(name: str, taken: set[str]) -> str:
    """The new clinic's code, from its name (app.core.codes.code_from_name)."""
    try:
        return code_from_name(name, taken)
    except ValueError:
        raise HTTPException(status.HTTP_409_CONFLICT, "No free clinic code for this name.") from None


async def _code_taken(db: Any, code: str) -> bool:
    """A clinic has it, or it is an old code still answered for a renamed clinic (CL01)."""
    return code in RENAMED or bool(await db.fetchval("select 1 from app.clinics where id = $1", code))


@router.get("", response_model=list[Clinic])
async def clinics(user: Annotated[Staff, Depends(staff)]) -> list[Clinic]:
    _bb(user)
    return await _list()


@router.post("", response_model=list[Clinic], status_code=status.HTTP_201_CREATED)
async def add_clinic(user: Annotated[Staff, Depends(staff)], body: NewClinic) -> list[Clinic]:
    _bb(user)
    pool = await get_pool()
    if body.code and await _code_taken(pool, body.code):  # before any invite, so nothing is half done
        raise HTTPException(status.HTTP_409_CONFLICT, f"The short name {body.code} is already used.")
    manager_id = link = None
    if body.manager_email:  # before the clinic is made: an invite that fails leaves nothing half done
        sql = "select id::text from app.profiles where email = $1"
        manager_id = await pool.fetchval(sql, body.manager_email)
        if manager_id is None:
            try:
                name = (body.manager_name or body.manager_email.split("@")[0]).strip()
                manager_id, link = await supabase_admin.invite(body.manager_email, name)
            except supabase_admin.AdminError as e:
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None
            await pool.execute(
                """insert into app.profiles (id, full_name, email) values ($1::uuid, $2, $3)
                   on conflict do nothing""",
                manager_id, name, body.manager_email,
            )  # fmt: skip
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        await conn.execute("select pg_advisory_xact_lock(hashtext('new clinic'))")  # one code at a time
        source = await conn.fetchrow("select * from app.clinics where id = $1", body.copy_from)
        if source is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "The clinic to copy from does not exist.")
        taken = {r["id"] for r in await conn.fetch("select id from app.clinics")}
        if body.code and await _code_taken(conn, body.code):
            raise HTTPException(status.HTTP_409_CONFLICT, f"The short name {body.code} is already used.")
        code = body.code or next_code(body.name, taken)
        cols = ["id", "name", "bot_name", "phone", "whatsapp", "website", *SETUP]
        values = [code, body.name.strip(), body.bot_name.strip(), body.phone, body.whatsapp, body.website,
                  *(source[c] for c in SETUP)]  # fmt: skip
        marks = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
        await conn.execute(f"insert into app.clinics ({', '.join(cols)}) values ({marks})", *values)
        sql = "select published from app.clinic_settings where clinic_id = $1"
        settings = await conn.fetchval(sql, body.copy_from)
        chat = {k: v for k, v in _obj(settings).items() if k in COPIED}
        look = dict(_obj(chat.get("appearance")).get("look") or {})
        bot = body.bot_name.strip()
        look |= {"name": bot, "avatar_letter": bot[:1].upper(), "logo": "", "location": ""}
        chat["appearance"] = {**_obj(chat.get("appearance")), "look": look}
        chat["chat"] = {"canvas": bool(chat.get("flow"))}  # runs on the copied canvas
        await conn.execute(
            """insert into app.clinic_settings (clinic_id, draft, published, version, published_by,
                 published_at, updated_by, follows)
               values ($1, $2::jsonb, $2::jsonb, 1, $3::uuid, now(), $3::uuid, $4)""",
            code,
            json.dumps(chat),
            user.id,
            list(main_template.PARTS) if body.copy_from == main_template.MAIN else [],
        )  # fmt: skip  (a copy of the main follows it: canvas, Templates, Appearance)
        if manager_id:
            await give_role(conn, str(manager_id), code, "clinic_manager")
    if link and body.manager_email:  # a new clinic has no Gmail yet: from the BB Gmail. Not sent: Team →
        # Reset password in the new clinic hands the link over.
        subject, text = staff_email.invite_text(name, "Admin", body.name.strip(), link)
        await staff_email.deliver(code, body.manager_email, subject, text, link, "invite")
    return await _list()


def _obj(v: Any) -> dict[str, Any]:
    return dict(json.loads(v) if isinstance(v, str) else v or {})


@router.put("/{clinic}", response_model=list[Clinic])
async def set_active(user: Annotated[Staff, Depends(staff)], clinic: str, body: Active) -> list[Clinic]:
    """Deactivate: the clinic's chat and CRM stop (nothing is deleted). Activate: back as it was."""
    _bb(user)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        done = await conn.execute("update app.clinics set active = $2 where id = $1", clinic, body.active)
    if done.endswith(" 0"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinic not found.")
    return await _list()


# A clinic's own setup, removed with it; anything else (leads, chats, doctors, integrations) keeps it.
SETUP_TABLES = ("access_grants", "clinic_permissions", "access_requests", "user_clinics", "clinic_websites",
                "clinic_setting_versions", "clinic_settings")  # fmt: skip


@router.delete("/{clinic}", response_model=list[Clinic])
async def delete_clinic(user: Annotated[Staff, Depends(staff)], clinic: str) -> list[Clinic]:
    """Deletes a clinic that holds no patient or business data (e.g. added by mistake): its setup, its team
    access, then the clinic. With leads, chats, doctors or integrations it is refused: deactivate it."""
    _bb(user)
    if clinic in (main_template.MAIN, "CL99"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This clinic cannot be deleted.")
    pool = await get_pool()
    try:
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
            for table in SETUP_TABLES:
                await conn.execute(f"delete from app.{table} where clinic_id = $1", clinic)
            done = await conn.execute("delete from app.clinics where id = $1", clinic)
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This clinic has data (leads, chats, doctors or integrations). Deactivate it instead.",
        ) from None
    if done.endswith(" 0"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinic not found.")
    return await _list()
