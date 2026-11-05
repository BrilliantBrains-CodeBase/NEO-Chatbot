"""Dashboard → Integrations → WhatsApp (Interakt), JSON only: connect the clinic's Interakt (its API key,
kept in Vault), set the template for each message (name, language, what fills each blank), send a test, and
see the log."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.core.db import get_pool
from app.crm import permissions as perm
from app.crm import vault, whatsapp
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm/console", tags=["crm"])


class Template(BaseModel):
    name: str = Field(default="", max_length=120)  # as approved in Interakt
    language: str = Field(default="en", pattern=r"^[a-z]{2}(_[A-Z]{2})?$")
    values: list[str] = Field(default=[], max_length=10)  # what fills {{1}}, {{2}} ...
    buttons: list[str] = Field(default=[], max_length=2)  # what each "Visit website" button opens
    text: str = Field(default="", max_length=1024)  # the approved text, pasted for the preview only
    on: bool = True

    @field_validator("values")
    @classmethod
    def _known(cls, v: list[str]) -> list[str]:
        if any(x not in whatsapp.VALUES for x in v):
            raise ValueError("A blank is filled with something unknown.")
        return v

    @field_validator("buttons")
    @classmethod
    def _links(cls, v: list[str]) -> list[str]:
        ok = all(x in ("map", "website", "meet") or x.startswith("menu/") for x in v)
        if not ok:
            raise ValueError("A button opens something unknown.")
        return v


class WhatsApp(BaseModel):
    connected: bool
    templates: dict[str, Template]  # purpose -> template
    purposes: dict[str, str]
    values: dict[str, str]
    log: list[dict[str, Any]]  # the last 15 messages
    sample: dict[str, str]  # what each blank would be (the clinic's real details, a sample patient)
    links: dict[str, str]  # what a template button can open
    link_base: str  # the URL to give each "Visit website" button in Interakt, with {{1}} at the end


class Key(BaseModel):
    api_key: str = Field(min_length=10, max_length=300)


class Test(BaseModel):
    purpose: str
    phone: str = Field(min_length=10, max_length=20)


def _base(request: Request) -> str:
    """This backend's public address (where /v1/r/ links live)."""
    return (get_settings().public_url or str(request.base_url)).rstrip("/")


def _manager(user: Staff, clinic: str) -> None:
    if not (user.bb_admin or user.roles.get(clinic) == "clinic_manager" or perm.granted(user, clinic)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Integrations are for admins and Super Admin.")


async def _state(clinic: str, base: str) -> WhatsApp:
    pool = await get_pool()
    acc = await pool.fetchrow("select templates from app.whatsapp_accounts where clinic_id = $1", clinic)
    saved = whatsapp._obj(acc["templates"]) if acc else {}
    log = await pool.fetch(
        "select purpose, to_phone, ok, error, at from app.whatsapp_log where clinic_id = $1 "
        "order by at desc limit 15",
        clinic,
    )
    async with pool.acquire() as conn:
        clinic_values = await whatsapp.clinic_values(conn, clinic)
        links = await whatsapp.link_options(conn, clinic)
    return WhatsApp(
        sample=SAMPLE
        | {"lead_code": f"{clinic}-TEST"}
        | {k: v or "(not set in Clinic info)" for k, v in clinic_values.items()},
        links=links,
        link_base=f"{base}/v1/r/{{{{1}}}}",
        connected=acc is not None,
        templates={p: Template.model_validate(saved.get(p) or {}) for p in whatsapp.PURPOSES},
        purposes=whatsapp.PURPOSES,
        values=whatsapp.VALUES,
        log=[dict(x) | {"at": x["at"].isoformat()} for x in log],
    )


# A sample patient and appointment, for the preview and the test message.
SAMPLE = {
    "name": "Test Patient", "date": "Thu 29 Oct", "time": "11:00 AM", "doctor": "Dr. Test",
    "treatment": "PRP", "meet_link": "https://meet.google.com/abc-defg-hij", "otp": "123456",
}  # fmt: skip


@router.get("/{clinic}/integrations/whatsapp", response_model=WhatsApp)
async def get_whatsapp(
    user: Annotated[Staff, Depends(staff)], clinic: str, base: Annotated[str, Depends(_base)]
) -> WhatsApp:
    _manager(user, clinic)
    return await _state(clinic, base)


@router.post("/{clinic}/integrations/whatsapp", response_model=WhatsApp)
async def connect(
    user: Annotated[Staff, Depends(staff)], clinic: str, base: Annotated[str, Depends(_base)], body: Key
) -> WhatsApp:
    """Keeps the Interakt API key in Vault (connecting again replaces it). Interakt has no "check the key"
    call: the key is checked by the first message (Send test)."""
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        old = await conn.fetchval("select key_secret from app.whatsapp_accounts where clinic_id = $1", clinic)
        key = await vault.save(conn, body.api_key.strip(), f"interakt key {clinic}")
        await conn.execute(
            """insert into app.whatsapp_accounts (clinic_id, key_secret, connected_by)
               values ($1, $2, $3::uuid)
               on conflict (clinic_id) do update set key_secret = $2, connected_by = $3::uuid,
                 connected_at = now()""",
            clinic, key, user.id,
        )  # fmt: skip
        await vault.delete(conn, old)
    return await _state(clinic, base)


@router.delete("/{clinic}/integrations/whatsapp", response_model=WhatsApp)
async def disconnect(
    user: Annotated[Staff, Depends(staff)], clinic: str, base: Annotated[str, Depends(_base)]
) -> WhatsApp:
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        old = await conn.fetchval(
            "delete from app.whatsapp_accounts where clinic_id = $1 returning key_secret", clinic
        )
        await vault.delete(conn, old)
    return await _state(clinic, base)


@router.put("/{clinic}/integrations/whatsapp/templates", response_model=WhatsApp)
async def save_templates(
    user: Annotated[Staff, Depends(staff)],
    clinic: str,
    base: Annotated[str, Depends(_base)],
    body: dict[str, Template],
) -> WhatsApp:
    """The template for each message (only the known messages are kept)."""
    _manager(user, clinic)
    kept = {p: t.model_dump() for p, t in body.items() if p in whatsapp.PURPOSES}
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        done = await conn.execute(
            "update app.whatsapp_accounts set templates = $2::jsonb where clinic_id = $1",
            clinic,
            json.dumps(kept),
        )
        if done.endswith(" 0"):
            raise HTTPException(status.HTTP_409_CONFLICT, "Connect the clinic's Interakt first.")
    return await _state(clinic, base)


@router.post("/{clinic}/integrations/whatsapp/test", response_model=WhatsApp)
async def send_test(
    user: Annotated[Staff, Depends(staff)], clinic: str, base: Annotated[str, Depends(_base)], body: Test
) -> WhatsApp:
    """Sends that message now to a number staff choose, with sample values (the answer is in the log)."""
    _manager(user, clinic)
    sample = SAMPLE | {"lead_code": f"{clinic}-TEST"}
    try:
        await whatsapp.send(clinic, body.purpose, body.phone, sample)
    except whatsapp.WhatsAppError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    return await _state(clinic, base)


# The address a WhatsApp template's "Visit website" button opens: <backend>/v1/r/<clinic>/<what> sends the
# patient on to the clinic's map, website, a menu button's link or their Meet link (kept up to date in the
# CRM).
links = APIRouter(tags=["whatsapp"])


@links.get("/r/{clinic}/{key:path}")
async def open_link(clinic: str, key: str) -> RedirectResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        url = await whatsapp.resolve(conn, clinic, key)
    if not url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link is not available.")
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


class SendTo(BaseModel):
    purpose: str
    lead_code: str | None = Field(default=None, max_length=20)  # a CRM contact: their real details
    phone: str | None = Field(default=None, max_length=20)  # or just a number (sample values)


@router.post("/{clinic}/integrations/whatsapp/send", response_model=WhatsApp)
async def send_now(
    user: Annotated[Staff, Depends(staff)], clinic: str, base: Annotated[str, Depends(_base)], body: SendTo
) -> WhatsApp:
    """Sends one message now. With a CRM contact, its blanks come from them: name, their latest appointment's
    date, time and doctor, the Meet link and the booking ID. With only a number, sample values are sent."""
    _manager(user, clinic)
    data: dict[str, Any] = dict(SAMPLE)
    phone = body.phone
    if body.lead_code:
        row = await (await get_pool()).fetchrow(
            """select l.lead_code, l.full_name, l.phone_e164, l.treatment, d.name doctor, a.meet_link,
                 to_char(coalesce(lower(a.slot) at time zone c.timezone, a.preferred_date),
                         'Dy DD Mon') on_day,
                 to_char(lower(a.slot) at time zone c.timezone, 'HH12:MI AM') at_
               from app.leads l join app.clinics c on c.id = l.clinic_id
                 left join lateral (select * from app.appointments x where x.lead_id = l.id
                                    order by x.created_at desc limit 1) a on true
                 left join app.doctors d on d.id = a.doctor_id
               where l.clinic_id = $1 and l.lead_code = $2 and l.deleted_at is null""",
            clinic, body.lead_code.strip(),
        )  # fmt: skip
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact not found in this clinic.")
        data = {"lead_code": row["lead_code"], "name": row["full_name"], "treatment": row["treatment"],
                "doctor": row["doctor"], "meet_link": row["meet_link"], "date": row["on_day"],
                "time": row["at_"] or "time to be confirmed"}  # fmt: skip
        phone = phone or row["phone_e164"]
    if not phone or len("".join(ch for ch in phone if ch.isdigit())) < 10:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a contact or type a phone number.")
    try:
        await whatsapp.send(clinic, body.purpose, phone, data)
    except whatsapp.WhatsAppError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    return await _state(clinic, base)
