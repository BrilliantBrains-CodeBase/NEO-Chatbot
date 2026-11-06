"""CRM Inbox (JSON only). The Inbox is the intake queue: new leads from every source wait there, unassigned,
until the clinic manager or a front desk member assigns them. Their requests (bookings, cancellations, call
backs...) are then handled by the lead's owner from the Lead drawer, with the routes below."""

import json
from collections.abc import Awaitable
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.api.v1.crm import (
    LEAD_SELECT,
    SOURCE_FILTER,
    Count,
    LeadRow,
    Option,
    _event,
    _lead_filter,
    bulk_access,
    can_edit,
    can_see,
    cell,
    csv_file,
    export_phone,
    in_clinic,
    lead_row,
    own_doctor,
    plain_text,
)
from app.chat import slots
from app.chat.leads import _free_doctors as free_doctors
from app.chat.leads import slot_length
from app.core.db import get_pool
from app.crm import calcom, vault, webhooks, whatsapp
from app.crm import permissions as perm
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm", tags=["crm"])

TYPES = ["book", "online", "cancel", "reschedule", "callback", "question"]


class Appt(BaseModel):
    id: str
    start: str | None  # ISO time; None when the patient chose "Any time"
    day: str | None  # the clinic-local day
    doctor: str | None
    doctor_id: str | None = None
    type: str
    status: str
    meet_link: str | None = None  # online consults, from Cal.com when approved


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
    urgent: bool = False  # an emergency in the chat


class InboxRequest(BaseModel):
    """A request waiting on an Inbox lead, as a summary: the owner handles it after assigning."""

    id: str
    type: str
    created_at: str
    treatment: str | None
    reason: str | None
    date: str | None
    time: str | None
    booked_date: str | None
    urgent: bool = False


class InboxLead(LeadRow):
    requests: list[InboxRequest]  # waiting, newest first


class Inbox(BaseModel):
    total: int  # unassigned leads matching the filters, across all pages
    all: int = 0  # the same without the type filter: the "All" chip, the menu and the Dashboard
    types: list[Count]  # leads per waiting request type, and "none" (a lead with no request, e.g. a form)
    items: list[InboxLead]
    treatments: list[str] = []  # every treatment these leads have, for the filter


SELECT = """select r.id, r.type, r.status, r.created_at, r.data, r.match_status, r.clinic_id, r.lead_id,
    l.lead_code, l.full_name, l.phone_e164, l.phone_cc, l.email, a.id a_id, lower(a.slot) a_start,
    to_char(lower(a.slot) at time zone c.timezone, 'HH24:MI') a_time,
    to_char(r.created_at at time zone c.timezone, 'YYYY-MM-DD HH24:MI') received,
    coalesce((lower(a.slot) at time zone c.timezone)::date, a.preferred_date) a_day, d.name a_doctor,
    a.type a_type, a.status a_status, a.doctor_id a_doctor_id, a.meet_link a_meet,
    a.calendar_event_id a_cal
  from app.requests r join app.leads l on l.id = r.lead_id join app.clinics c on c.id = r.clinic_id
  left join app.appointments a on a.id = coalesce(
    (select id from app.appointments where request_id = r.id order by created_at desc limit 1),
    r.matched_appointment_id)
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
            doctor_id=str(r["a_doctor_id"]) if r["a_doctor_id"] else None,
            type=r["a_type"],
            status=r["a_status"],
            meet_link=r["a_meet"],
        )
    # One lead per phone: a request under a different name (e.g. family sharing a phone) shows who asked.
    typed = str(data.get("name") or "").strip()
    same = not typed or " ".join(typed.lower().split()) == " ".join(str(r["full_name"]).lower().split())
    name = r["full_name"] if same else f"{typed} · existing lead {r['full_name']} (same phone)"
    return InboxItem(
        id=str(r["id"]), type=r["type"], status=r["status"], created_at=r["created_at"].isoformat(),
        lead_code=r["lead_code"], name=name, phone=r["phone_e164"], email=r["email"],
        treatment=data.get("treatment"), reason=data.get("reason"), date=data.get("date"),
        time=data.get("time"), booked_date=data.get("booked_date"), match_status=r["match_status"],
        appointment=appt, urgent=bool(data.get("urgent")),
    )  # fmt: skip


# The day a request is about: the day asked for, the booked day (a cancellation), else the day it came in.
REQUEST_DAY = """coalesce(nullif(r.data->>'date', ''), nullif(r.data->>'booked_date', ''),
    to_char(r.created_at at time zone c.timezone, 'YYYY-MM-DD'))"""


def _inbox_filter(
    clinic: str,
    type_: str | None,
    done: bool,
    q: str,
    date_from: date | None,
    date_to: date | None,
    treatment: str | None,
    source: str | None = None,
) -> tuple[str, list[Any]]:
    """The Inbox filters, shared by the list and the export. `q` matches the patient's name (the lead's or the
    one typed in this request), phone (spaces and dashes ignored), treatment, email or lead code."""
    where = f"""r.clinic_id = $1 and ($2::text is null or r.type = $2)
        and {"r.status <> 'pending'" if done else "r.status = 'pending'"}
        and ($3 = '' or l.full_name ilike '%'||$3||'%' or r.data->>'name' ilike '%'||$3||'%'
          or l.phone_e164 like '%'||nullif(regexp_replace($3, '[\\s-]', '', 'g'), '')||'%'
          or r.data->>'treatment' ilike '%'||$3||'%' or l.email ilike '%'||$3||'%' or l.lead_code ilike $3)
        and ($4::text is null or {REQUEST_DAY} >= $4) and ($5::text is null or {REQUEST_DAY} <= $5)
        and ($6::text is null or r.data->>'treatment' = $6)
        and ($7::text is null or l.source = $7)"""
    days = [d.isoformat() if d else None for d in (date_from, date_to)]
    return where, [clinic, type_, plain_text(q), *days, treatment, source]


# The newest request first, pending and handled alike; those of one moment keep a fixed order across pages.
REQUEST_ORDER = "order by r.created_at desc, r.id desc"
RequestType = Literal["book", "online", "cancel", "reschedule", "callback", "question"]
REQUEST_LABEL = {
    "book": "Booking request", "online": "Online consult", "cancel": "Cancellation",
    "reschedule": "Reschedule", "callback": "Callback", "question": "Question",
}  # fmt: skip
EXPORT_COLUMNS = ["Code", "Name", "Phone", "Email", "Type", "Treatment", "Asked date", "Asked time",
                  "Booked date", "Reason", "Appointment date", "Appointment time", "Doctor",
                  "Appointment type",
                  "Appointment status", "Status", "Received"]  # fmt: skip


@router.get("/inbox/export")
async def export_inbox(
    user: Annotated[Staff, Depends(staff)],
    clinic: Annotated[str, Query(pattern=r"^CL\d{2,3}$")],
    type: Annotated[RequestType | None, Query()] = None,
    done: bool = False,
    q: Annotated[str, Query(max_length=100)] = "",
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    treatment: Annotated[str | None, Query(max_length=200)] = None,
    source: Annotated[str | None, Query(pattern=SOURCE_FILTER)] = None,
) -> Response:
    """Every request matching the Inbox filters (all pages), as a CSV for Excel."""
    bulk_access(user, clinic)
    await perm.require(await get_pool(), user, clinic, "inbox", "view")  # Who sees what
    where, args = _inbox_filter(clinic, type, done, q, date_from, date_to, treatment, source)
    rows = await (await get_pool()).fetch(f"{SELECT} where {where} {REQUEST_ORDER}", *args)
    return _inbox_csv(clinic, rows)


class ExportPicked(BaseModel):
    clinic: str = Field(pattern=r"^CL\d{2,3}$")
    ids: list[UUID] = Field(min_length=1, max_length=5000)


@router.post("/inbox/export")
async def export_picked_requests(user: Annotated[Staff, Depends(staff)], body: ExportPicked) -> Response:
    """The requests ticked on the Inbox screen, as a CSV (a request of another clinic is never included)."""
    bulk_access(user, body.clinic)
    await perm.require(await get_pool(), user, body.clinic, "inbox", "view")  # Who sees what
    rows = await (await get_pool()).fetch(
        f"{SELECT} where r.clinic_id = $1 and r.id = any($2::uuid[]) {REQUEST_ORDER}", body.clinic, body.ids
    )
    return _inbox_csv(body.clinic, rows)


def _inbox_csv(clinic: str, rows: list[asyncpg.Record]) -> Response:
    out: list[list[object]] = []
    for r in rows:
        i = _item(r)
        a = i.appointment
        out.append([
            i.lead_code, cell(i.name), export_phone(r["phone_e164"], r["phone_cc"]), cell(i.email),
            REQUEST_LABEL.get(i.type, i.type), cell(i.treatment), cell(i.date),
            "Any time" if i.time == "any" else cell(i.time), cell(i.booked_date), cell(i.reason),
            a.day if a else "", r["a_time"] or "", cell(a.doctor) if a else "",
            {"online": "Online", "in_clinic": "In-clinic"}.get(a.type, a.type) if a else "",
            a.status if a else "", i.status, r["received"],
        ])  # fmt: skip
    return csv_file(f"inbox-{clinic}", EXPORT_COLUMNS, out)


InboxType = Literal["book", "online", "cancel", "reschedule", "callback", "question", "none"]
# In the Inbox: no owner yet, and not closed as Lost or Invalid.
INBOX_WHERE = " and l.stage not in ('lost', 'invalid')"
WAITING = "select 1 from app.requests rq where rq.lead_id = l.id and rq.status = 'pending'"


@router.get("/inbox", response_model=Inbox)
async def inbox(
    user: Annotated[Staff, Depends(staff)],
    clinic: Annotated[str, Query(pattern=r"^CL\d{2,3}$")],
    type: Annotated[InboxType | None, Query()] = None,
    q: Annotated[str, Query(max_length=100)] = "",
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    treatment: Annotated[str | None, Query(max_length=200)] = None,
    source: Annotated[str | None, Query(pattern=SOURCE_FILTER)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Inbox:
    """New leads waiting for an owner, latest contact first, each with its waiting requests. `type` keeps
    leads with a request of that type waiting ("none": with no request, e.g. a website form). `from` and `to`
    (days, both included) keep leads created then. The counts per type follow the other filters."""
    can_see(user, clinic)
    await perm.require(await get_pool(), user, clinic, "inbox", "view")  # Who sees what
    base, args = _lead_filter(clinic, source, q, date_from, date_to, treatment, "unassigned")
    base += INBOX_WHERE
    where = base
    if type == "none":
        where += f" and not exists ({WAITING})"
    elif type:  # from the fixed list above, validated by FastAPI
        where += f" and exists ({WAITING} and rq.type = '{type}')"
    pool = await get_pool()
    async with pool.acquire() as conn:
        counts = {
            r[0]: r[1]
            for r in await conn.fetch(
                f"""select rq.type, count(distinct l.id) from app.leads l
                    join app.requests rq on rq.lead_id = l.id and rq.status = 'pending'
                    where {base} group by 1""",
                *args,
            )
        }
        every, waiting = await conn.fetchrow(
            f"""select count(*), count(*) filter (where exists ({WAITING}))
                from app.leads l where {base}""",
            *args,
        )
        total = await conn.fetchval(f"select count(*) from app.leads l where {where}", *args)
        rows = await conn.fetch(
            f"""{LEAD_SELECT.replace("l.created_at", "l.created_at, l.id")} where {where}
                order by l.last_contact_at desc, l.lead_code desc limit $7 offset $8""",
            *args, limit, offset,
        )  # fmt: skip
        asks = await conn.fetch(
            """select id, lead_id, type, created_at, data from app.requests
               where lead_id = any($1::uuid[]) and status = 'pending' order by created_at desc""",
            [r["id"] for r in rows],
        )
        treatments = await conn.fetch(
            f"""select distinct l.treatment from app.leads l where {base} and l.treatment is not null
                order by 1""",
            *args,
        )
    by_lead: dict[Any, list[InboxRequest]] = {}
    for a in asks:
        data: dict[str, Any] = json.loads(a["data"]) if isinstance(a["data"], str) else a["data"]
        by_lead.setdefault(a["lead_id"], []).append(
            InboxRequest(
                id=str(a["id"]),
                type=a["type"],
                created_at=a["created_at"].isoformat(),
                treatment=data.get("treatment"),
                reason=data.get("reason"),
                date=data.get("date"),
                time=data.get("time"),
                booked_date=data.get("booked_date"),
                urgent=bool(data.get("urgent")),
            )  # fmt: skip
        )
    return Inbox(
        total=total,
        all=every,
        types=[Count(key=t, count=counts.get(t, 0)) for t in TYPES]
        + [Count(key="none", count=every - waiting)],
        items=[InboxLead.model_validate(lead_row(r) | {"requests": by_lead.get(r["id"], [])}) for r in rows],
        treatments=[r[0] for r in treatments],
    )


class AssignIn(BaseModel):
    clinic: str = Field(pattern=r"^CL\d{2,3}$")
    codes: list[str] = Field(min_length=1, max_length=500)
    to: UUID | None = None  # left out: me


class Assigned(BaseModel):
    assigned: list[str]  # lead codes now owned by `to`
    taken: list[str]  # assigned by someone else meanwhile (or not in the Inbox): left as they are
    to: str  # the owner's name


@router.post("/inbox/assign", response_model=Assigned)
async def assign_from_inbox(user: Annotated[Staff, Depends(staff)], body: AssignIn) -> Assigned:
    """Give Inbox leads an owner, moving them to Leads. Front Desk takes leads for themselves; an Admin (or
    Super Admin) assigns to anyone who can take leads. Only leads still unassigned change, so two people
    taking the same lead at once never take it from each other. The leads' open tasks follow the new owner."""
    can_edit(user, body.clinic)
    await perm.require(await get_pool(), user, body.clinic, "inbox", "edit")  # Who sees what
    to = str(body.to or user.id)
    if to != user.id and not (user.bb_admin or user.roles.get(body.clinic) == "clinic_manager"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can assign leads to yourself only.")
    codes = list(dict.fromkeys(body.codes))
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        # Who did it, for the audit (and the "assigned to you" notification skips taking it yourself).
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        name = await conn.fetchval(
            """select p.full_name from app.user_clinics u join app.profiles p on p.id = u.user_id
               where u.user_id = $1::uuid and u.clinic_id = $2 and u.active and p.active
                 and u.role <> 'doctor'""",
            to, body.clinic,
        )  # fmt: skip
        if name is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That person cannot take leads here.")
        done = await conn.fetch(
            """update app.leads set assigned_to = $3::uuid, updated_at = now()
               where clinic_id = $1 and lead_code = any($2::text[]) and assigned_to is null
                 and deleted_at is null
               returning id, clinic_id, lead_code""",
            body.clinic, codes, to,
        )  # fmt: skip
        for lead in done:
            await _event(conn, lead, user, "assigned", {"to": name, "from": "inbox"})
        if done:
            await conn.execute(
                """update app.tasks set assigned_to = $2::uuid, updated_at = now()
                   where lead_id = any($1::uuid[]) and status = 'open'""",
                [r["id"] for r in done], to,
            )  # fmt: skip
    got = {r["lead_code"] for r in done}
    return Assigned(
        assigned=[c for c in codes if c in got], taken=[c for c in codes if c not in got], to=name
    )


@router.get("/leads/{code}/requests", response_model=list[InboxItem])
async def lead_requests(user: Annotated[Staff, Depends(staff)], code: str) -> list[InboxItem]:
    """A lead's requests waiting for its owner, oldest first: the Lead drawer's "Pending requests"."""
    pool = await get_pool()
    clinic = await pool.fetchval(
        "select clinic_id from app.leads where lead_code = $1 and deleted_at is null", code
    )
    if clinic is None or not in_clinic(user, clinic):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found.")
    await perm.require(pool, user, clinic, "leads", "view")  # Who sees what
    rows = await pool.fetch(
        f"{SELECT} where l.lead_code = $1 and l.deleted_at is null and r.status = 'pending' "
        "order by r.created_at, r.id",
        code,
    )
    return [_item(r) for r in rows]


@router.get("/requests/{request_id}", response_model=InboxItem)
async def one_request(user: Annotated[Staff, Depends(staff)], request_id: UUID) -> InboxItem:
    """One request, for opening it from a notification or the calendar when it is not on the page shown."""
    r = await (await get_pool()).fetchrow(f"{SELECT} where r.id = $1", request_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found.")
    can_see(user, r["clinic_id"])
    await perm.require(await get_pool(), user, r["clinic_id"], "inbox", "view")  # Who sees what
    return _item(r)


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
    await perm.require(await get_pool(), user, r["clinic_id"], "inbox", "edit")  # Who sees what
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


async def _new_slot(
    conn: asyncpg.Connection, r: asyncpg.Record, data: dict[str, Any], user: Staff
) -> tuple[Any, datetime | None]:
    """The appointment a reschedule moves to: same doctor and type, the asked day and time."""
    tz = await conn.fetchval("select timezone from app.clinics where id = $1", r["clinic_id"])
    day = date.fromisoformat(data["date"])
    if data.get("time") in (None, "any"):
        start, end = None, None
    else:
        start = datetime.combine(day, time.fromisoformat(data["time"]), ZoneInfo(tz))
        # The doctor's own length for this kind of visit, else the clinic's.
        end = start + await slot_length(conn, r["clinic_id"], r["a_doctor_id"], r["a_type"] or "in_clinic")
    try:
        async with conn.transaction():
            new = await conn.fetchval(
                """insert into app.appointments (clinic_id, lead_id, request_id, doctor_id, type, slot,
                     preferred_date, status, rescheduled_from_id, confirmed_by, confirmed_at)
                   values ($1, $2, $3, $4, $5, case when $6::timestamptz is null then null
                     else tstzrange($6, $7, '[)') end, $8, 'confirmed', $9, $10::uuid, now()) returning id""",
                r["clinic_id"], r["lead_id"], r["id"], r["a_doctor_id"], r["a_type"] or "in_clinic",
                start, end, None if start else day, r["a_id"], user.id,
            )  # fmt: skip
            return new, start
    except asyncpg.exceptions.ExclusionViolationError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The doctor is already booked at that time. Call the patient for another.",
        ) from None


class Approve(BaseModel):
    """Changes agreed with the patient on the phone, applied before approving (all optional)."""

    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")  # also for "Any time"
    treatment: str | None = Field(default=None, min_length=2, max_length=100)
    doctor_id: str | None = None  # the doctor whose free times staff picked from
    note: str = Field(default="", max_length=2000)  # what the patient said, for the team (lead timeline)


class Slots(BaseModel):
    doctors: list[Option]  # doctors who work in this mode
    days: dict[str, list[str]]  # YYYY-MM-DD -> free HH:MM starts of the chosen doctor


@router.get("/slots", response_model=Slots)
async def free_times(
    user: Annotated[Staff, Depends(staff)],
    clinic: Annotated[str, Query(pattern=r"^CL\d{2,3}$")],
    mode: Literal["in_clinic", "online"],
    doctor_id: str | None = None,
    days: Annotated[int, Query(ge=1, le=60)] = 14,
) -> Slots:
    """Free times for moving a booking: one doctor's (or any doctor's), from today. A time booked in-clinic
    or online is taken for both."""
    can_see(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn:
        doctors = await conn.fetch(
            """select distinct d.id, d.name, d.sort_order from app.doctors d
               join app.doctor_availability a on a.doctor_id = d.id and a.mode = $2
               where d.clinic_id = $1 and d.active order by d.sort_order, d.name""",
            clinic, mode,
        )  # fmt: skip
        if doctor_id and doctor_id not in {str(d["id"]) for d in doctors}:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "That doctor does not work in this mode."
            )
        tz = await conn.fetchval("select timezone from app.clinics where id = $1", clinic)
        now = datetime.now(ZoneInfo(tz))
        free = await slots.free_slots_range(
            conn, clinic, now.date(), now.date() + timedelta(days=days - 1), mode, now.date(),
            now.hour * 60 + now.minute, doctor_id=doctor_id,
        )  # fmt: skip
    return Slots(doctors=[Option(id=str(d["id"]), name=d["name"]) for d in doctors], days=free)


async def _move(
    conn: asyncpg.Connection, r: asyncpg.Record, day_s: str | None, time_s: str | None, doctor_id: str | None
) -> None:
    """Moves a booking's appointment to the day and time agreed with the patient. The doctor must work then
    and be free (in-clinic and online share one diary); the current doctor is kept when free."""
    c = await conn.fetchrow("select id, timezone from app.clinics where id = $1", r["clinic_id"])
    day = date.fromisoformat(day_s) if day_s else r["a_day"]
    if not time_s:  # a new day, still any time
        await conn.execute(
            "update app.appointments set slot = null, preferred_date = $2 where id = $1", r["a_id"], day
        )
        return
    first = datetime.combine(day, time.fromisoformat(time_s), ZoneInfo(c["timezone"]))
    if first <= datetime.now(first.tzinfo):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That time has already passed.")
    await conn.execute(  # free its own time while choosing (the day keeps the row valid)
        "update app.appointments set slot = null, preferred_date = $2 where id = $1", r["a_id"], day
    )
    # Each free doctor with the end of their own slot (their length for this kind of visit).
    free = dict(await free_doctors(conn, c, r["a_type"], first, "s_crm"))
    if not free:
        raise HTTPException(status.HTTP_409_CONFLICT, "No doctor is free at that time. Choose another time.")
    if doctor_id:  # the doctor staff picked must be one of the free ones
        doctor = next((d for d in free if str(d) == doctor_id), None)
        if doctor is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "That doctor is not free then. Choose another time."
            )
    else:
        doctor = r["a_doctor_id"] if r["a_doctor_id"] in free else next(iter(free))
    last = free[doctor]
    await conn.execute(
        """update app.appointments set slot = tstzrange($2, $3, '[)'), preferred_date = null, doctor_id = $4
           where id = $1""",
        r["a_id"], first, last, doctor,
    )  # fmt: skip


async def _online(conn: asyncpg.Connection, r: asyncpg.Record, data: dict[str, Any]) -> None:
    """Books the consult in Cal.com (Google Meet) and keeps the link on the appointment. A request for
    "Any time" needs the time staff agreed with the patient. Cal.com refusing undoes the approval."""
    start: datetime | None = r["a_start"]
    if start is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The patient chose Any time: enter the agreed time first."
        )
    acc = await account(conn, r["clinic_id"], r["a_doctor_id"])
    if acc.key and not acc.event:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "This doctor has no online consults in Cal.com yet (Dashboard → Integrations → Cal.com).",
        )
    try:
        booked = await calcom.book(
            start, r["full_name"], r["email"], r["phone_e164"],
            {"lead": r["lead_code"], "treatment": data.get("treatment") or ""}, acc,
        )  # fmt: skip
    except calcom.CalcomError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None
    await conn.execute(
        "update app.appointments set meet_link = $2, calendar_event_id = $3 where id = $1",
        r["a_id"], booked.meet_link, booked.uid,
    )  # fmt: skip


async def account(conn: asyncpg.Connection, clinic: str, doctor: Any) -> calcom.Account:
    """The clinic's own Cal.com (key from Vault, that doctor's event), else the backend's (.env)."""
    row = await conn.fetchrow(
        """select a.key_secret, d.event_type_id from app.calcom_accounts a
             left join app.calcom_doctors d on d.clinic_id = a.clinic_id and d.doctor_id = $2
           where a.clinic_id = $1""",
        clinic, doctor,
    )  # fmt: skip
    if row is None:
        return calcom.Account()
    return calcom.Account(key=await vault.read(conn, row["key_secret"]), event=row["event_type_id"])


async def _calcom[T](call: Awaitable[T]) -> T:
    """A Cal.com call inside an approval: when Cal.com refuses, the whole approval is undone."""
    try:
        return await call
    except calcom.CalcomError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None


@router.post("/requests/{request_id}/approve", response_model=InboxItem)
async def approve(
    user: Annotated[Staff, Depends(staff)], request_id: str, body: Approve | None = None
) -> InboxItem:
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
        if kind == "online" and not r["email"]:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "This patient has no email for the Meet link. Add it first.",
            )
        change = body or Approve()
        if change.note.strip():
            lead = {"id": r["lead_id"], "clinic_id": r["clinic_id"]}
            await _event(conn, lead, user, "note", {"text": change.note.strip()})
        if change.treatment and kind in ("book", "online", "reschedule"):
            data["treatment"] = change.treatment.strip()
            await conn.execute(
                "update app.leads set treatment = $2 where id = $1", r["lead_id"], data["treatment"]
            )
            await conn.execute(
                "update app.requests set data = data || $2::jsonb where id = $1",
                r["id"], json.dumps({"treatment": data["treatment"]}),
            )  # fmt: skip
        if kind in ("book", "online") and r["a_id"] and (change.date or change.time):
            await _move(conn, r, change.date, change.time, change.doctor_id)
            r = await conn.fetchrow(f"{SELECT} where r.id = $1", r["id"])
        if kind == "reschedule" and (change.date or change.time):
            data["date"] = change.date or data.get("date")
            data["time"] = change.time or data.get("time") or "any"
        if kind in ("book", "online"):
            if r["a_id"]:
                await _set_appt(conn, r["a_id"], user, "confirmed")
                webhooks.emit(r["clinic_id"], "appointment_confirmed", {
                    "lead_code": r["lead_code"], "name": r["full_name"], "phone": r["phone_e164"],
                    "type": kind, "date": data.get("date"), "time": data.get("time"), "doctor": r["a_doctor"],
                })  # fmt: skip
            if kind == "online" and r["a_id"]:
                await _online(conn, r, data)
            if r["a_id"]:
                appt = await conn.fetchrow(
                    """select to_char(lower(a.slot) at time zone c.timezone, 'Dy DD Mon') d,
                         to_char(lower(a.slot) at time zone c.timezone, 'HH12:MI AM') t, a.meet_link
                       from app.appointments a join app.clinics c on c.id = a.clinic_id where a.id = $1""",
                    r["a_id"],
                )  # fmt: skip
                whatsapp.notify(r["clinic_id"], f"{'online' if kind == 'online' else 'inclinic'}_confirmed",
                                r["phone_e164"], {
                    "lead_code": r["lead_code"], "name": r["full_name"], "doctor": r["a_doctor"],
                    "treatment": data.get("treatment"), "date": appt["d"] if appt else data.get("date"),
                    "time": appt["t"] if appt else data.get("time"),
                    "meet_link": appt["meet_link"] if appt else None,
                })  # fmt: skip
            await conn.execute(
                """update app.leads set stage = 'booked', stage_reason = null, updated_at = now()
                   where id = $1 and stage in ('new', 'follow_up', 'lost')""",
                r["lead_id"],
            )
        elif kind == "cancel" and r["a_id"]:
            await _set_appt(conn, r["a_id"], user, "cancelled")
            if r["a_cal"]:  # an online consult: Cal.com cancels it and emails the patient
                acc = await account(conn, r["clinic_id"], r["a_doctor_id"])
                await _calcom(calcom.cancel(r["a_cal"], "Cancelled at the patient's request", acc))
        elif kind == "reschedule":
            if not data.get("date"):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The new day is missing.")
            if r["a_cal"] and data.get("time") in (None, "any"):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "An online consult needs an exact new time: choose one.",
                )
            if r["a_id"]:
                await _set_appt(conn, r["a_id"], user, "rescheduled")
            new, start = await _new_slot(conn, r, data, user)
            if r["a_cal"] and start:  # an online consult: Cal.com moves it and emails the new time
                moved = await _calcom(
                    calcom.reschedule(
                        r["a_cal"],
                        start,
                        "Rescheduled at the patient's request",
                        await account(conn, r["clinic_id"], r["a_doctor_id"]),
                    )
                )
                await conn.execute(
                    """update app.appointments set meet_link = coalesce($2, $3), calendar_event_id = $4
                       where id = $1""",
                    new, moved.meet_link, r["a_meet"], moved.uid,
                )  # fmt: skip
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


class Appointment(BaseModel):
    id: str
    start: str | None  # ISO; None when the patient chose "Any time"
    day: str  # the clinic-local day
    time: str | None  # "14:30", clinic time
    doctor: str | None
    doctor_id: str | None
    type: str  # in_clinic | online
    status: str
    meet_link: str | None
    lead_code: str
    name: str
    phone: str | None
    email: str | None
    treatment: str | None
    stage: str


class Appointments(BaseModel):
    doctors: list[Option]  # active doctors, for the day view's columns
    items: list[Appointment]


@router.get("/appointments", response_model=Appointments)
async def appointments(
    user: Annotated[Staff, Depends(staff)],
    clinic: Annotated[str, Query(pattern=r"^CL\d{2,3}$")],
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date | None, Query(alias="to")] = None,
    status_: Annotated[str, Query(alias="status", pattern="^(active|all)$")] = "active",
) -> Appointments:
    """Appointments of one clinic on the given days (clinic time), earliest first. `active` = pending and
    confirmed, plus visited and no-show (what happened that day); `all` adds cancelled, rejected, moved."""
    can_see(user, clinic)
    await perm.require(await get_pool(), user, clinic, "appointments", "view")  # Who sees what
    last = date_to or date_from
    if (last - date_from).days > 62:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose at most 2 months.")
    pool = await get_pool()
    async with pool.acquire() as conn:
        limited, mine = await own_doctor(conn, user, clinic)  # a Doctor sees their own appointments
        doctors = await conn.fetch(
            "select id, name from app.doctors where clinic_id = $1 and active order by sort_order, name",
            clinic,
        )
        rows = await conn.fetch(
            """select a.id, lower(a.slot) start, d.id doctor_id, d.name doctor, a.type, a.status, a.meet_link,
                 l.lead_code, l.full_name, l.phone_e164, l.email, l.treatment, l.stage,
                 coalesce((lower(a.slot) at time zone c.timezone)::date, a.preferred_date) as day,
                 to_char(lower(a.slot) at time zone c.timezone, 'HH24:MI') tm
               from app.appointments a join app.leads l on l.id = a.lead_id
               join app.clinics c on c.id = a.clinic_id left join app.doctors d on d.id = a.doctor_id
               where a.clinic_id = $1 and l.deleted_at is null
                 and coalesce((lower(a.slot) at time zone c.timezone)::date, a.preferred_date)
                     between $2 and $3
                 and ($4 = 'all' or a.status in ('pending', 'confirmed', 'visited', 'no_show', 'missed'))
                 and (not $5 or a.doctor_id = $6::uuid)
               order by day, lower(a.slot) nulls last, l.full_name""",
            clinic, date_from, last, status_, limited, mine,
        )  # fmt: skip
    return Appointments(
        doctors=[Option(id=str(d["id"]), name=d["name"]) for d in doctors],
        items=[
            Appointment(
                id=str(r["id"]),
                start=r["start"].isoformat() if r["start"] else None,
                day=r["day"].isoformat(),
                time=r["tm"],
                doctor=r["doctor"],
                doctor_id=str(r["doctor_id"]) if r["doctor_id"] else None,
                type=r["type"],
                status=r["status"],
                meet_link=r["meet_link"],
                lead_code=r["lead_code"],
                name=r["full_name"],
                phone=r["phone_e164"],
                email=r["email"],
                treatment=r["treatment"],
                stage=r["stage"],
            )  # fmt: skip
            for r in rows
        ],
    )


class StatusIn(BaseModel):
    status: Literal["visited", "no_show", "cancelled"]
    reason: str = Field(default="", max_length=500)  # needed to cancel


class MoveIn(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    doctor_id: str | None = None
    reason: str = Field(default="", max_length=500)


async def _appt(conn: asyncpg.Connection, user: Staff, appt_id: str) -> asyncpg.Record:
    try:
        a = await conn.fetchrow(
            """select a.id a_id, a.clinic_id, a.lead_id, a.type a_type, a.status, a.doctor_id a_doctor_id,
                 a.calendar_event_id a_cal, a.meet_link a_meet,
                 coalesce((lower(a.slot) at time zone c.timezone)::date, a.preferred_date) a_day
               from app.appointments a join app.clinics c on c.id = a.clinic_id
               where a.id = $1::uuid for update of a""",
            appt_id,
        )
    except asyncpg.DataError:
        a = None
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found.")
    can_edit(user, a["clinic_id"])
    await perm.require(await get_pool(), user, a["clinic_id"], "appointments", "edit")  # Who sees what
    if a["status"] not in ("pending", "confirmed"):
        raise HTTPException(status.HTTP_409_CONFLICT, "This appointment is already closed.")
    await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)  # audit: who did it
    return a


async def _one(conn: asyncpg.Connection, appt_id: Any) -> Appointment:
    r = await conn.fetchrow(
        """select a.id, lower(a.slot) start, d.id doctor_id, d.name doctor, a.type, a.status, a.meet_link,
             l.lead_code, l.full_name, l.phone_e164, l.email, l.treatment, l.stage,
             coalesce((lower(a.slot) at time zone c.timezone)::date, a.preferred_date) as day,
             to_char(lower(a.slot) at time zone c.timezone, 'HH24:MI') tm
           from app.appointments a join app.leads l on l.id = a.lead_id
           join app.clinics c on c.id = a.clinic_id left join app.doctors d on d.id = a.doctor_id
           where a.id = $1""",
        appt_id,
    )
    return Appointment(
        id=str(r["id"]), start=r["start"].isoformat() if r["start"] else None, day=r["day"].isoformat(),
        time=r["tm"], doctor=r["doctor"], doctor_id=str(r["doctor_id"]) if r["doctor_id"] else None,
        type=r["type"], status=r["status"], meet_link=r["meet_link"], lead_code=r["lead_code"],
        name=r["full_name"], phone=r["phone_e164"], email=r["email"], treatment=r["treatment"],
        stage=r["stage"],
    )  # fmt: skip


@router.post("/appointments/{appt_id}/status", response_model=Appointment)
async def appointment_status(
    user: Annotated[Staff, Depends(staff)], appt_id: str, body: StatusIn
) -> Appointment:
    """Visited (the lead becomes Visited), No show, or Cancel with a reason (an online consult's Cal.com
    booking is cancelled too). Each goes on the lead's timeline."""
    if body.status == "cancelled" and len(body.reason.strip()) < 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give a reason to cancel.")
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        a = await _appt(conn, user, appt_id)
        await conn.execute(
            """update app.appointments set status = $2, updated_at = now(),
                 confirmed_at = case when $2 in ('visited', 'no_show') then coalesce(confirmed_at, now())
                   else confirmed_at end
               where id = $1""",
            a["a_id"], body.status,
        )  # fmt: skip
        if body.status == "visited":
            await conn.execute(
                """update app.leads set stage = 'visited', stage_reason = null, updated_at = now()
                   where id = $1""",
                a["lead_id"],
            )
        lead = {"id": a["lead_id"], "clinic_id": a["clinic_id"]}
        await _event(conn, lead, user, "appointment", {"status": body.status, "text": body.reason.strip()})
        if body.status == "cancelled" and a["a_cal"]:
            await _calcom(calcom.cancel(a["a_cal"], body.reason.strip()))
        return await _one(conn, a["a_id"])


@router.post("/appointments/{appt_id}/move", response_model=Appointment)
async def move_appointment(user: Annotated[Staff, Depends(staff)], appt_id: str, body: MoveIn) -> Appointment:
    """Moves a pending or confirmed appointment to a free time of a doctor (in-clinic and online share one
    diary). An online consult's Cal.com booking moves too, and Cal.com emails the patient the new time."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        a = await _appt(conn, user, appt_id)
        await _move(conn, a, body.date, body.time, body.doctor_id)
        lead = {"id": a["lead_id"], "clinic_id": a["clinic_id"]}
        await _event(
            conn, lead, user, "appointment",
            {"status": "moved", "to": f"{body.date} {body.time}", "text": body.reason.strip()},
        )  # fmt: skip
        if a["a_cal"]:
            start = await conn.fetchval("select lower(slot) from app.appointments where id = $1", a["a_id"])
            moved = await _calcom(
                calcom.reschedule(a["a_cal"], start, body.reason.strip() or "Moved by the clinic")
            )
            await conn.execute(
                """update app.appointments set meet_link = coalesce($2, meet_link), calendar_event_id = $3
                   where id = $1""",
                a["a_id"], moved.meet_link, moved.uid,
            )  # fmt: skip
        return await _one(conn, a["a_id"])
