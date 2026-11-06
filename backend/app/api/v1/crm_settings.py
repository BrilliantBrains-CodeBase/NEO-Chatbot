"""Clinic settings (JSON only, migration 0038): the chosen clinic's own record for the CRM. Its details, how
new leads are assigned, who is emailed on an emergency, and the logo and favicon the CRM shows while the
clinic is chosen. Reading needs Settings (Who sees what) at view, saving at edit; the logo and favicon are
read by everyone in the clinic, since every page shows them. The chatbot keeps its own copy of the contact
details (Dashboard → Clinic info): nothing here changes what patients see.
"""

import re
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field, field_validator

from app.core.codes import CLINIC_CODE
from app.core.db import get_pool
from app.crm import permissions as perm
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm/clinic-settings", tags=["crm"])

CLINIC = Annotated[str, Path(pattern=CLINIC_CODE)]
PHONE = r"^\+[1-9][0-9]{6,14}$"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
TYPES = r"png|jpeg|webp|svg\+xml|x-icon|vnd\.microsoft\.icon"
IMAGE = re.compile(rf"^data:image/({TYPES});base64,[A-Za-z0-9+/=]+$")
LOGO_MAX = 400_000
FAVICON_MAX = 100_000
DETAILS = (
    "name", "email", "phone", "alt_phone", "whatsapp", "website", "address", "city", "state", "postal_code",
    "country", "registration_no", "gstin", "lead_assignment",
)  # fmt: skip


def _blank(v: Any) -> Any:
    """Empty text is "not set" (null in the database)."""
    if isinstance(v, str):
        v = " ".join(v.split())
        return v or None
    return v


class Alerts(BaseModel):
    emergency_admins: bool = True
    emergency_emails: list[str] = Field(default=[], max_length=10)

    @field_validator("emergency_emails")
    @classmethod
    def _emails(cls, v: list[str]) -> list[str]:
        out = list(dict.fromkeys(e.strip().lower() for e in v if e.strip()))
        bad = [e for e in out if not EMAIL.match(e) or len(e) > 120]
        if bad:
            raise ValueError(f"Not an email address: {bad[0]}")
        return out


class Details(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, pattern=PHONE)
    alt_phone: str | None = Field(default=None, pattern=PHONE)
    whatsapp: str | None = Field(default=None, pattern=PHONE)
    website: str | None = Field(default=None, max_length=200, pattern=r"^https://\S+$")
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=60)
    state: str | None = Field(default=None, max_length=60)
    postal_code: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9 -]{1,9}$")
    country: str = Field(default="India", min_length=2, max_length=60)
    registration_no: str | None = Field(default=None, max_length=60)
    gstin: str | None = Field(default=None, pattern=r"^[0-9]{2}[A-Z0-9]{13}$")
    # "manual" is the old name of "inbox" (before migration 0039).
    lead_assignment: Literal["inbox", "round_robin", "manager", "manual"] = "inbox"

    @field_validator(
        "name", "email", "phone", "alt_phone", "whatsapp", "website", "address", "city", "state",
        "postal_code", "country", "registration_no", "gstin", mode="before",
    )  # fmt: skip
    @classmethod
    def _tidy(cls, v: Any) -> Any:
        return _blank(v)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.lower()
        if not EMAIL.match(v):
            raise ValueError("Please enter a valid email address.")
        return v

    @field_validator("gstin", mode="before")
    @classmethod
    def _upper(cls, v: Any) -> Any:
        v = _blank(v)
        return v.upper().replace(" ", "") if isinstance(v, str) else v


class ClinicSettings(BaseModel):
    id: str
    details: dict[str, str | None]  # as stored: older rows may predate today's checks
    alerts: Alerts
    can_edit: bool


class SettingsIn(BaseModel):
    details: Details
    alerts: Alerts


class Branding(BaseModel):
    logo: str | None = None
    favicon: str | None = None
    updated_at: str | None = None  # changes with each save: the browser keeps the images until then


class BrandingIn(BaseModel):
    logo: str | None = Field(default=None, max_length=LOGO_MAX)
    favicon: str | None = Field(default=None, max_length=FAVICON_MAX)

    @field_validator("logo", "favicon")
    @classmethod
    def _image(cls, v: str | None) -> str | None:
        if v and not IMAGE.match(v):
            raise ValueError("Upload a PNG, JPG, WebP, SVG or ICO image.")
        return v or None


def _member(user: Staff, clinic: str) -> None:
    if not user.bb_admin and clinic not in user.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this clinic.")


async def _read(conn: Any, user: Staff, clinic: str) -> ClinicSettings:
    row = await conn.fetchrow(f"select {', '.join(DETAILS)} from app.clinics where id = $1", clinic)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinic not found.")
    alerts = await conn.fetchrow(
        "select emergency_admins, emergency_emails from app.clinic_alerts where clinic_id = $1", clinic
    )
    role = "bb_admin" if user.bb_admin else user.roles.get(clinic, "")
    rules = await perm.for_person(conn, clinic, user.id, role) if role else {}
    return ClinicSettings(
        id=clinic,
        details=dict(row),
        alerts=Alerts(**dict(alerts)) if alerts else Alerts(),
        can_edit=rules.get("settings") == "edit",
    )


@router.get("/{clinic}", response_model=ClinicSettings)
async def get_settings_(user: Annotated[Staff, Depends(staff)], clinic: CLINIC) -> ClinicSettings:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await perm.require(conn, user, clinic, "settings", "view")
        return await _read(conn, user, clinic)


@router.put("/{clinic}", response_model=ClinicSettings)
async def put_settings(
    user: Annotated[Staff, Depends(staff)], clinic: CLINIC, body: SettingsIn
) -> ClinicSettings:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await perm.require(conn, user, clinic, "settings", "edit")
        d = body.details.model_dump()
        sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(DETAILS))
        async with conn.transaction():
            done = await conn.execute(
                f"update app.clinics set {sets} where id = $1", clinic, *(d[k] for k in DETAILS)
            )
            if done == "UPDATE 0":
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinic not found.")
            await conn.execute(
                """insert into app.clinic_alerts (clinic_id, emergency_admins, emergency_emails, updated_by)
                   values ($1, $2, $3, $4::uuid)
                   on conflict (clinic_id) do update
                     set emergency_admins = $2, emergency_emails = $3, updated_by = $4::uuid""",
                clinic, body.alerts.emergency_admins, body.alerts.emergency_emails, user.id,
            )  # fmt: skip
        return await _read(conn, user, clinic)


@router.get("/{clinic}/branding", response_model=Branding)
async def get_branding(user: Annotated[Staff, Depends(staff)], clinic: CLINIC) -> Branding:
    """For every page of the CRM: anyone in the clinic."""
    _member(user, clinic)
    row = await (await get_pool()).fetchrow(
        "select logo, favicon, updated_at from app.clinic_branding where clinic_id = $1", clinic
    )
    if row is None:
        return Branding()
    return Branding(logo=row["logo"], favicon=row["favicon"], updated_at=row["updated_at"].isoformat())


@router.put("/{clinic}/branding", response_model=Branding)
async def put_branding(user: Annotated[Staff, Depends(staff)], clinic: CLINIC, body: BrandingIn) -> Branding:
    """Replaces both images; null removes one (the CRM's own N and icon show again)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await perm.require(conn, user, clinic, "settings", "edit")
        row = await conn.fetchrow(
            """insert into app.clinic_branding (clinic_id, logo, favicon, updated_by)
               values ($1, $2, $3, $4::uuid)
               on conflict (clinic_id) do update set logo = $2, favicon = $3, updated_by = $4::uuid
               returning logo, favicon, updated_at""",
            clinic, body.logo, body.favicon, user.id,
        )  # fmt: skip
    return Branding(logo=row["logo"], favicon=row["favicon"], updated_at=row["updated_at"].isoformat())
