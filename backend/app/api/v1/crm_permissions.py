"""Who sees what (migration 0032), JSON only: Team → Roles & permissions. Super Admin sets the defaults for
all
clinics and any clinic's own rules; an Admin sets their clinic's Front Desk and Doctor rules, never
above the manager's own access. Each save stores only what differs from the layer below.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.db import get_pool
from app.crm import permissions as perm
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm/permissions", tags=["crm"])


class Screen(BaseModel):
    key: str
    label: str
    group: str  # CRM or Dashboard


class Grant(BaseModel):
    id: str
    user_id: str
    name: str
    screen: str
    level: str
    until: str
    given_by: str | None


class Rules(BaseModel):
    screens: list[Screen]
    roles: list[str]
    defaults: dict[str, dict[str, str]]  # built-in + BB's defaults (what a clinic starts from)
    effective: dict[str, dict[str, str]]  # what is in force in this clinic
    own: dict[str, dict[str, str]]  # this clinic's own changes
    can_edit_defaults: bool  # Super Admin
    can_edit_managers: bool  # Super Admin (the Admin row)
    grants: list[Grant]  # access given to one person for a time, not ended yet


class Save(BaseModel):
    rules: dict[str, dict[str, str]]  # the full table being saved


def _manager(user: Staff, clinic: str) -> None:
    if not (user.bb_admin or user.roles.get(clinic) == "clinic_manager"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Who sees what is for Admins and Super Admin.")


def _diff(table: dict[str, Any], base: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Only the levels that differ from the layer below."""
    out: dict[str, dict[str, str]] = {}
    for role, screens in perm.clean(table).items():
        changed = {s: str(lv) for s, lv in screens.items() if base[role].get(s) != lv}
        if changed:
            out[role] = changed
    return out


async def _rules(user: Staff, clinic: str) -> Rules:
    pool = await get_pool()
    row = await pool.fetchrow(
        """select (select permissions from app.platform where id = 1) defaults,
             (select rules from app.clinic_permissions where clinic_id = $1) own""",
        clinic,
    )
    grants = await pool.fetch(
        """select g.*, p.full_name name, b.full_name giver from app.access_grants g
             join app.profiles p on p.id = g.user_id left join app.profiles b on b.id = g.given_by
           where g.clinic_id = $1 and g.until > now() order by g.until""",
        clinic,
    )
    defaults_layer = perm._obj(row["defaults"])
    own = perm.clean(perm._obj(row["own"]))
    return Rules(
        screens=[Screen(key=k, label=label, group=g) for k, (label, g) in perm.SCREENS.items()
                 if k not in perm.FIXED],
        roles=list(perm.ROLES),
        defaults=perm.stack(defaults_layer),
        effective=perm.stack(defaults_layer, own),
        own=own,
        can_edit_defaults=user.bb_admin,
        can_edit_managers=user.bb_admin,
        grants=[
            Grant(id=str(g["id"]), user_id=str(g["user_id"]), name=g["name"], screen=g["screen"],
                  level=g["level"], until=g["until"].isoformat(), given_by=g["giver"])
            for g in grants
        ],
    )  # fmt: skip


@router.get("/{clinic}", response_model=Rules)
async def get_rules(user: Annotated[Staff, Depends(staff)], clinic: str) -> Rules:
    _manager(user, clinic)
    return await _rules(user, clinic)


@router.put("/{clinic}", response_model=Rules)
async def save_clinic(user: Annotated[Staff, Depends(staff)], clinic: str, body: Save) -> Rules:
    """This clinic's own rules. An Admin: Front Desk and Doctor only, never above the manager."""
    _manager(user, clinic)
    current = await _rules(user, clinic)
    table = perm.clean(body.rules)
    if not user.bb_admin:
        mine = current.effective["clinic_manager"]
        if any(mine.get(s) != lv for s, lv in table.get("clinic_manager", {}).items()):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Super Admin changes what Admins see.")
        for role in ("front_desk", "doctor"):
            for s, lv in table.get(role, {}).items():
                if perm.rank(lv) > perm.rank(mine.get(s, "hidden")):
                    label = perm.SCREENS[s][0]
                    raise HTTPException(
                        status.HTTP_403_FORBIDDEN, f"{label}: you cannot give more than your own access."
                    )
    own = _diff(table, current.defaults)
    if not user.bb_admin:  # Super Admin's limits on Admins stay, also on "Use the defaults"
        if limits := current.own.get("clinic_manager"):
            own["clinic_manager"] = dict(limits)
        else:
            own.pop("clinic_manager", None)
    await _store(user, "insert", clinic, own)
    return await _rules(user, clinic)


@router.put("/defaults/{clinic}", response_model=Rules)
async def save_defaults(user: Annotated[Staff, Depends(staff)], clinic: str, body: Save) -> Rules:
    """Super Admin: the defaults for every clinic (clinics keep their own changes on top)."""
    if not user.bb_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Super Admin sets the defaults for all clinics.")
    await _store(user, "defaults", None, _diff(perm.clean(body.rules), perm.stack()))
    return await _rules(user, clinic)


async def _store(user: Staff, kind: str, clinic: str | None, rules: dict[str, dict[str, str]]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        if kind == "defaults":
            await conn.execute(
                "update app.platform set permissions = $1::jsonb, updated_by = $2::uuid where id = 1",
                json.dumps(rules), user.id,
            )  # fmt: skip
        else:
            await conn.execute(
                """insert into app.clinic_permissions (clinic_id, rules, updated_by)
                   values ($1, $2::jsonb, $3::uuid)
                   on conflict (clinic_id) do update set rules = $2::jsonb, updated_by = $3::uuid""",
                clinic, json.dumps(rules), user.id,
            )  # fmt: skip


class NewGrant(BaseModel):
    user_id: str
    screen: str
    level: Literal["view", "edit"]
    until: datetime  # with its time zone, e.g. 2026-11-01T18:00:00+05:30


@router.post("/{clinic}/grants", response_model=Rules)
async def give(user: Annotated[Staff, Depends(staff)], clinic: str, body: NewGrant) -> Rules:
    """One person gets a screen at view or edit until a moment (at most 90 days); then it ends by itself.
    An Admin gives Front Desk and Doctors only, never above their own access."""
    _manager(user, clinic)
    if body.screen not in perm.SCREENS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown screen.")
    now = datetime.now(UTC)
    if body.until.tzinfo is None or not now < body.until <= now + timedelta(days=90):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose an end within the next 90 days.")
    pool = await get_pool()
    role = await pool.fetchval(
        "select role from app.user_clinics where user_id::text = $1 and clinic_id = $2 and active",
        body.user_id, clinic,
    )  # fmt: skip
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not an active member of this clinic.")
    if role == "bb_admin" or (role == "clinic_manager" and not user.bb_admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Super Admin gives an Admin extra access.")
    if not user.bb_admin:
        mine = (await _rules(user, clinic)).effective["clinic_manager"]
        if perm.rank(body.level) > perm.rank(mine.get(body.screen, "hidden")):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot give more than your own access.")
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        await conn.execute(
            """insert into app.access_grants (clinic_id, user_id, screen, level, until, given_by)
               values ($1, $2::uuid, $3, $4, $5, $6::uuid)""",
            clinic, body.user_id, body.screen, body.level, body.until, user.id,
        )  # fmt: skip
    return await _rules(user, clinic)


@router.delete("/{clinic}/grants/{grant}", response_model=Rules)
async def take_back(user: Annotated[Staff, Depends(staff)], clinic: str, grant: str) -> Rules:
    """Ends access given for a time now."""
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        sql = "delete from app.access_grants where id::text = $1 and clinic_id = $2"
        await conn.execute(sql, grant, clinic)
    return await _rules(user, clinic)
