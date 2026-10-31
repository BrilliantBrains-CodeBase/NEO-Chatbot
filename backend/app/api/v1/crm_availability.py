"""CRM → Doctors Availability, JSON only: every doctor's day today (cards) and one doctor's week (grid).

Read from the same tables the chatbot books from: weekly hours (in-clinic and online), leave, clinic closed
days and holidays, appointments, and the free times the chatbot would offer (app.chat.slots). Each doctor's
slot length is their own for the kind of visit, else the clinic's (Dashboard → Doctors).
"""

from datetime import date, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.v1.crm import can_see
from app.chat import slots
from app.core.db import get_pool
from app.crm import permissions as perm
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm", tags=["crm"])

CLINIC = Annotated[str, Query(pattern=r"^CL\d{2,3}$")]


class Span(BaseModel):
    start: str  # HH:MM, clinic time
    end: str


class Booking(BaseModel):
    id: str
    start: str | None  # HH:MM; None when the patient chose "Any time"
    end: str | None
    type: str  # in_clinic | online
    status: str  # pending | confirmed | visited | no_show | missed
    patient: str
    lead_code: str


class Day(BaseModel):
    date: str
    closed: bool  # the clinic is closed (weekday or holiday): no in-clinic visits
    holiday: str | None  # its reason, on a clinic holiday (no visits at all)
    leave: str | None  # the doctor's leave reason ("" when none given); None when not on leave
    in_clinic: list[Span]  # the doctor's hours that day
    online: list[Span]
    free_in_clinic: list[str]  # free starts, as the chatbot offers them (past times left out)
    free_online: list[str]
    bookings: list[Booking]


class Doctor(BaseModel):
    id: str
    name: str
    role_title: str
    in_clinic_minutes: int  # their own length, else the clinic's
    online_minutes: int


class Card(BaseModel):
    doctor: Doctor
    today: Day


class Board(BaseModel):
    today: str
    open_time: str  # the clinic's hours, for the grid's rows
    close_time: str
    doctors: list[Card]


class Week(BaseModel):
    doctor: Doctor
    today: str
    open_time: str
    close_time: str
    days: list[Day]


async def _check(user: Staff, clinic: str) -> None:
    can_see(user, clinic)
    await perm.require(await get_pool(), user, clinic, "doctors", "view")  # Who sees what


async def _doctors(conn: Any, clinic: str, doctor_id: str | None = None) -> list[Doctor]:
    rows = await conn.fetch(
        """select d.id, d.name, d.role_title,
                  coalesce(d.in_clinic_minutes, c.slot_minutes) ic,
                  coalesce(d.online_minutes, c.online_slot_minutes) onl
           from app.doctors d join app.clinics c on c.id = d.clinic_id
           where d.clinic_id = $1 and d.active and ($2::uuid is null or d.id = $2::uuid)
           order by d.sort_order, d.name""",
        clinic, doctor_id,
    )  # fmt: skip
    return [
        Doctor(id=str(r["id"]), name=r["name"], role_title=r["role_title"],
               in_clinic_minutes=r["ic"], online_minutes=r["onl"])
        for r in rows
    ]  # fmt: skip


async def _days(conn: Any, clinic: str, doc: Doctor, first: date, last: date) -> list[Day]:
    """The doctor's days from first to last (clinic time)."""
    c = await conn.fetchrow("select timezone, closed_weekdays from app.clinics where id = $1", clinic)
    tz = ZoneInfo(c["timezone"])
    now = datetime.now(tz)
    hours = await conn.fetch(
        """select weekday, mode, to_char(start_time, 'HH24:MI') s, to_char(end_time, 'HH24:MI') e
           from app.doctor_availability where doctor_id = $1::uuid order by start_time""",
        doc.id,
    )
    leave = await conn.fetch(
        "select from_date, to_date, reason from app.doctor_leave where doctor_id = $1::uuid "
        "and to_date >= $2 and from_date <= $3",
        doc.id, first, last,
    )  # fmt: skip
    rows = await conn.fetch(
        "select day, reason from app.clinic_holidays where clinic_id = $1 and day between $2 and $3",
        clinic, first, last,
    )  # fmt: skip
    holidays = {r["day"]: r["reason"] for r in rows}
    appts = await conn.fetch(
        """select a.id, a.type, a.status, l.full_name, l.lead_code,
                  coalesce((lower(a.slot) at time zone c.timezone)::date, a.preferred_date) as day,
                  to_char(lower(a.slot) at time zone c.timezone, 'HH24:MI') s,
                  to_char(upper(a.slot) at time zone c.timezone, 'HH24:MI') e
           from app.appointments a join app.leads l on l.id = a.lead_id
           join app.clinics c on c.id = a.clinic_id
           where a.doctor_id = $1::uuid and l.deleted_at is null
             and a.status in ('pending', 'confirmed', 'visited', 'no_show', 'missed')
             and coalesce((lower(a.slot) at time zone c.timezone)::date, a.preferred_date) between $2 and $3
           order by lower(a.slot) nulls last""",
        doc.id, first, last,
    )  # fmt: skip
    minutes = now.hour * 60 + now.minute
    free = {
        mode: await slots.free_slots_range(conn, clinic, first, last, mode, now.date(), minutes, "", doc.id)
        for mode in ("in_clinic", "online")
    }
    out = []
    day = first
    while day <= last:
        dow = (day.weekday() + 1) % 7  # 0 = Sunday
        off = next((x for x in leave if x["from_date"] <= day <= x["to_date"]), None)
        out.append(
            Day(
                date=day.isoformat(),
                closed=dow in c["closed_weekdays"] or day in holidays,
                holiday=holidays.get(day),
                leave=off["reason"] if off else None,
                in_clinic=[Span(start=h["s"], end=h["e"]) for h in hours
                           if h["weekday"] == dow and h["mode"] == "in_clinic"],
                online=[Span(start=h["s"], end=h["e"]) for h in hours
                        if h["weekday"] == dow and h["mode"] == "online"],
                free_in_clinic=free["in_clinic"].get(day.isoformat(), []),
                free_online=free["online"].get(day.isoformat(), []),
                bookings=[Booking(id=str(a["id"]), start=a["s"], end=a["e"], type=a["type"],
                                  status=a["status"], patient=a["full_name"], lead_code=a["lead_code"])
                          for a in appts if a["day"] == day],
            )
        )  # fmt: skip
        day += timedelta(days=1)
    return out


async def _hours(conn: Any, clinic: str) -> tuple[str, str]:
    r = await conn.fetchrow(
        "select to_char(open_time, 'HH24:MI') o, to_char(close_time, 'HH24:MI') c "
        "from app.clinics where id = $1",
        clinic,
    )
    return r["o"], r["c"]


@router.get("/availability/doctors", response_model=list[Doctor])
async def doctors(user: Annotated[Staff, Depends(staff)], clinic: CLINIC) -> list[Doctor]:
    """The clinic's active doctors (the sidebar's list)."""
    await _check(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await _doctors(conn, clinic)


@router.get("/availability", response_model=Board)
async def board(user: Annotated[Staff, Depends(staff)], clinic: CLINIC) -> Board:
    """Every active doctor's day today: hours, leave, bookings and free times."""
    await _check(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn:
        tz = await conn.fetchval("select timezone from app.clinics where id = $1", clinic)
        today = datetime.now(ZoneInfo(tz)).date()
        open_time, close_time = await _hours(conn, clinic)
        cards = [Card(doctor=d, today=(await _days(conn, clinic, d, today, today))[0])
                 for d in await _doctors(conn, clinic)]  # fmt: skip
    return Board(today=today.isoformat(), open_time=open_time, close_time=close_time, doctors=cards)


@router.get("/availability/{doctor_id}", response_model=Week)
async def week(
    user: Annotated[Staff, Depends(staff)],
    clinic: CLINIC,
    doctor_id: str,
    start: date | None = None,
) -> Week:
    """One doctor's week: 7 days from `start` (default today)."""
    await _check(user, clinic)
    try:
        UUID(doctor_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found in this clinic.") from None
    pool = await get_pool()
    async with pool.acquire() as conn:
        found = await _doctors(conn, clinic, doctor_id)
        if not found:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found in this clinic.")
        tz = await conn.fetchval("select timezone from app.clinics where id = $1", clinic)
        today = datetime.now(ZoneInfo(tz)).date()
        first = start or today
        open_time, close_time = await _hours(conn, clinic)
        days = await _days(conn, clinic, found[0], first, first + timedelta(days=6))
    return Week(
        doctor=found[0], today=today.isoformat(), open_time=open_time, close_time=close_time, days=days
    )
