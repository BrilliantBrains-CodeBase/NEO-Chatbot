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
from urllib.parse import unquote_to_bytes

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, Response

from app.api.v1.crm_console import Appearance, Template
from app.chat import guard
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
        ids = set(re.findall(r"\bCL\d{2}\b", f.read_text(encoding="utf-8", errors="ignore")))
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
    """Should the chatbot show on this page? Only on the clinic's approved website (the page's own Origin)
    and on the pages its rule allows. The loader asks once per page."""
    origin = (request.headers.get("origin") or "").rstrip("/")
    known = await guard.get_clinic(clinic)
    if known is None or not guard.origin_allowed(known, origin):
        return {"show": False}
    host = origin.replace("://www.", "://")
    site = await (await get_pool()).fetchrow(
        """select pages_mode, pages from app.clinic_websites where clinic_id = $1 and status = 'approved'
             and replace(origin, '://www.', '://') = $2""",
        clinic, host,
    )  # fmt: skip
    if site is None:  # e.g. a local test page in development
        return {"show": True}
    return {"show": page_shown(site["pages_mode"], list(site["pages"]), path[:300])}


async def _published_look(clinic: str) -> dict[str, Any] | None:
    saved = await (await get_pool()).fetchval(
        "select published->'appearance' from app.clinic_settings where clinic_id = $1", clinic
    )
    if not saved or saved == "null":
        return None
    return Appearance.model_validate(json.loads(saved) if isinstance(saved, str) else saved).model_dump()


@router.get("/config/{clinic}")
async def config(request: Request, clinic: str) -> dict[str, Any]:
    """The clinic's published Dashboard → Appearance and Templates (the menu's style), for the widget (None
    until first published: the widget keeps its built-in look). Nothing private: what any visitor sees."""
    if await guard.get_clinic(clinic) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such clinic.")
    look = await _published_look(clinic)
    if look and look["look"]["logo"].startswith("data:"):  # an upload: its own file, not in every page view
        base = (get_settings().public_url or str(request.base_url)).rstrip("/")
        version = zlib.crc32(look["look"]["logo"].encode())
        look["look"]["logo"] = f"{base}/v1/widget/logo/{clinic}?v={version:x}"
    tpl = await (await get_pool()).fetchval(
        "select published->'template' from app.clinic_settings where clinic_id = $1", clinic
    )
    template = Template.model_validate(json.loads(tpl)).model_dump() if tpl and tpl != "null" else None
    return {"appearance": look, "template": template}


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
