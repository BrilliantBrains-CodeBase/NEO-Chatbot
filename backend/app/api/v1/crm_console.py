"""Dashboard (the chatbot console) in the CRM, JSON only: each clinic's widget settings as a draft that staff
edit, then publish (migration 0019). Every value is checked here; the browser never writes the tables.
Clinic managers and BB Admin only. The live chatbot does not read these settings until it is switched over."""

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.core.db import get_pool
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm/console", tags=["crm"])

COLOR = r"^#[0-9A-Fa-f]{6}$"


class Look(BaseModel):
    name: str = Field(default="Arya", min_length=2, max_length=40)
    status_line: str = Field(default="Instant Reply", max_length=13)
    enabled: bool = True
    logo: str = Field(default="", max_length=300_000)  # https URL or a small data:image (upload)
    avatar_letter: str = Field(default="A", min_length=1, max_length=2)

    @field_validator("logo")
    @classmethod
    def _logo(cls, v: str) -> str:
        if v and not (v.startswith("https://") or v.startswith("data:image/")):
            raise ValueError("Use an https:// image address or upload an image.")
        return v


class Colours(BaseModel):
    main: str = Field(default="#3E74D9", pattern=COLOR)
    highlight: str = Field(default="#FFCC70", pattern=COLOR)


class WidgetStyle(BaseModel):
    size: Literal["small", "medium", "large"] = "medium"
    radius: Literal["square", "rounded", "round"] = "rounded"
    border: Literal["none", "subtle", "strong"] = "subtle"
    shadow: Literal["none", "soft", "strong"] = "soft"
    header_text: str = Field(default="Instant Reply · Powered by Brilliant Brains", max_length=80)
    footer_on: bool = True
    footer_text: str = Field(default="Not For Medical Advice · Powered By Brilliant Brains", max_length=80)
    footer_link: str = Field(
        default="https://brilliantbrains.ai", max_length=300, pattern=r"^(https://\S+)?$"
    )


class Launcher(BaseModel):
    position: Literal["bottom_right", "bottom_left"] = "bottom_right"
    offset_x: int = Field(default=24, ge=0, le=200)
    offset_y: int = Field(default=24, ge=0, le=200)
    shape: Literal["pill", "rounded", "circle"] = "pill"
    size: Literal["small", "medium", "large"] = "medium"
    background: str = Field(default="#3E74D9", pattern=COLOR)
    icon: Literal["chat", "logo"] = "chat"
    icon_color: str = Field(default="#FFFFFF", pattern=COLOR)
    border: Literal["none", "subtle", "strong"] = "none"
    label_on: bool = True
    label_text: str = Field(default="Chat with us", max_length=32)
    label_after_s: int = Field(default=0, ge=0, le=120)  # 0: shown as soon as the page loads
    notification_dot: bool = True
    opens_as: Literal["panel", "full"] = "panel"
    open_on_first_visit: bool = False


class Appearance(BaseModel):
    look: Look = Look()
    colours: Colours = Colours()
    widget: WidgetStyle = WidgetStyle()
    launcher: Launcher = Launcher()


# The sections of the settings; each later screen (Templates, Menu buttons, ...) adds its own.
SECTIONS: dict[str, type[BaseModel]] = {"appearance": Appearance}


class Settings(BaseModel):
    clinic: str
    draft: dict[str, Any]  # every section, filled with defaults where nothing is saved yet
    published: dict[str, Any]
    version: int  # 0: never published
    changed: bool  # the draft differs from what is published
    published_at: str | None
    updated_at: str | None


def _filled(saved: dict[str, Any]) -> dict[str, Any]:
    """Each section checked and completed with defaults (old drafts keep working when fields are added)."""
    return {
        name: model.model_validate(saved.get(name) or {}).model_dump() for name, model in SECTIONS.items()
    }


async def _manager(user: Staff, clinic: str) -> None:
    if not (user.bb_admin or user.roles.get(clinic) == "clinic_manager"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The Dashboard is for clinic managers and BB Admin.")


async def _load(clinic: str) -> Settings:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if not await conn.fetchval("select 1 from app.clinics where id = $1 and active", clinic):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown clinic.")
        r = await conn.fetchrow("select * from app.clinic_settings where clinic_id = $1", clinic)
        bot = await conn.fetchval("select bot_name from app.clinics where id = $1", clinic)
    draft_saved = _json(r["draft"]) if r else {}
    published_saved = _json(r["published"]) if r else {}
    if not draft_saved.get("appearance"):  # start from the clinic's bot name
        draft_saved["appearance"] = {"look": {"name": bot, "avatar_letter": bot[:1].upper()}}
    draft, published = _filled(draft_saved), _filled(published_saved) if published_saved else {}
    return Settings(
        clinic=clinic, draft=draft, published=published, version=r["version"] if r else 0,
        changed=draft != published,
        published_at=r["published_at"].isoformat() if r and r["published_at"] else None,
        updated_at=r["updated_at"].isoformat() if r else None,
    )  # fmt: skip


def _json(v: Any) -> dict[str, Any]:
    return dict(json.loads(v) if isinstance(v, str) else v or {})


@router.get("/{clinic}/settings", response_model=Settings)
async def get_settings_(user: Annotated[Staff, Depends(staff)], clinic: str) -> Settings:
    await _manager(user, clinic)
    return await _load(clinic)


@router.put("/{clinic}/settings/{section}", response_model=Settings)
async def save_draft(
    user: Annotated[Staff, Depends(staff)], clinic: str, section: str, body: dict[str, Any]
) -> Settings:
    """Saves one section of the draft (checked against its rules). Patients see nothing until it is
    published."""
    await _manager(user, clinic)
    model = SECTIONS.get(section)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown settings section.")
    try:
        value = model.model_validate(body).model_dump()
    except ValidationError as e:  # the first wrong field, in words staff can act on
        err = e.errors()[0]
        field = " → ".join(str(x) for x in err["loc"])
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field}: {err['msg']}") from None
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)  # audit: who
        await conn.execute(
            """insert into app.clinic_settings (clinic_id, draft, updated_by)
               values ($1, jsonb_build_object($2::text, $3::jsonb), $4::uuid)
               on conflict (clinic_id) do update
                 set draft = app.clinic_settings.draft || jsonb_build_object($2::text, $3::jsonb),
                     updated_by = $4::uuid""",
            clinic, section, json.dumps(value), user.id,
        )  # fmt: skip
    return await _load(clinic)


@router.post("/{clinic}/publish", response_model=Settings)
async def publish(user: Annotated[Staff, Depends(staff)], clinic: str) -> Settings:
    """The draft becomes what the widget shows, as a new numbered version (kept for roll back)."""
    await _manager(user, clinic)
    current = await _load(clinic)
    if not current.changed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing new to publish.")
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        version = await conn.fetchval(
            """insert into app.clinic_settings (clinic_id, draft, published, version, published_by,
                 published_at, updated_by)
               values ($1, $2::jsonb, $2::jsonb, 1, $3::uuid, now(), $3::uuid)
               on conflict (clinic_id) do update set draft = $2::jsonb, published = $2::jsonb,
                 version = app.clinic_settings.version + 1, published_by = $3::uuid, published_at = now()
               returning version""",
            clinic, json.dumps(current.draft), user.id,
        )  # fmt: skip
        await conn.execute(
            """insert into app.clinic_setting_versions (clinic_id, version, settings, published_by)
               values ($1, $2, $3::jsonb, $4::uuid)""",
            clinic, version, json.dumps(current.draft), user.id,
        )  # fmt: skip
    return await _load(clinic)
