"""CRM API (JSON only). Every route needs a signed-in staff member (app.crm.auth.staff)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.db import get_pool
from app.crm.auth import ROLE_LABEL, Staff, staff

router = APIRouter(prefix="/crm", tags=["crm"])


class ClinicAccess(BaseModel):
    id: str  # CL01
    name: str  # Neo Follicle
    role: str  # bb_admin
    role_label: str  # BB Admin


class Me(BaseModel):
    id: str
    name: str
    email: str
    initials: str
    bb_admin: bool
    role_label: str  # the highest role, for the profile menu
    clinics: list[ClinicAccess]


def initials(name: str) -> str:
    parts = [p for p in name.replace("Dr ", "").split() if p[:1].isalpha()]
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper() if parts else "?"


RANK = ["bb_admin", "clinic_manager", "front_desk", "doctor"]


@router.get("/me", response_model=Me)
async def me(user: Annotated[Staff, Depends(staff)]) -> Me:
    """Who is signed in and which clinics they see. BB Admin sees every active clinic (not test clinics)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("select id, name from app.clinics where active and not is_test order by id")
    clinics = []
    for r in rows:
        role = "bb_admin" if user.bb_admin else user.roles.get(r["id"])
        if role:
            clinics.append(ClinicAccess(id=r["id"], name=r["name"], role=role, role_label=ROLE_LABEL[role]))
    top = min(user.roles.values(), key=RANK.index)
    return Me(
        id=user.id,
        name=user.name,
        email=user.email,
        initials=initials(user.name),
        bb_admin=user.bb_admin,
        role_label=ROLE_LABEL[top],
        clinics=clinics,
    )
