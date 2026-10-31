"""CRM → Doctors Availability, JSON only: every doctor's day today (cards) and one doctor's week (grid).

Read from the same tables the chatbot books from: weekly hours (in-clinic and online), leave, clinic closed
days and holidays, appointments, and the free times the chatbot would offer (app.chat.slots). Each doctor's
slot length is their own for the kind of visit, else the clinic's (Dashboard → Doctors).
"""

import json
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.v1 import crm_doctors, crm_inbox
from app.api.v1.crm import NewLead, add_lead, can_edit, can_see
from app.api.v1.crm_doctors import Schedule
from app.chat import slots
from app.chat.flows import EMAIL
from app.chat.leads import _free_doctors
from app.core.db import get_pool
from app.crm import permissions as perm
from app.crm import whatsapp
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


async def _doctor_id(conn: Any, user: Staff, clinic: str, doctor_id: str, need: str) -> str:
    """The doctor, checked: in this clinic, and a doctor changes only their own hours (the doctor record
    linked to their sign-in, in Team)."""
    try:
        UUID(doctor_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found in this clinic.") from None
    can_see(user, clinic)
    await perm.require(conn, user, clinic, "doctors", need)  # type: ignore[arg-type]
    linked = await conn.fetchrow(
        "select user_id::text from app.doctors where id = $1::uuid and clinic_id = $2", doctor_id, clinic
    )
    if linked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found in this clinic.")
    own = not user.bb_admin and user.roles.get(clinic) == "doctor"
    if need == "edit" and own and linked["user_id"] != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Doctors can change only their own hours and leave.")
    return doctor_id


async def _schedule(clinic: str, doctor_id: str, problems: list[str] | None = None) -> Schedule:
    d = next(x for x in (await crm_doctors._list(clinic)).doctors if x.id == doctor_id)
    return Schedule.model_construct(
        in_clinic=d.in_clinic, online=d.online, leave=d.leave, calcom=d.calcom, problems=problems or []
    )


@router.get("/availability/{doctor_id}/schedule", response_model=Schedule)
async def get_schedule(user: Annotated[Staff, Depends(staff)], clinic: CLINIC, doctor_id: str) -> Schedule:
    """A doctor's weekly in-clinic and online hours and upcoming leave."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _doctor_id(conn, user, clinic, doctor_id, "view")
    return await _schedule(clinic, doctor_id)


@router.put("/availability/{doctor_id}/schedule", response_model=Schedule)
async def save_schedule(
    user: Annotated[Staff, Depends(staff)], clinic: CLINIC, doctor_id: str, body: Schedule
) -> Schedule:
    """Saves a doctor's weekly hours and upcoming leave (all replaced by what was sent). A doctor connected
    to Cal.com gets them there too."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await _doctor_id(conn, user, clinic, doctor_id, "edit")
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        await crm_doctors._save(conn, clinic, doctor_id, body)
    return await _schedule(clinic, doctor_id, await crm_doctors._calcom(clinic, doctor_id))


class NewPatient(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(max_length=20)
    phone_cc: str = Field(default="+91", pattern=r"^\+[1-9][0-9]{0,3}$")


class BookIn(BaseModel):
    date: date
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    type: Literal["in_clinic", "online"]
    lead_code: str | None = Field(default=None, max_length=30)  # an existing lead, or
    patient: NewPatient | None = None  # a new one
    email: str | None = Field(default=None, max_length=200)  # online: for the Meet link (kept on the lead)
    treatment: str | None = Field(default=None, max_length=100)
    note: str = Field(default="", max_length=2000)


class Booked(BaseModel):
    lead_code: str
    appointment_id: str
    date: str  # the day, to open it in Appointments


@router.post("/availability/{doctor_id}/book", response_model=Booked)
async def book(
    user: Annotated[Staff, Depends(staff)], clinic: CLINIC, doctor_id: str, body: BookIn
) -> Booked:
    """Staff add a patient at a free time: a CONFIRMED appointment at once (no Inbox step). Online: the
    consult is booked in Cal.com now (Google Meet; Cal.com emails the link), so the patient's email is needed;
    Cal.com refusing saves nothing. The patient gets the clinic's "confirmed" WhatsApp, as on approval. Only
    a time the chatbot would offer can be booked."""
    can_edit(user, clinic)
    if (body.lead_code is None) == (body.patient is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a patient or add a new one.")
    email = (body.email or "").strip().lower() or None
    if email and not EMAIL.match(email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter a valid email.")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _doctor_id(conn, user, clinic, doctor_id, "view")
        await perm.require(conn, user, clinic, "appointments", "edit")  # Who sees what
        tz = ZoneInfo(await conn.fetchval("select timezone from app.clinics where id = $1", clinic))
        now = datetime.now(tz)
        free = await slots.free_slots_range(
            conn, clinic, body.date, body.date, body.type, now.date(), now.hour * 60 + now.minute, "",
            doctor_id,
        )  # fmt: skip
        known = None
        if body.lead_code:
            known = await conn.fetchval(
                "select email from app.leads where lead_code = $1 and clinic_id = $2 and deleted_at is null",
                body.lead_code, clinic,
            )  # fmt: skip
    if body.time not in free.get(body.date.isoformat(), []):
        raise HTTPException(status.HTTP_409_CONFLICT, "That time is not free any more. Choose another.")
    if body.type == "online" and not (email or known):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter the patient's email: the Meet link is sent there."
        )
    if body.patient:  # a new lead, as Add lead makes it (a known phone is refused with its lead code)
        made = await add_lead(
            user,
            NewLead(clinic=clinic, name=body.patient.name, phone=body.patient.phone,
                    phone_cc=body.patient.phone_cc, email=email, treatment=body.treatment,
                    doctor_id=doctor_id, type=body.type, note=body.note),
        )  # fmt: skip
        code = made.code
    else:
        code = str(body.lead_code)
    start = datetime.combine(body.date, time.fromisoformat(body.time), tz)
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        lead = await conn.fetchrow(
            """select id, clinic_id, full_name, phone_e164, email from app.leads
               where lead_code = $1 and clinic_id = $2 and deleted_at is null""",
            code, clinic,
        )  # fmt: skip
        if lead is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found in this clinic.")
        if email and email != lead["email"]:
            await conn.execute("update app.leads set email = $2 where id = $1", lead["id"], email)
        clinic_row = await conn.fetchrow("select id, timezone from app.clinics where id = $1", clinic)
        found = await _free_doctors(conn, clinic_row, body.type, start, "s_crm", doctor_id)
        if not found:
            raise HTTPException(status.HTTP_409_CONFLICT, "That time is not free any more. Choose another.")
        try:
            appt = await conn.fetchval(
                """insert into app.appointments (clinic_id, lead_id, doctor_id, type, slot, status,
                     confirmed_by, confirmed_at)
                   values ($1, $2, $3::uuid, $4, tstzrange($5, $6, '[)'), 'confirmed', $7::uuid, now())
                   returning id""",
                clinic, lead["id"], doctor_id, body.type, start, found[0][1], user.id,
            )  # fmt: skip
        except asyncpg.exceptions.ExclusionViolationError:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "That time was just booked. Choose another."
            ) from None
        if body.type == "online":  # Cal.com now; refusing undoes everything above
            rec: Any = {
                "a_start": start, "a_id": appt, "a_doctor_id": UUID(doctor_id), "clinic_id": clinic,
                "full_name": lead["full_name"], "email": email or lead["email"],
                "phone_e164": lead["phone_e164"], "lead_code": code,
            }  # fmt: skip
            await crm_inbox._online(conn, rec, {"treatment": body.treatment})
        await conn.execute(
            """update app.leads set stage = 'booked', stage_reason = null, updated_at = now()
               where id = $1 and stage in ('new', 'follow_up', 'lost')""",
            lead["id"],
        )
        await conn.execute(
            "insert into app.lead_events (clinic_id, lead_id, kind, data, actor) "
            "values ($1, $2, 'appointment', $3::jsonb, $4::uuid)",
            clinic, lead["id"],
            json.dumps({"appointment_id": str(appt), "status": "confirmed", "by": "staff"}), user.id,
        )  # fmt: skip
        meet = await conn.fetchval("select meet_link from app.appointments where id = $1", appt)
        name = await conn.fetchval("select name from app.doctors where id = $1::uuid", doctor_id)
    purpose = "online_confirmed" if body.type == "online" else "inclinic_confirmed"
    whatsapp.notify(clinic, purpose, lead["phone_e164"], {
        "lead_code": code, "name": lead["full_name"], "doctor": name, "treatment": body.treatment,
        "date": start.strftime("%a %d %b"), "time": start.strftime("%I:%M %p"), "meet_link": meet,
    })  # fmt: skip
    return Booked(lead_code=code, appointment_id=str(appt), date=body.date.isoformat())
