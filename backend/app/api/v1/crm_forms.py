"""Dashboard → Integrations → Website forms (migration 0026), JSON only for the CRM.

The clinic's own forms on its website and landing pages (Unbounce, Elementor, WPForms, Wix, Google Forms,
Typeform ...) send each submission to the form's private address (its own key, kept in Supabase Vault). The
first submission shows the form's fields with an example; staff map them to our fields and turn the form on;
from then on each submission becomes a lead (source "Website form"), cleaned and de-duplicated like Sheet
leads. Forms may post as a normal form (urlencoded) or as JSON.
"""

import hmac
import json
import secrets
from typing import Annotated, Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.v1.crm_sheets import FIELDS, _lead_from_row, _manager
from app.core.config import get_settings
from app.core.db import get_pool
from app.crm import vault
from app.crm.auth import Staff, staff
from app.crm.sheet_values import shown

router = APIRouter(tags=["crm"])
SKIP = {"key", "submit", "g-recaptcha-response", "_wpnonce", "action", "form_id", "page_id"}  # not form data


class Submission(BaseModel):
    at: str
    ok: bool
    result: str  # the lead code, or why not


class Form(BaseModel):
    id: str
    name: str
    active: bool
    fields: list[str]  # as the form sends them
    sample: list[str]  # one example submission, shown the CRM's way
    mapping: dict[str, str]  # form field -> our field
    last_seen_at: str | None
    log: list[Submission]  # the last 10


class NewForm(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class FormSettings(BaseModel):
    active: bool = False
    mapping: dict[str, str] = Field(default={}, max_length=100)


class Link(BaseModel):
    link: str


async def _list(clinic: str) -> list[Form]:
    pool = await get_pool()
    forms = await pool.fetch("select * from app.lead_forms where clinic_id = $1 order by created_at", clinic)
    log = await pool.fetch(
        """select * from (select l.*, row_number() over (partition by form_id order by at desc) n
                          from app.lead_form_log l where clinic_id = $1) x where n <= 10 order by at desc""",
        clinic,
    )
    return [
        Form(
            id=str(f["id"]), name=f["name"], active=f["active"], fields=list(f["fields"]),
            sample=[shown(v) for v in f["sample"]], mapping=dict(_json(f["mapping"])),
            last_seen_at=f["last_seen_at"].isoformat() if f["last_seen_at"] else None,
            log=[Submission(at=x["at"].isoformat(), ok=x["ok"], result=x["result"])
                 for x in log if x["form_id"] == f["id"]],
        )
        for f in forms
    ]  # fmt: skip


def _json(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


@router.get("/crm/console/{clinic}/integrations/forms", response_model=list[Form])
async def forms(user: Annotated[Staff, Depends(staff)], clinic: str) -> list[Form]:
    _manager(user, clinic)
    return await _list(clinic)


@router.post("/crm/console/{clinic}/integrations/forms", response_model=list[Form])
async def add_form(user: Annotated[Staff, Depends(staff)], clinic: str, body: NewForm) -> list[Form]:
    """A new form with its own key (kept in Vault). It is off until its fields are mapped."""
    _manager(user, clinic)
    name = body.name.strip()
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        same = "select 1 from app.lead_forms where clinic_id = $1 and name = $2"
        if await conn.fetchval(same, clinic, name):
            raise HTTPException(status.HTTP_409_CONFLICT, "A form with this name is already added.")
        key = await vault.save(conn, secrets.token_urlsafe(32), f"form {clinic} {name[:40]}")
        await conn.execute(
            "insert into app.lead_forms (clinic_id, name, secret, created_by) values ($1, $2, $3, $4::uuid)",
            clinic, name, key, user.id,
        )  # fmt: skip
    return await _list(clinic)


@router.delete("/crm/console/{clinic}/integrations/forms/{form}", response_model=list[Form])
async def delete_form(user: Annotated[Staff, Depends(staff)], clinic: str, form: str) -> list[Form]:
    """Removes a form: its address stops working at once (leads already made stay)."""
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        old = await conn.fetchval(
            "delete from app.lead_forms where clinic_id = $1 and id::text = $2 returning secret", clinic, form
        )
        if old is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Form not found.")
        await vault.delete(conn, old)
    return await _list(clinic)


@router.put("/crm/console/{clinic}/integrations/forms/{form}", response_model=list[Form])
async def save_form(
    user: Annotated[Staff, Depends(staff)], clinic: str, form: str, body: FormSettings
) -> list[Form]:
    """Turns a form on or off and saves its fields -> ours. On needs Name and Phone or Email."""
    _manager(user, clinic)
    pool = await get_pool()
    row = await pool.fetchrow(
        "select fields from app.lead_forms where clinic_id = $1 and id::text = $2", clinic, form
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Form not found.")
    mapping = {k: f for k, f in body.mapping.items() if f and f != "skip"}
    for k, f in mapping.items():
        if k not in row["fields"] or f not in FIELDS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"'{k}' cannot go to '{f}'.")
    used = list(mapping.values())
    twice = sorted({FIELDS[f] for f in used if used.count(f) > 1})
    if twice:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Two fields go to {', '.join(twice)}.")
    if body.active and not ("name" in used and ("phone" in used or "email" in used)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "To turn it on, choose its Name and Phone (or Email)."
        )
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        await conn.execute(
            "update app.lead_forms set active = $2, mapping = $3::jsonb where id::text = $1",
            form, body.active, json.dumps(mapping),
        )  # fmt: skip
    return await _list(clinic)


@router.get("/crm/console/{clinic}/integrations/forms/{form}/link", response_model=Link)
async def form_link(user: Annotated[Staff, Depends(staff)], clinic: str, form: str, request: Request) -> Link:
    """The form's private address, to paste in the form builder's "send to URL / webhook" setting."""
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn:
        secret = await conn.fetchval(
            "select secret from app.lead_forms where clinic_id = $1 and id::text = $2", clinic, form
        )
        if secret is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Form not found.")
        key = await vault.read(conn, secret)
    base = (get_settings().public_url or str(request.base_url)).rstrip("/")
    return Link(link=f"{base}/v1/integrations/forms/{form}?key={key}")


async def _values(request: Request) -> dict[str, str]:
    """The submission's fields, from JSON (flat, or nested one level) or a normal form post."""
    raw = (await request.body())[:100_000]
    # JSON whatever the label says (Google Apps Script forms send it as text/plain), else a form post.
    is_json = "json" in request.headers.get("content-type", "") or raw.lstrip()[:1] in (b"{", b"[")
    data: Any
    try:
        data = json.loads(raw or b"{}") if is_json else dict(parse_qsl(raw.decode("utf-8", "replace")))
    except ValueError:
        wrong = "Send the form as JSON or a form post."
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, wrong) from None
    if not isinstance(data, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Send the form's fields as an object.")
    out: dict[str, str] = {}
    for k, v in data.items():
        if isinstance(v, dict):  # e.g. {"fields": {...}} or {"data": {...}}
            out |= {str(a): str(b) for a, b in v.items() if not isinstance(b, dict | list)}
        elif isinstance(v, list):
            out[str(k)] = ", ".join(str(x) for x in v)
        elif v is not None:
            out[str(k)] = str(v)
    return {k.strip()[:100]: v.strip()[:1000] for k, v in out.items() if k.strip() and k.strip() not in SKIP}


@router.post("/integrations/forms/{form}")
async def from_form(form: str, key: str, request: Request) -> dict[str, Any]:
    """Called by the form builder with one submission. Until the form is on, it only records the fields."""
    got = await _values(request)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow("select * from app.lead_forms where id::text = $1", form)
        real = await vault.read(conn, row["secret"]) if row else None
        if row is None or not real or not hmac.compare_digest(real, key):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This form's address is not valid. Copy it again.")
        fields = list(dict.fromkeys([*row["fields"], *got]))[:100]
        sample = [got.get(f, "")[:300] for f in fields] if got else list(row["sample"])
        await conn.execute(
            "update app.lead_forms set fields = $2, sample = $3, last_seen_at = now() where id = $1",
            row["id"], fields, sample,
        )  # fmt: skip
        clinic = await conn.fetchrow(
            "select id, lead_assignment from app.clinics where id = $1 and active", row["clinic_id"]
        )
        if not row["active"] or clinic is None:
            ok, result = False, "Fields received. Map them and turn the form on."
        else:
            tab = {"tab": "form", "mapping": row["mapping"], "date_order": None}
            try:
                result = await _lead_from_row(conn, clinic, row["name"], tab, {"values": got}, "website_form")
                ok = True
            except ValueError as e:
                ok, result = False, str(e)
        await conn.execute(
            "insert into app.lead_form_log (form_id, clinic_id, ok, result) values ($1, $2, $3, $4)",
            row["id"], row["clinic_id"], ok, result[:300],
        )  # fmt: skip
    return {"ok": ok, "result": result}
