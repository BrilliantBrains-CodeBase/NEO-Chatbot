"""Dashboard → Integrations → WhatsApp (Interakt), JSON only: connect the clinic's Interakt (its API key,
kept in Vault), set the template for each message (name, language, what fills each blank), send a test, and
see the log."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.core.db import get_pool
from app.crm import vault, whatsapp
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm/console", tags=["crm"])


class Template(BaseModel):
    name: str = Field(default="", max_length=120)  # as approved in Interakt
    language: str = Field(default="en", pattern=r"^[a-z]{2}(_[A-Z]{2})?$")
    values: list[str] = Field(default=[], max_length=10)  # what fills {{1}}, {{2}} ...
    on: bool = True

    @field_validator("values")
    @classmethod
    def _known(cls, v: list[str]) -> list[str]:
        if any(x not in whatsapp.VALUES for x in v):
            raise ValueError("A blank is filled with something unknown.")
        return v


class WhatsApp(BaseModel):
    connected: bool
    templates: dict[str, Template]  # purpose -> template
    purposes: dict[str, str]
    values: dict[str, str]
    log: list[dict[str, Any]]  # the last 15 messages
    sample: dict[str, str]  # what each blank would be (the clinic's real details, a sample patient)


class Key(BaseModel):
    api_key: str = Field(min_length=10, max_length=300)


class Test(BaseModel):
    purpose: str
    phone: str = Field(min_length=10, max_length=20)


def _manager(user: Staff, clinic: str) -> None:
    if not (user.bb_admin or user.roles.get(clinic) == "clinic_manager"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Integrations are for clinic managers and BB Admin.")


async def _state(clinic: str) -> WhatsApp:
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
    return WhatsApp(
        sample=SAMPLE
        | {"lead_code": f"{clinic}-TEST"}
        | {k: v or "(not set in Clinic info)" for k, v in clinic_values.items()},
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
async def get_whatsapp(user: Annotated[Staff, Depends(staff)], clinic: str) -> WhatsApp:
    _manager(user, clinic)
    return await _state(clinic)


@router.post("/{clinic}/integrations/whatsapp", response_model=WhatsApp)
async def connect(user: Annotated[Staff, Depends(staff)], clinic: str, body: Key) -> WhatsApp:
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
    return await _state(clinic)


@router.delete("/{clinic}/integrations/whatsapp", response_model=WhatsApp)
async def disconnect(user: Annotated[Staff, Depends(staff)], clinic: str) -> WhatsApp:
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        old = await conn.fetchval(
            "delete from app.whatsapp_accounts where clinic_id = $1 returning key_secret", clinic
        )
        await vault.delete(conn, old)
    return await _state(clinic)


@router.put("/{clinic}/integrations/whatsapp/templates", response_model=WhatsApp)
async def save_templates(
    user: Annotated[Staff, Depends(staff)], clinic: str, body: dict[str, Template]
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
    return await _state(clinic)


@router.post("/{clinic}/integrations/whatsapp/test", response_model=WhatsApp)
async def send_test(user: Annotated[Staff, Depends(staff)], clinic: str, body: Test) -> WhatsApp:
    """Sends that message now to a number staff choose, with sample values (the answer is in the log)."""
    _manager(user, clinic)
    sample = SAMPLE | {"lead_code": f"{clinic}-TEST"}
    try:
        await whatsapp.send(clinic, body.purpose, body.phone, sample)
    except whatsapp.WhatsAppError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    return await _state(clinic)
