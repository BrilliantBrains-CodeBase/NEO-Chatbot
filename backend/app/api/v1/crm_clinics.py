"""Login & security → Clinics (BB Admin only), JSON only. All clinics live in the one project: a new clinic
is a new row with the next free code (CL02 … CL98, CL99 is the test clinic, then CL100 … CL999). It copies
another clinic's working setup (hours, slots, booking window, lead assignment) and its chat (canvas,
Appearance, Templates, Menu wording), published and running on the canvas; never its contact details,
services, reviews, doctors, websites or keys. The first Clinic Manager can be invited at once. Clinics are
deactivated, never deleted.
"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.api.v1.crm_team import _give
from app.core.db import get_pool
from app.crm import supabase_admin
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
    bot_name: str = Field(min_length=2, max_length=40)
    copy_from: str = Field(pattern=r"^CL\d{2,3}$")
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
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Clinics are managed by BB Admin.")


async def _list() -> list[Clinic]:
    rows = await (await get_pool()).fetch(
        """select c.id, c.name, c.bot_name, c.active, c.is_test,
             (select count(*) from app.user_clinics u where u.clinic_id = c.id and u.active) members
           from app.clinics c order by length(c.id), c.id"""
    )
    return [Clinic(**dict(r)) for r in rows]


def next_code(taken: set[str]) -> str:
    """The first free code: CL02 … CL98 (CL99 is the test clinic), then CL100 … CL999."""
    for n in [*range(2, 99), *range(100, 1000)]:
        code = f"CL{n:02d}"
        if code not in taken:
            return code
    raise HTTPException(status.HTTP_409_CONFLICT, "No clinic codes left.")


@router.get("", response_model=list[Clinic])
async def clinics(user: Annotated[Staff, Depends(staff)]) -> list[Clinic]:
    _bb(user)
    return await _list()


@router.post("", response_model=list[Clinic], status_code=status.HTTP_201_CREATED)
async def add_clinic(user: Annotated[Staff, Depends(staff)], body: NewClinic) -> list[Clinic]:
    _bb(user)
    pool = await get_pool()
    manager_id = None
    if body.manager_email:  # before the clinic is made: an invite that fails leaves nothing half done
        sql = "select id::text from app.profiles where email = $1"
        manager_id = await pool.fetchval(sql, body.manager_email)
        if manager_id is None:
            try:
                name = (body.manager_name or body.manager_email.split("@")[0]).strip()
                manager_id = await supabase_admin.invite(body.manager_email, name)
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
        code = next_code({r["id"] for r in await conn.fetch("select id from app.clinics")})
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
                 published_at, updated_by) values ($1, $2::jsonb, $2::jsonb, 1, $3::uuid, now(), $3::uuid)""",
            code, json.dumps(chat), user.id,
        )  # fmt: skip
        if manager_id:
            await _give(conn, str(manager_id), code, "clinic_manager")
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
