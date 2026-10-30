"""The chatbot widget's files (frontend/widgets build), served by the backend itself. A clinic's website
includes <backend>/v1/widget/<file>.js (Dashboard → Website install gives the line); the widget then talks to
the same backend, which runs it only on the clinic's approved websites. Nothing here names a clinic: each
loader file says which clinic it is for (its clinic ID), and that is read from the built files.
"""

import base64
import binascii
import fnmatch
import json
import re
import time
import zlib
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote_to_bytes, urlsplit

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, Response

from app.api.v1.crm_console import Appearance, Template
from app.api.v1.crm_sheets import _lead_from_row
from app.chat import guard, main_template
from app.core.config import get_settings
from app.core.db import get_pool

router = APIRouter(prefix="/widget", tags=["widget"])

FILE = re.compile(r"^[a-z0-9-]+(\.app)?\.js$")  # a loader (neo-follicle.js) or its full widget (.app.js)
_found: tuple[float, dict[str, str]] = (0.0, {})


def folder() -> Path:
    """The built widget files: WIDGET_DIR, else frontend/widgets/dist next to the backend."""
    configured = get_settings().widget_dir
    return Path(configured) if configured else Path(__file__).resolve().parents[4] / "frontend/widgets/dist"


def loaders() -> dict[str, str]:
    """Clinic ID -> its loader's name, read from the built loaders (checked again after a minute)."""
    global _found
    if time.monotonic() - _found[0] < 60:
        return _found[1]
    out: dict[str, str] = {}
    for f in sorted(folder().glob("*.js")):
        if f.name.endswith(".app.js"):
            continue
        ids = set(re.findall(r"\bCL\d{2,3}\b", f.read_text(encoding="utf-8", errors="ignore")))
        if len(ids) == 1:  # a loader is for exactly one clinic
            out[ids.pop()] = f.stem
    _found = (time.monotonic(), out)
    return out


def page_shown(mode: str, pages: list[str], path: str) -> bool:
    """The site's pages rule: every page, only these paths, or every page except these ("*" = anything)."""
    if mode == "all":
        return True
    hit = any(fnmatch.fnmatchcase(path, p) or path.rstrip("/") == p.rstrip("/") for p in pages)
    return hit if mode == "only" else not hit


@router.get("/show")
async def show(request: Request, clinic: str, path: str = "/") -> dict[str, bool]:
    """Should the chatbot show on this page, and should the page's own forms be sent as leads (capture)?"""
    shown = await _shown(request, clinic, path)
    capture = await _capture_site(clinic, request.headers.get("origin") or "") is not None
    return {"show": shown, "capture": capture}


# Auto-capture: a form field's name (or label) -> our field. First match wins; the rest go in the notes.
GUESS = [
    ("email", re.compile(r"e-?mail", re.I)),
    ("phone", re.compile(r"phone|mobile|tel\b|contact.?(no|num)|whats.?app|cell", re.I)),
    ("name", re.compile(r"name", re.I)),
    ("treatment", re.compile(r"treatment|service|department|special|doctor|concern|procedure", re.I)),
    ("notes", re.compile(r"message|comment|query|question|note|description|detail|problem|reason", re.I)),
]


def guess(fields: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Which form field is the name, phone, email, treatment and message (by its name, else its value).
    Returns (values, mapping) ready for a lead: a first and a last name become one Name."""
    values = dict(fields)
    first = next((k for k in values if re.search(r"first.?name|fname", k, re.I)), None)
    last = next((k for k in values if re.search(r"last.?name|surname|lname", k, re.I)), None)
    if first and last:
        values["Name"] = f"{values.pop(first)} {values.pop(last)}"
    mapping: dict[str, str] = {}
    for field, rule in GUESS:
        key = next((k for k in values if k not in mapping and rule.search(k)), None)
        if key is None and field == "email":
            key = next((k for k, v in values.items() if k not in mapping and EMAIL.fullmatch(v)), None)
        if key is None and field == "phone":
            key = next((k for k, v in values.items() if k not in mapping and PHONE.fullmatch(v)), None)
        if key is not None:
            mapping[key] = field
    return values, mapping


EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}")
PHONE = re.compile(r"\+?[\d\s()-]{10,18}")


@router.post("/form")
async def captured_form(request: Request, clinic: str) -> dict[str, bool]:
    """A form submitted on the clinic's approved website (auto-capture on), sent by the chatbot script.
    It becomes a lead (source Website form) when it has a name and a phone or email."""
    origin = request.headers.get("origin") or ""
    site = await _capture_site(clinic, origin)
    ip = guard.client_ip(request.headers, request.client.host if request.client else None)
    if site is None or not guard.limiter.allow(f"form:{ip}", 5):
        return {"ok": False}
    try:
        sent = json.loads((await request.body())[:50_000] or b"{}")
    except ValueError:
        return {"ok": False}
    raw = sent.get("fields") if isinstance(sent, dict) else None
    if not isinstance(raw, dict):
        return {"ok": False}
    items = list(raw.items())[:60]
    fields = {str(k).strip()[:100]: str(v).strip()[:1000] for k, v in items if str(v).strip()}
    values, mapping = guess(fields)
    page = str(sent.get("page") or "")[:300]
    values |= {"Page": page} if page.startswith(site) else {}
    utm = sent.get("utm") if isinstance(sent.get("utm"), dict) else {}
    values |= {str(k)[:40]: str(v)[:200] for k, v in utm.items() if str(k).startswith("utm_")}
    if values.get("utm_campaign"):
        mapping["utm_campaign"] = "campaign"
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        sql = "select id, lead_assignment from app.clinics where id = $1 and active"
        row = await conn.fetchrow(sql, clinic)
        if row is None:
            return {"ok": False}
        tab = {"tab": "auto-capture", "mapping": mapping, "date_order": None}
        name = "Website form: " + (urlsplit(page).path or "/") if page else "Website form"
        try:
            await _lead_from_row(conn, row, name[:80], tab, {"values": values}, "website_form")
        except ValueError:
            return {"ok": False}
    return {"ok": True}


async def _capture_site(clinic: str, origin: str) -> str | None:
    """The approved website (its origin) whose own forms are sent as leads, if this page's site is one."""
    host = origin.rstrip("/").replace("://www.", "://")
    found = await (await get_pool()).fetchval(
        """select origin from app.clinic_websites where clinic_id = $1 and status = 'approved'
             and capture_forms and replace(origin, '://www.', '://') = $2""",
        clinic, host,
    )  # fmt: skip
    return str(found) if found else None


async def _shown(request: Request, clinic: str, path: str) -> bool:
    """Should the chatbot show on this page? Only on the clinic's approved website (the page's own Origin)
    and on the pages its rule allows, unless the clinic switched it off (Appearance → Enabled, as published).
    The loader asks once per page."""
    origin = (request.headers.get("origin") or "").rstrip("/")
    known = await guard.get_clinic(clinic)
    if known is None or not guard.origin_allowed(known, origin):
        return False
    off = await (await get_pool()).fetchval(
        "select published->'appearance'->'look'->>'enabled' = 'false' from app.clinic_settings "
        "where clinic_id = $1",
        clinic,
    )
    if off:
        return False
    host = origin.replace("://www.", "://")
    site = await (await get_pool()).fetchrow(
        """select pages_mode, pages from app.clinic_websites where clinic_id = $1 and status = 'approved'
             and replace(origin, '://www.', '://') = $2""",
        clinic, host,
    )  # fmt: skip
    if site is None:  # e.g. a local test page in development
        return True
    return page_shown(site["pages_mode"], list(site["pages"]), path[:300])


async def _published(clinic: str) -> dict[str, Any]:
    """The published Appearance, Templates and contact, a followed part being the main template's."""
    async with (await get_pool()).acquire() as conn:
        row = await conn.fetchrow(
            """select published->'appearance' appearance, published->'template' template,
                 published->'contact' contact from app.clinic_settings where clinic_id = $1""",
            clinic,
        )
        saved = {k: json.loads(row[k]) for k in ("appearance", "template", "contact") if row and row[k]}
        await main_template.apply(conn, clinic, saved)
    return {k: v for k, v in saved.items() if v}


async def _published_look(clinic: str) -> dict[str, Any] | None:
    saved = (await _published(clinic)).get("appearance")
    return Appearance.model_validate(saved).model_dump() if saved else None


@router.get("/config/{clinic}")
async def config(request: Request, clinic: str) -> dict[str, Any]:
    """The clinic's published Dashboard → Appearance and Templates (the menu's style), for the widget (None
    until first published: the widget keeps its built-in look). Nothing private: what any visitor sees."""
    if await guard.get_clinic(clinic) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such clinic.")
    saved = await _published(clinic)
    look = Appearance.model_validate(saved["appearance"]).model_dump() if saved.get("appearance") else None
    if look and look["look"]["logo"].startswith("data:"):  # an upload: its own file, not in every page view
        base = (get_settings().public_url or str(request.base_url)).rstrip("/")
        version = zlib.crc32(look["look"]["logo"].encode())
        look["look"]["logo"] = f"{base}/v1/widget/logo/{clinic}?v={version:x}"
    template = Template.model_validate(saved["template"]).model_dump() if saved.get("template") else None
    return {"appearance": look, "template": template, "contact": _contact(saved.get("contact"))}


def _contact(saved: Any) -> dict[str, str]:
    """The mobile contact row's Call and WhatsApp (Clinic info → Contact & hours, as published)."""
    c = dict(saved or {})
    wa = re.sub(r"\D", "", c.get("whatsapp") or "")
    text = c.get("whatsapp_message") or ""
    return {
        "phone": c.get("phone") or "",
        "whatsapp": f"https://wa.me/{wa}" + (f"?text={quote(text)}" if text else "") if wa else "",
    }


@router.get("/logo/{clinic}")
async def logo(clinic: str) -> Response:
    """The clinic's uploaded logo (Dashboard → Appearance), as an image file."""
    look = await _published_look(clinic)
    url = look["look"]["logo"] if look else ""
    head, _, data = url.partition(",")
    kind = head[5:].split(";")[0]
    if not url.startswith("data:image/") or not data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No uploaded logo.")
    try:
        body = base64.b64decode(data) if head.endswith(";base64") else unquote_to_bytes(data)
    except binascii.Error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No uploaded logo.") from None
    return Response(body, media_type=kind, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/{name}")
async def widget_file(name: str) -> FileResponse:
    path = folder() / name
    if not FILE.fullmatch(name) or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such widget file.")
    return FileResponse(
        path, media_type="application/javascript", headers={"Cache-Control": "public, max-age=300"}
    )
