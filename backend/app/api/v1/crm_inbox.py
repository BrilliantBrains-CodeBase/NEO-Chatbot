"""CRM Inbox (JSON only): the requests patients made in the chatbot, and what staff do with them."""

import json
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.v1.crm import Count, _event, can_edit, can_see
from app.core.db import get_pool
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm", tags=["crm"])

TYPES = ["book", "online", "cancel", "reschedule", "callback", "question"]


class Appt(BaseModel):
    id: str
    start: str | None  # ISO time; None when the patient chose "Any time"
    day: str | None  # the clinic-local day
    doctor: str | None
    type: str
    status: str


class InboxItem(BaseModel):
    id: str
    type: str
    status: str
    created_at: str
    lead_code: str
    name: str
    phone: str | None
    email: str | None
    treatment: str | None
    reason: str | None
    date: str | None  # the asked day (book, online, reschedule)
    time: str | None  # "10:30" or "any"
    booked_date: str | None  # cancel and reschedule: the day the patient says they were booked
    match_status: str | None  # matched | no_match
    appointment: Appt | None  # the booking's appointment, or the matched one for cancel and reschedule


class Inbox(BaseModel):
    pending: list[Count]  # pending requests per type, for the tabs, the menu and the bell
    items: list[InboxItem]


SELECT = """select r.id, r.type, r.status, r.created_at, r.data, r.match_status, r.clinic_id, r.lead_id,
    l.lead_code, l.full_name, l.phone_e164, l.email, a.id a_id, lower(a.slot) a_start,
    coalesce((lower(a.slot) at time zone c.timezone)::date, a.preferred_date) a_day, d.name a_doctor,
    a.type a_type, a.status a_status, a.doctor_id a_doctor_id
  from app.requests r join app.leads l on l.id = r.lead_id join app.clinics c on c.id = r.clinic_id
  left join app.appointments a on a.id = coalesce(r.matched_appointment_id,
    (select id from app.appointments where request_id = r.id order by created_at limit 1))
  left join app.doctors d on d.id = a.doctor_id"""


def _item(r: asyncpg.Record) -> InboxItem:
    data: dict[str, Any] = json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]
    appt = None
    if r["a_id"]:
        appt = Appt(
            id=str(r["a_id"]),
            start=r["a_start"].isoformat() if r["a_start"] else None,
            day=r["a_day"].isoformat() if r["a_day"] else None,
            doctor=r["a_doctor"],
            type=r["a_type"],
            status=r["a_status"],
        )
    return InboxItem(
        id=str(r["id"]), type=r["type"], status=r["status"], created_at=r["created_at"].isoformat(),
        lead_code=r["lead_code"], name=r["full_name"], phone=r["phone_e164"], email=r["email"],
        treatment=data.get("treatment"), reason=data.get("reason"), date=data.get("date"),
        time=data.get("time"), booked_date=data.get("booked_date"), match_status=r["match_status"],
        appointment=appt,
    )  # fmt: skip


@router.get("/inbox", response_model=Inbox)
async def inbox(
    user: Annotated[Staff, Depends(staff)],
    clinic: Annotated[str, Query(pattern=r"^CL\d{2}$")],
    type: Annotated[
        Literal["book", "online", "cancel", "reschedule", "callback", "question"] | None, Query()
    ] = None,
    done: bool = False,
) -> Inbox:
    """Pending requests (oldest first, so nobody waits longest), or the latest 100 handled ones."""
    can_see(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn:
        counts = {
            r[0]: r[1]
            for r in await conn.fetch(
                "select type, count(*) from app.requests where clinic_id = $1 and status = 'pending'"
                " group by 1",
                clinic,
            )
        }
        rows = await conn.fetch(
            f"""{SELECT} where r.clinic_id = $1 and ($2::text is null or r.type = $2)
                and {"r.status <> 'pending'" if done else "r.status = 'pending'"}
                order by r.created_at {"desc" if done else "asc"} limit 100""",
            clinic, type,
        )  # fmt: skip
    return Inbox(
        pending=[Count(key=t, count=counts.get(t, 0)) for t in TYPES], items=[_item(r) for r in rows]
    )


class Reject(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class Done(BaseModel):
    outcome: Literal["answered", "no_answer", "busy", "wrong_number"] = "answered"
    note: str = Field(default="", max_length=2000)


async def _pending(conn: asyncpg.Connection, user: Staff, request_id: str) -> asyncpg.Record:
    try:
        r = await conn.fetchrow(f"{SELECT} where r.id = $1::uuid for update of r", request_id)
    except asyncpg.DataError:
        r = None
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found.")
    can_edit(user, r["clinic_id"])
    if r["status"] != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "This request is already handled.")
    await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)  # audit: who did it
    return r


async def _close(
    conn: asyncpg.Connection, r: asyncpg.Record, user: Staff, state: str, data: dict[str, Any]
) -> None:
    await conn.execute(
        "update app.requests set status = $2, updated_at = now() where id = $1", r["id"], state
    )
    lead = {"id": r["lead_id"], "clinic_id": r["clinic_id"]}
    await _event(conn, lead, user, "request", {"type": r["type"], "status": state, **data})


async def _set_appt(conn: asyncpg.Connection, appt: Any, user: Staff, state: str) -> None:
    await conn.execute(
        """update app.appointments set status = $2, updated_at = now(),
             confirmed_by = case when $2 = 'confirmed' then $3::uuid else confirmed_by end,
             confirmed_at = case when $2 = 'confirmed' then now() else confirmed_at end
           where id = $1""",
        appt, state, user.id,
    )  # fmt: skip


async def _new_slot(conn: asyncpg.Connection, r: asyncpg.Record, data: dict[str, Any], user: Staff) -> None:
    """The appointment a reschedule moves to: same doctor and type, the asked day and time."""
    c = await conn.fetchrow("select timezone, slot_minutes from app.clinics where id = $1", r["clinic_id"])
    day = date.fromisoformat(data["date"])
    if data.get("time") in (None, "any"):
        start, end = None, None
    else:
        start = datetime.combine(day, time.fromisoformat(data["time"]), ZoneInfo(c["timezone"]))
        end = start + timedelta(minutes=c["slot_minutes"])
    try:
        async with conn.transaction():
            await conn.execute(
                """insert into app.appointments (clinic_id, lead_id, request_id, doctor_id, type, slot,
                     preferred_date, status, rescheduled_from_id, confirmed_by, confirmed_at)
                   values ($1, $2, $3, $4, $5, case when $6::timestamptz is null then null
                     else tstzrange($6, $7, '[)') end, $8, 'confirmed', $9, $10::uuid, now())""",
                r["clinic_id"], r["lead_id"], r["id"], r["a_doctor_id"], r["a_type"] or "in_clinic",
                start, end, None if start else day, r["a_id"], user.id,
            )  # fmt: skip
    except asyncpg.exceptions.ExclusionViolationError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The doctor is already booked at that time. Call the patient for another.",
        ) from None


@router.post("/requests/{request_id}/approve", response_model=InboxItem)
async def approve(user: Annotated[Staff, Depends(staff)], request_id: str) -> InboxItem:
    """Booking or online consult: the appointment is confirmed and the lead becomes Booked. Cancel: the
    matched appointment is cancelled. Reschedule: the matched one is marked rescheduled and a confirmed
    one is made for the asked day and time."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        r = await _pending(conn, user, request_id)
        data: dict[str, Any] = json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]
        kind = r["type"]
        if kind in ("callback", "question"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Mark a callback as done instead.")
        if kind in ("book", "online"):
            if r["a_id"]:
                await _set_appt(conn, r["a_id"], user, "confirmed")
            await conn.execute(
                """update app.leads set stage = 'booked', stage_reason = null, updated_at = now()
                   where id = $1 and stage in ('new', 'follow_up', 'lost')""",
                r["lead_id"],
            )
        elif kind == "cancel" and r["a_id"]:
            await _set_appt(conn, r["a_id"], user, "cancelled")
        elif kind == "reschedule":
            if not data.get("date"):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The new day is missing.")
            if r["a_id"]:
                await _set_appt(conn, r["a_id"], user, "rescheduled")
            await _new_slot(conn, r, data, user)
        await _close(conn, r, user, "done", {"outcome": "approved"})
        row = await conn.fetchrow(f"{SELECT} where r.id = $1", r["id"])
    return _item(row)


@router.post("/requests/{request_id}/reject", response_model=InboxItem)
async def reject(user: Annotated[Staff, Depends(staff)], request_id: str, body: Reject) -> InboxItem:
    """Not possible as asked (the reason goes on the lead's timeline). A booking's appointment is rejected."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        r = await _pending(conn, user, request_id)
        if r["type"] in ("book", "online") and r["a_id"]:
            await _set_appt(conn, r["a_id"], user, "rejected")
        await _close(conn, r, user, "rejected", {"text": body.reason.strip()})
        row = await conn.fetchrow(f"{SELECT} where r.id = $1", r["id"])
    return _item(row)


@router.post("/requests/{request_id}/done", response_model=InboxItem)
async def done(user: Annotated[Staff, Depends(staff)], request_id: str, body: Done) -> InboxItem:
    """A callback or question handled: the call is logged on the lead."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        r = await _pending(conn, user, request_id)
        if r["type"] not in ("callback", "question"):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Approve or reject this request instead."
            )
        lead = {"id": r["lead_id"], "clinic_id": r["clinic_id"]}
        await _event(conn, lead, user, "call", {"outcome": body.outcome, "text": body.note.strip()})
        await conn.execute("update app.leads set last_contact_at = now() where id = $1", r["lead_id"])
        await _close(conn, r, user, "done", {"outcome": body.outcome})
        row = await conn.fetchrow(f"{SELECT} where r.id = $1", r["id"])
    return _item(row)
