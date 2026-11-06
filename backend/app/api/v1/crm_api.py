"""Chatbot → Integrations → Lead & Booking API (migration 0042), JSON only.

An outside system (a website, a landing page, Zapier or Make, a partner app) POSTs JSON to an endpoint's
address with its key in the X-API-Key header. Staff paste a sample of that JSON and match its fields
(nested ones too: "patient.contact.phone") to ours. Each call then makes a lead (cleaned and de-duplicated
like every other source), or a lead and a booking request in the Inbox. A booking's time is held when it
is free;
when it is taken or not given, the request still comes in for the front desk to arrange. Fields not matched
can be kept on the lead as More information. Every call is logged; one repeated with the same external id
answers the first result instead of making a second lead.
"""

import hmac
import json
import re
import secrets
from datetime import date, datetime, time
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.v1.crm_sheets import _lead_from_row, _manager
from app.chat import guard
from app.chat.leads import _clinic, _free_doctors, first_manager
from app.core.config import get_settings
from app.core.db import get_pool
from app.crm import vault, webhooks
from app.crm.auth import Staff, staff

router = APIRouter(tags=["crm"])

# Our fields, by what each call makes. A lead needs a name and a phone or email.
LEAD_FIELDS = {
    "name": "Name", "phone": "Phone", "email": "Email", "treatment": "Treatment", "campaign": "Campaign",
    "source": "Source", "city": "City", "notes": "Notes", "external_id": "External id (no duplicates)",
}  # fmt: skip
BOOKING_FIELDS = {
    "date": "Appointment date", "time": "Appointment time", "doctor": "Doctor", "type": "In-clinic or online",
    "reason": "Reason / message",
}  # fmt: skip
SOURCES = (
    "meta_ads",
    "google_ads",
    "manual",
    "whatsapp",
    "referral",
    "walk_in",
    "phone_call",
    "website_form",
)
EXTRA_MAX = 50  # More information: at most this many fields, each value up to 500 characters
CALLS_PER_MINUTE = 120


class Call(BaseModel):
    at: str
    ok: bool
    status_code: int
    result: str
    lead_code: str | None


class Endpoint(BaseModel):
    id: str
    name: str
    creates: Literal["lead", "booking"]
    active: bool
    url: str
    key: str  # the API key, for the X-API-Key header (admins only)
    sample: Any | None
    paths: list[str]  # every field found in the sample (nested ones as "a.b.c")
    mapping: dict[str, str]  # our field -> path in the payload
    keep_extra: bool
    calls_7d: int
    log: list[Call]  # the last 20 calls


class NewEndpoint(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    creates: Literal["lead", "booking"] = "lead"


class Change(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    creates: Literal["lead", "booking"] | None = None
    sample: Any | None = None
    mapping: dict[str, str] | None = None
    keep_extra: bool | None = None
    active: bool | None = None


class Preview(BaseModel):
    lead: dict[str, str]
    booking: dict[str, str]
    extra: dict[str, str]
    problems: list[str]
    makes: str  # what a call with this payload makes


def flatten(v: Any, path: str = "", out: dict[str, str] | None = None) -> dict[str, str]:
    """Every value in a JSON payload by its path: {"patient": {"phone": "98…"}} -> {"patient.phone": "98…"}.
    Lists by position ("items.0.name"). Empty values are left out; at most 200 fields."""
    out = {} if out is None else out
    if len(out) >= 200:
        return out
    if isinstance(v, dict):
        for k, x in v.items():
            flatten(x, f"{path}.{k}" if path else str(k), out)
    elif isinstance(v, list):
        for i, x in enumerate(v[:20]):
            flatten(x, f"{path}.{i}" if path else str(i), out)
    elif v is not None and str(v).strip() != "":
        out[path] = str(v).strip()[:1000]
    return out


def parse_day(text: str) -> date | None:
    """2026-11-10, 10/11/2026 or 10-11-2026 (day first, as in India), 10 Nov 2026."""
    t = text.strip()[:40]
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$", t)
        if m:
            d, mo, y = map(int, m.groups())
        else:
            for fmt in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"):
                try:
                    return datetime.strptime(t, fmt).date()
                except ValueError:
                    continue
            return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_time(text: str) -> str | None:
    """10:30, 10.30, 10:30 AM, 2 pm, 14:00 -> "HH:MM". None when not a time ("any", "morning")."""
    m = re.match(r"^\s*(\d{1,2})(?:[:.](\d{2}))?\s*([ap]\.?m\.?)?\s*$", text.strip().lower())
    if not m:
        return None
    h, mi, half = int(m[1]), int(m[2] or 0), m[3]
    if half:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if half.startswith("p") else 0)
    if not m[2] and not half:
        return None  # a bare number is not a time
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None


def mode_of(text: str) -> str:
    return "online" if re.search(r"online|video|virtual|tele|remote|zoom|meet", text, re.I) else "in_clinic"


def read(payload: Any, mapping: dict[str, str]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Ours (lead fields), the booking's fields and the fields not matched, from one payload."""
    flat = flatten(payload)
    lead = {f: flat[p] for f, p in mapping.items() if f in LEAD_FIELDS and flat.get(p)}
    booking = {f: flat[p] for f, p in mapping.items() if f in BOOKING_FIELDS and flat.get(p)}
    used = set(mapping.values())
    extra = {p: v[:500] for p, v in flat.items() if p not in used}
    return lead, booking, dict(list(extra.items())[:EXTRA_MAX])


async def _doctor(conn: asyncpg.Connection, clinic: str, text: str) -> asyncpg.Record | None:
    """A doctor by id, else by name ("Dr Sandeep" finds "Dr. Sandeep Mahapatra")."""
    words = [w for w in re.findall(r"[a-z]+", text.lower()) if w not in ("dr", "doctor")]
    found: asyncpg.Record | None = await conn.fetchrow(
        """select id, name from app.doctors where clinic_id = $1 and active
             and (id::text = $2 or ($3::text[] <> '{}' and
               (select bool_and(lower(name) like '%' || w || '%') from unnest($3::text[]) w)))
           order by sort_order limit 1""",
        clinic, text.strip(), words,
    )  # fmt: skip
    return found


async def preview(
    conn: asyncpg.Connection, clinic: str, creates: str, payload: Any, mapping: dict[str, str]
) -> Preview:
    lead, booking, extra = read(payload, mapping)
    problems = []
    if len(lead.get("name", "").strip()) < 2:
        problems.append("No name: match a field to Name.")
    if not (lead.get("phone") or lead.get("email")):
        problems.append("No phone or email: match a field to Phone or Email.")
    shown: dict[str, str] = {}
    makes = "A lead (waiting in the Inbox until it has an owner)."
    if creates == "booking":
        day = parse_day(booking.get("date", "")) if booking.get("date") else None
        at = parse_time(booking.get("time", "")) if booking.get("time") else None
        if booking.get("date") and not day:
            problems.append(f"The date “{booking['date']}” is not understood (use 2026-11-10 or 10/11/2026).")
        if booking.get("time") and not at:
            problems.append(
                f"The time “{booking['time']}” is not understood: the request comes in for any time."
            )
        doctor = await _doctor(conn, clinic, booking["doctor"]) if booking.get("doctor") else None
        if booking.get("doctor") and not doctor:
            problems.append(f"No doctor matches “{booking['doctor']}”: any free doctor is used.")
        shown = {
            "date": day.isoformat() if day else "—",
            "time": at or "any time",
            "doctor": doctor["name"] if doctor else "any free doctor",
            "type": "Online" if mode_of(booking.get("type", "")) == "online" else "In-clinic",
            "reason": booking.get("reason", ""),
        }
        makes = (
            "A lead and a booking request in the Inbox; the time is held when it is free."
            if day
            else "A lead and a call back request (no date given): the front desk arranges the time."
        )
    return Preview(lead=lead, booking=shown, extra=extra, problems=problems, makes=makes)


def _json(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


async def _list(clinic: str, request: Request) -> list[Endpoint]:
    base = (get_settings().public_url or str(request.base_url)).rstrip("/")
    pool = await get_pool()
    out = []
    async with pool.acquire() as conn:
        for e in await conn.fetch(
            "select * from app.api_endpoints where clinic_id = $1 order by created_at", clinic
        ):
            log = await conn.fetch(
                "select * from app.api_log where endpoint_id = $1 order by at desc limit 20", e["id"]
            )
            n = await conn.fetchval(
                """select count(*) from app.api_log where endpoint_id = $1 and ok
                     and at > now() - interval '7 days'""",
                e["id"],
            )
            sample = _json(e["sample"])
            out.append(
                Endpoint(
                    id=str(e["id"]),
                    name=e["name"],
                    creates=e["creates"],
                    active=e["active"],
                    url=f"{base}/v1/integrations/api/{e['id']}",
                    key=await vault.read(conn, e["secret"]) or "",
                    sample=sample,
                    paths=list(flatten(sample)) if sample is not None else [],
                    mapping=dict(_json(e["mapping"])),
                    keep_extra=e["keep_extra"],
                    calls_7d=n,
                    log=[
                        Call(
                            at=x["at"].isoformat(),
                            ok=x["ok"],
                            status_code=x["status_code"],
                            result=x["result"],
                            lead_code=x["lead_code"],
                        )
                        for x in log
                    ],
                )  # fmt: skip
            )
    return out


@router.get("/crm/console/{clinic}/integrations/api", response_model=list[Endpoint])
async def endpoints(user: Annotated[Staff, Depends(staff)], clinic: str, request: Request) -> list[Endpoint]:
    _manager(user, clinic)
    return await _list(clinic, request)


@router.post("/crm/console/{clinic}/integrations/api", response_model=list[Endpoint])
async def add_endpoint(
    user: Annotated[Staff, Depends(staff)], clinic: str, body: NewEndpoint, request: Request
) -> list[Endpoint]:
    """A new endpoint (off until its fields are matched), with its own API key kept in Vault."""
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        secret = await vault.save(conn, "neo_" + secrets.token_urlsafe(24), f"api {clinic} {body.name[:40]}")
        try:
            await conn.execute(
                """insert into app.api_endpoints (clinic_id, name, creates, secret, created_by)
                   values ($1, $2, $3, $4, $5::uuid)""",
                clinic, body.name.strip(), body.creates, secret, user.id,
            )  # fmt: skip
        except asyncpg.UniqueViolationError:
            raise HTTPException(status.HTTP_409_CONFLICT, "An endpoint with that name exists.") from None
    return await _list(clinic, request)


async def _endpoint(conn: asyncpg.Connection, clinic: str, endpoint: str) -> asyncpg.Record:
    e: asyncpg.Record | None = await conn.fetchrow(
        "select * from app.api_endpoints where clinic_id = $1 and id::text = $2 for update", clinic, endpoint
    )
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Endpoint not found.")
    return e


@router.put("/crm/console/{clinic}/integrations/api/{endpoint}", response_model=list[Endpoint])
async def change_endpoint(
    user: Annotated[Staff, Depends(staff)], clinic: str, endpoint: str, body: Change, request: Request
) -> list[Endpoint]:
    """Name, what it makes, the sample, the matching, More information, on or off (only what is sent)."""
    _manager(user, clinic)
    sent = body.model_fields_set
    if "mapping" in sent and body.mapping is not None:
        known = LEAD_FIELDS | BOOKING_FIELDS
        if any(f not in known or not p or len(p) > 200 for f, p in body.mapping.items()):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Match each field to one of ours.")
    if "sample" in sent and len(json.dumps(body.sample)) > 50_000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The sample is too large (50 KB at most).")
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        e = await _endpoint(conn, clinic, endpoint)
        mapping = (
            body.mapping if "mapping" in sent and body.mapping is not None else dict(_json(e["mapping"]))
        )
        if body.active and not ({"name"} <= set(mapping) and {"phone", "email"} & set(mapping)):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Match Name and a Phone or Email field before turning it on.",
            )
        await conn.execute(
            """update app.api_endpoints set name = coalesce($3, name), creates = coalesce($4, creates),
                 sample = case when $5 then $6::jsonb else sample end, mapping = $7::jsonb,
                 keep_extra = coalesce($8, keep_extra), active = coalesce($9, active)
               where id = $1 and clinic_id = $2""",
            e["id"], clinic, body.name.strip() if body.name else None, body.creates, "sample" in sent,
            json.dumps(body.sample) if "sample" in sent else None, json.dumps(mapping), body.keep_extra,
            body.active,
        )  # fmt: skip
    return await _list(clinic, request)


@router.post("/crm/console/{clinic}/integrations/api/{endpoint}/key", response_model=list[Endpoint])
async def new_key(
    user: Annotated[Staff, Depends(staff)], clinic: str, endpoint: str, request: Request
) -> list[Endpoint]:
    """A new API key: the old one stops working at once."""
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        e = await _endpoint(conn, clinic, endpoint)
        secret = await vault.save(conn, "neo_" + secrets.token_urlsafe(24), f"api {clinic} {e['name'][:40]}")
        await conn.execute("update app.api_endpoints set secret = $2 where id = $1", e["id"], secret)
        await vault.delete(conn, e["secret"])
    return await _list(clinic, request)


@router.delete("/crm/console/{clinic}/integrations/api/{endpoint}", response_model=list[Endpoint])
async def delete_endpoint(
    user: Annotated[Staff, Depends(staff)], clinic: str, endpoint: str, request: Request
) -> list[Endpoint]:
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        e = await _endpoint(conn, clinic, endpoint)
        await conn.execute("delete from app.api_endpoints where id = $1", e["id"])
        await vault.delete(conn, e["secret"])
    return await _list(clinic, request)


class TestIn(BaseModel):
    sample: Any | None = None  # left out: the saved sample


@router.post("/crm/console/{clinic}/integrations/api/{endpoint}/test", response_model=Preview)
async def test_endpoint(
    user: Annotated[Staff, Depends(staff)], clinic: str, endpoint: str, body: TestIn
) -> Preview:
    """What a call with this payload would make, by the saved matching. Nothing is saved."""
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn:
        e = await conn.fetchrow(
            "select * from app.api_endpoints where clinic_id = $1 and id::text = $2", clinic, endpoint
        )
        if e is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Endpoint not found.")
        payload = body.sample if body.sample is not None else _json(e["sample"])
        if payload is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Paste a sample payload first.")
        return await preview(conn, clinic, e["creates"], payload, dict(_json(e["mapping"])))


# ---------- the endpoint an outside system calls ----------


def _answer(code: int, body: dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=code, content=body)


async def _log(conn: asyncpg.Connection, e: asyncpg.Record, code: int, result: str, **more: Any) -> None:
    await conn.execute(
        """insert into app.api_log (endpoint_id, clinic_id, ok, status_code, result, lead_code, request_id,
             external_id) values ($1, $2, $3, $4, $5, $6, $7::uuid, $8)""",
        e["id"], e["clinic_id"], 200 <= code < 300, code, result[:300], more.get("lead_code"),
        more.get("request_id"), (more.get("external_id") or None) and str(more["external_id"])[:200],
    )  # fmt: skip


@router.post("/integrations/api/{endpoint}")
async def call(
    endpoint: str, request: Request, x_api_key: Annotated[str | None, Header()] = None
) -> JSONResponse:
    """One lead (or a lead and a booking request) from an outside system, as JSON with the endpoint's key in
    the X-API-Key header. Answers {"ok": true, "lead_code", "request_id", "time_held", "duplicate"} or
    {"ok": false, "error"}."""
    raw = (await request.body())[:100_001]
    if len(raw) > 100_000:
        return _answer(413, {"ok": False, "error": "The payload is too large (100 KB at most)."})
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        e = await conn.fetchrow("select * from app.api_endpoints where id::text = $1", endpoint)
        real = await vault.read(conn, e["secret"]) if e else None
        if e is None or not x_api_key or not real or not hmac.compare_digest(real, x_api_key):
            return _answer(401, {"ok": False, "error": "Invalid API key or address."})
        if not guard.limiter.allow(f"api:{e['id']}", CALLS_PER_MINUTE):
            return _answer(
                429, {"ok": False, "error": f"Too many calls: at most {CALLS_PER_MINUTE} a minute."}
            )
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            await _log(conn, e, 400, "Not JSON")
            return _answer(400, {"ok": False, "error": "Send the body as JSON."})
        if not isinstance(payload, dict):
            await _log(conn, e, 400, "Not a JSON object")
            return _answer(400, {"ok": False, "error": "Send one JSON object."})
        if not e["active"]:
            await _log(conn, e, 403, "Endpoint off")
            return _answer(403, {"ok": False, "error": "This endpoint is switched off in the CRM."})
        clinic = await conn.fetchrow(
            "select id, lead_assignment from app.clinics where id = $1 and active", e["clinic_id"]
        )
        if clinic is None:
            return _answer(403, {"ok": False, "error": "This clinic is not active."})
        mapping = dict(_json(e["mapping"]))
        lead, booking, extra = read(payload, mapping)
        external = lead.pop("external_id", None)
        if external:  # a retry: the first result again
            first = await conn.fetchrow(
                """select lead_code, request_id from app.api_log where endpoint_id = $1 and ok
                     and external_id = $2 order by at limit 1""",
                e["id"], external[:200],
            )  # fmt: skip
            if first:
                return _answer(200, {"ok": True, "lead_code": first["lead_code"],
                                     "request_id": str(first["request_id"]) if first["request_id"] else None,
                                     "time_held": None, "duplicate": True})  # fmt: skip
        try:
            async with conn.transaction():  # a savepoint: a refused call still gets its log line
                result = await _take(conn, e, clinic, lead, booking, extra if e["keep_extra"] else {})
        except ValueError as err:
            await _log(conn, e, 422, str(err), external_id=external)
            return _answer(422, {"ok": False, "error": str(err)})
        await _log(conn, e, 200, result["lead_code"], external_id=external, **result)
    return _answer(200, {"ok": True, **result, "duplicate": False})


async def _take(
    conn: asyncpg.Connection,
    e: asyncpg.Record,
    clinic: asyncpg.Record,
    lead: dict[str, str],
    booking: dict[str, str],
    extra: dict[str, str],
) -> dict[str, Any]:
    source = lead.pop("source", "").strip().lower().replace(" ", "_")
    source = source if source in SOURCES else "api"
    tab = {"tab": e["name"], "mapping": {f: f for f in lead}, "date_order": None}
    code = await _lead_from_row(conn, clinic, e["name"], tab, {"values": lead}, source)
    row = await conn.fetchrow(
        "select id, full_name, phone_e164, email, treatment, assigned_to from app.leads where lead_code = $1",
        code,
    )
    if extra:
        await conn.execute(
            "update app.leads set extra = extra || $2::jsonb where id = $1", row["id"], json.dumps(extra)
        )
    out: dict[str, Any] = {"lead_code": code, "request_id": None, "time_held": None}
    if e["creates"] != "booking":
        return out

    c = await _clinic(conn, clinic["id"])
    tz = ZoneInfo(c["timezone"])
    day = parse_day(booking.get("date", "")) if booking.get("date") else None
    at = parse_time(booking.get("time", "")) if booking.get("time") else None
    mode = mode_of(booking.get("type", ""))
    doctor = await _doctor(conn, clinic["id"], booking["doctor"]) if booking.get("doctor") else None
    reason = booking.get("reason", "")
    data: dict[str, Any] = {
        "name": row["full_name"], "phone": row["phone_e164"], "email": row["email"],
        "treatment": lead.get("treatment") or row["treatment"],
    }  # fmt: skip
    if day is None:  # no date: the front desk calls to arrange one
        kind, data["reason"] = (
            "callback",
            " · ".join(x for x in ("Booking request without a date", reason) if x),
        )
    else:
        kind = "online" if mode == "online" else "book"
        data |= {"date": day.isoformat(), "time": at or "any", "reason": reason or None}
    request: UUID = await conn.fetchval(
        """insert into app.requests (clinic_id, lead_id, type, data) values ($1, $2, $3, $4::jsonb)
           returning id""",
        clinic["id"], row["id"], kind, json.dumps({k: v for k, v in data.items() if v}),
    )  # fmt: skip
    out["request_id"] = str(request)
    appt = None
    if day is not None:
        held = False
        if at and day >= datetime.now(tz).date():
            first = datetime.combine(day, time.fromisoformat(at), tz)
            if first > datetime.now(tz):
                for doc, last in await _free_doctors(
                    conn, c, mode, first, "s_api", str(doctor["id"]) if doctor else None
                ):
                    try:
                        async with conn.transaction():
                            appt = await conn.fetchval(
                                """insert into app.appointments (clinic_id, lead_id, request_id, doctor_id,
                                     type, slot)
                                   values ($1, $2, $3, $4, $5, tstzrange($6, $7, '[)')) returning id""",
                                clinic["id"], row["id"], request, doc, mode, first, last,
                            )  # fmt: skip
                        held = True
                        break
                    except asyncpg.exceptions.ExclusionViolationError:
                        continue
        if not held:  # not free, or no time: the day is kept and staff choose the time
            appt = await conn.fetchval(
                """insert into app.appointments (clinic_id, lead_id, request_id, doctor_id, type,
                     preferred_date)
                   values ($1, $2, $3, $4, $5, $6) returning id""",
                clinic["id"], row["id"], request, doctor["id"] if doctor else None, mode, day,
            )  # fmt: skip
            if at:
                note = f"Asked for {at}, which is not free: choose a time with the patient."
                await conn.execute(
                    "update app.requests set data = data || $2::jsonb where id = $1",
                    request, json.dumps({"reason": " · ".join(x for x in (reason, note) if x)}),
                )  # fmt: skip
        out["time_held"] = held
    owner = row["assigned_to"] or await first_manager(conn, clinic["id"])
    await conn.execute(
        """insert into app.tasks (clinic_id, lead_id, appointment_id, type, title, due_at, assigned_to)
           values ($1, $2, $3, $4, $5, now() + interval '30 minutes', $6)""",
        clinic["id"], row["id"], appt, "confirm_booking" if appt else "call_new_lead",
        f"{'Booking' if appt else 'Call back'} request from {e['name']}", owner,
    )  # fmt: skip
    events: list[tuple[str, dict[str, Any]]] = [
        ("request", {"type": kind, "request_id": str(request), "via": e["name"]})
    ]
    if appt:
        events.append(("appointment", {"appointment_id": str(appt), "status": "pending"}))
    for k, ev in events:
        await conn.execute(
            "insert into app.lead_events (clinic_id, lead_id, kind, data) values ($1, $2, $3, $4::jsonb)",
            clinic["id"], row["id"], k, json.dumps(ev),
        )  # fmt: skip
    webhooks.emit(clinic["id"], "callback_request" if kind == "callback" else "booking_request", {
        "lead_code": code, "type": kind, "name": row["full_name"], "phone": row["phone_e164"],
        "email": row["email"], "treatment": data.get("treatment"), "date": data.get("date"),
        "time": data.get("time"), "reason": data.get("reason"),
    })  # fmt: skip
    return out
