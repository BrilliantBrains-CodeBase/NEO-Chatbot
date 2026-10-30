"""Dashboard → Website install, JSON only: the websites a clinic's chatbot may run on (migration 0020).

A site is added as pending; a Clinic Manager or BB Admin approves or rejects it. Only approved sites are kept
in app.clinics.allowed_origins, which the chat checks on every message, so the widget works on them only.
Every change is in the audit log.
"""

from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from app.api.v1 import widget
from app.chat import guard
from app.core.config import get_settings
from app.core.db import get_pool
from app.crm import permissions as perm
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm/console", tags=["crm"])


class Website(BaseModel):
    id: str
    origin: str
    status: Literal["pending", "approved", "rejected"]
    pages_mode: Literal["all", "only", "except"]
    pages: list[str]
    capture_forms: bool  # the chatbot script also sends this site's own form submissions as leads
    added_by: str | None
    decided_by: str | None
    decided_at: str | None
    created_at: str


class NewSite(BaseModel):
    address: str = Field(min_length=4, max_length=200)  # "neofollicle.com" or a full https address

    @field_validator("address")
    @classmethod
    def _origin(cls, v: str) -> str:
        """Only the site (https://host), whatever page was pasted; https only."""
        raw = v.strip().lower()
        parts = urlsplit(raw if "://" in raw else "https://" + raw)
        if parts.scheme != "https" or not parts.hostname or "." not in parts.hostname:
            raise ValueError("Enter the website's address, e.g. https://neofollicle.com (https only).")
        return f"https://{parts.hostname}" + (f":{parts.port}" if parts.port else "")


class Decision(BaseModel):
    status: Literal["approved", "rejected"]


class Pages(BaseModel):
    pages_mode: Literal["all", "only", "except"] = "all"
    pages: list[str] = Field(default=[], max_length=50)

    @field_validator("pages")
    @classmethod
    def _paths(cls, v: list[str]) -> list[str]:
        out = [p.strip() for p in v if p.strip()]
        for p in out:
            if not p.startswith("/") or " " in p or len(p) > 200:
                raise ValueError(f"'{p}' is not a path; paths start with /, e.g. /hair-transplant/*")
        return out


async def _manager(user: Staff, clinic: str) -> None:
    if not (user.bb_admin or user.roles.get(clinic) == "clinic_manager" or perm.granted(user, clinic)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Website install is for clinic managers and BB Admin.")


async def _list(clinic: str) -> list[Website]:
    rows = await (await get_pool()).fetch(
        """select w.*, a.full_name added, d.full_name decided from app.clinic_websites w
             left join app.profiles a on a.id = w.added_by left join app.profiles d on d.id = w.decided_by
           where w.clinic_id = $1 order by w.created_at""",
        clinic,
    )
    return [
        Website(
            id=str(r["id"]),
            origin=r["origin"],
            status=r["status"],
            pages_mode=r["pages_mode"],
            pages=list(r["pages"]),
            capture_forms=r["capture_forms"],
            added_by=r["added"],
            decided_by=r["decided"],
            decided_at=r["decided_at"].isoformat() if r["decided_at"] else None,
            created_at=r["created_at"].isoformat(),
        )  # fmt: skip
        for r in rows
    ]


async def _change(user: Staff, clinic: str, sql: str, *args: Any) -> list[Website]:
    """One change, then the clinic's allowed sites = its approved sites (the chat sees them within a
    minute)."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)  # audit: who
        done = await conn.execute(sql, *args)
        if done.endswith(" 0"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Website not found.")
        await conn.execute(
            """update app.clinics set allowed_origins = coalesce(
                 (select array_agg(origin order by origin) from app.clinic_websites
                  where clinic_id = $1 and status = 'approved'), '{}') where id = $1""",
            clinic,
        )
    guard._clinics.pop(clinic, None)  # this server sees the change at once
    return await _list(clinic)


class Embed(BaseModel):
    code: str  # empty: no widget is built for this clinic yet
    file: str


@router.get("/{clinic}/websites/embed", response_model=Embed)
async def embed_code(user: Annotated[Staff, Depends(staff)], clinic: str, request: Request) -> Embed:
    """The one line to paste on the clinic's website, just before </body>: this backend's address and the
    clinic's widget file (found in the built widget files, so nothing is fixed here)."""
    await _manager(user, clinic)
    name = widget.loaders().get(clinic)
    if not name:
        return Embed(code="", file="")
    base = (get_settings().public_url or str(request.base_url)).rstrip("/")
    url = f"{base}/v1/widget/{name}.js"
    return Embed(code=f'<script src="{url}" defer></script>', file=url)


@router.get("/{clinic}/websites", response_model=list[Website])
async def websites(user: Annotated[Staff, Depends(staff)], clinic: str) -> list[Website]:
    await _manager(user, clinic)
    return await _list(clinic)


@router.post("/{clinic}/websites", response_model=list[Website])
async def add_website(user: Annotated[Staff, Depends(staff)], clinic: str, body: NewSite) -> list[Website]:
    """Adds a site as pending: the chat does not run there until it is approved."""
    await _manager(user, clinic)
    if await (await get_pool()).fetchval(
        "select 1 from app.clinic_websites where clinic_id = $1 and origin = $2", clinic, body.address
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.address} is already in the list.")
    return await _change(
        user, clinic,
        "insert into app.clinic_websites (clinic_id, origin, added_by) values ($1, $2, $3::uuid)",
        clinic, body.address, user.id,
    )  # fmt: skip


@router.post("/{clinic}/websites/{site}/decision", response_model=list[Website])
async def decide_website(
    user: Annotated[Staff, Depends(staff)], clinic: str, site: str, body: Decision
) -> list[Website]:
    """Approve (the chat runs there) or reject (refused) a site."""
    await _manager(user, clinic)
    return await _change(
        user, clinic,
        """update app.clinic_websites set status = $3, decided_by = $4::uuid, decided_at = now()
           where clinic_id = $1 and id = $2::uuid""",
        clinic, site, body.status, user.id,
    )  # fmt: skip


@router.put("/{clinic}/websites/{site}/pages", response_model=list[Website])
async def website_pages(
    user: Annotated[Staff, Depends(staff)], clinic: str, site: str, body: Pages
) -> list[Website]:
    """Where on the site the bot shows: all pages, only these paths, or all except these."""
    await _manager(user, clinic)
    return await _change(
        user, clinic,
        "update app.clinic_websites set pages_mode = $3, pages = $4 where clinic_id = $1 and id = $2::uuid",
        clinic, site, body.pages_mode, body.pages,
    )  # fmt: skip


class Capture(BaseModel):
    on: bool


@router.put("/{clinic}/websites/{site}/capture", response_model=list[Website])
async def website_capture(
    user: Annotated[Staff, Depends(staff)], clinic: str, site: str, body: Capture
) -> list[Website]:
    """Auto-capture on or off: the chatbot script on this site also sends its form submissions as leads."""
    await _manager(user, clinic)
    return await _change(
        user, clinic,
        "update app.clinic_websites set capture_forms = $3 where clinic_id = $1 and id = $2::uuid",
        clinic, site, body.on,
    )  # fmt: skip


@router.post("/{clinic}/websites/{site}/check")
async def check_install(user: Annotated[Staff, Depends(staff)], clinic: str, site: str) -> dict[str, Any]:
    """Opens the approved website's home page and looks for this clinic's widget code on it."""
    await _manager(user, clinic)
    origin = await (await get_pool()).fetchval(
        "select origin from app.clinic_websites "
        "where clinic_id = $1 and id = $2::uuid and status = 'approved'",
        clinic, site,
    )  # fmt: skip
    if origin is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Approve the website first.")
    name = widget.loaders().get(clinic)
    if not name:
        return {"found": False, "message": "This clinic has no widget yet."}
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, max_redirects=3) as client:
            res = await client.get(origin + "/", headers={"User-Agent": "NEO-Chatbot install check"})
        html = res.text[:2_000_000]
    except httpx.HTTPError:
        return {"found": False, "message": f"Could not open {origin}. Is the website online?"}
    if f"/v1/widget/{name}.js" in html:
        return {"found": True, "message": f"The widget code is on {origin}."}
    return {
        "found": False,
        "message": f"The widget code was not found on {origin}'s home page. Paste it just before </body>.",
    }


@router.delete("/{clinic}/websites/{site}", response_model=list[Website])
async def remove_website(user: Annotated[Staff, Depends(staff)], clinic: str, site: str) -> list[Website]:
    """Removes a site: the chat stops running there."""
    await _manager(user, clinic)
    return await _change(
        user, clinic, "delete from app.clinic_websites where clinic_id = $1 and id = $2::uuid", clinic, site
    )
