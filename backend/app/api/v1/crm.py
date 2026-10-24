"""CRM API (JSON only). Every route needs a signed-in staff member (app.crm.auth.staff)."""

import json
from typing import Annotated

from asyncpg import Record
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.db import get_pool
from app.crm.auth import ROLE_LABEL, Staff, staff

router = APIRouter(prefix="/crm", tags=["crm"])


class ClinicAccess(BaseModel):
    id: str  # CL01
    name: str  # Neo Follicle
    role: str  # bb_admin
    role_label: str  # BB Admin


class Me(BaseModel):
    id: str
    name: str
    email: str
    initials: str
    bb_admin: bool
    role_label: str  # the highest role, for the profile menu
    clinics: list[ClinicAccess]


def initials(name: str) -> str:
    parts = [p for p in name.replace("Dr ", "").split() if p[:1].isalpha()]
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper() if parts else "?"


RANK = ["bb_admin", "clinic_manager", "front_desk", "doctor"]


@router.get("/me", response_model=Me)
async def me(user: Annotated[Staff, Depends(staff)]) -> Me:
    """Who is signed in and which clinics they see. BB Admin sees every active clinic (not test clinics)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("select id, name from app.clinics where active and not is_test order by id")
    clinics = []
    for r in rows:
        role = "bb_admin" if user.bb_admin else user.roles.get(r["id"])
        if role:
            clinics.append(ClinicAccess(id=r["id"], name=r["name"], role=role, role_label=ROLE_LABEL[role]))
    top = min(user.roles.values(), key=RANK.index)
    return Me(
        id=user.id,
        name=user.name,
        email=user.email,
        initials=initials(user.name),
        bb_admin=user.bb_admin,
        role_label=ROLE_LABEL[top],
        clinics=clinics,
    )


class Count(BaseModel):
    key: str
    count: int


class TodayAppt(BaseModel):
    time: str | None  # "11:30", None when the patient chose "Any time"
    patient: str
    lead_code: str
    doctor: str | None
    type: str  # in_clinic | online
    status: str
    treatment: str | None


class Dashboard(BaseModel):
    clinic: str
    days: int
    new_leads: int
    inbox_pending: int
    callbacks_waiting: int
    followups_due: int
    today: list[TodayAppt]
    sources: list[Count]
    funnel: list[Count]
    treatments: list[Count]
    chats: int
    chat_leads: int
    chat_answered_by: list[Count]  # flow, rule, kb, ... (bot replies in the period)
    unanswered: int


TZ = "Asia/Kolkata"
STAGES = ["new", "follow_up", "booked", "visited", "lost", "invalid"]


def can_see(user: Staff, clinic: str) -> None:
    if not (user.bb_admin or clinic in user.roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this clinic.")


@router.get("/dashboard", response_model=Dashboard)
async def dashboard(
    user: Annotated[Staff, Depends(staff)],
    clinic: Annotated[str, Query(pattern=r"^CL\d{2}$")],
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> Dashboard:
    """The Dashboard numbers for one clinic over the last `days` days (today in clinic time)."""
    can_see(user, clinic)
    since = f"now() - make_interval(days => {days})"
    pool = await get_pool()
    async with pool.acquire() as conn:
        leads_in = f"from app.leads where clinic_id=$1 and deleted_at is null and created_at >= {since}"
        today_end = f"(date_trunc('day', now() at time zone '{TZ}') + interval '1 day') at time zone '{TZ}'"
        k = await conn.fetchrow(
            f"""select
              (select count(*) {leads_in}) nl,
              (select count(*) from app.requests where clinic_id=$1 and status='pending') ip,
              (select count(*) from app.requests where clinic_id=$1 and status='pending'
                 and type='callback') cb,
              (select count(*) from app.tasks where clinic_id=$1 and status='open'
                 and due_at < {today_end}) fu,
              (select count(*) from app.chat_sessions where clinic_id=$1 and started_at >= {since}) ch,
              (select count(*) from app.chat_sessions where clinic_id=$1 and started_at >= {since}
                 and lead_id is not null) cl,
              (select count(*) from app.unanswered_questions where clinic_id=$1 and not reviewed) un""",
            clinic,
        )
        today = await conn.fetch(
            f"""select to_char(lower(a.slot) at time zone '{TZ}', 'HH24:MI') tm, l.full_name, l.lead_code,
                   d.name doctor, a.type, a.status, l.treatment
                from app.appointments a join app.leads l on l.id = a.lead_id
                left join app.doctors d on d.id = a.doctor_id
                where a.clinic_id=$1 and a.status in ('pending','confirmed')
                  and coalesce((lower(a.slot) at time zone '{TZ}')::date, a.preferred_date)
                      = (now() at time zone '{TZ}')::date
                order by lower(a.slot) nulls last""",
            clinic,
        )

        async def group(sql: str) -> list[Count]:
            return [Count(key=r[0] or "", count=r[1]) for r in await conn.fetch(sql, clinic)]

        sources = await group(f"select source, count(*) {leads_in} group by 1 order by 2 desc")
        stages = {c.key: c.count for c in await group(f"select stage, count(*) {leads_in} group by 1")}
        treatments = await group(
            f"select treatment, count(*) {leads_in} and treatment is not null"
            " group by 1 order by 2 desc limit 5"
        )
        answered = await group(
            f"""select answered_by, count(*) from app.chat_messages where clinic_id=$1 and role='bot'
                and answered_by is not null and created_at >= {since} group by 1 order by 2 desc"""
        )
    return Dashboard(
        clinic=clinic,
        days=days,
        new_leads=k["nl"],
        inbox_pending=k["ip"],
        callbacks_waiting=k["cb"],
        followups_due=k["fu"],
        today=[
            TodayAppt(
                time=r["tm"],
                patient=r["full_name"],
                lead_code=r["lead_code"],
                doctor=r["doctor"],
                type=r["type"],
                status=r["status"],
                treatment=r["treatment"],
            )
            for r in today
        ],
        sources=sources,
        funnel=[Count(key=s, count=stages.get(s, 0)) for s in STAGES],
        treatments=treatments,
        chats=k["ch"],
        chat_leads=k["cl"],
        chat_answered_by=answered,
        unanswered=k["un"],
    )


class LeadRow(BaseModel):
    code: str  # lead_code, the id shown to staff
    name: str
    phone: str | None
    email: str | None
    source: str
    campaign: str | None
    treatment: str | None
    doctor: str | None
    type: str | None  # in_clinic | online
    stage: str
    assigned: str | None
    contacts: int
    last_contact_at: str
    created_at: str


class LeadList(BaseModel):
    total: int  # matching the filters
    stages: list[Count]  # every stage, for the tabs (search and source applied, stage not)
    items: list[LeadRow]


class LeadEvent(BaseModel):
    kind: str
    data: dict[str, object]
    by: str | None
    at: str


class ChatLine(BaseModel):
    role: str  # patient | bot
    text: str
    at: str


class LeadDetail(LeadRow):
    stage_reason: str | None
    notes: str
    page_url: str | None
    device: str | None
    verified: bool
    events: list[LeadEvent]
    chat: list[ChatLine]  # the latest chat, oldest first


LEAD_SELECT = """select l.lead_code, l.full_name, l.phone_e164, l.email, l.source, l.campaign, l.treatment,
    d.name doctor, l.appointment_type, l.stage, p.full_name assigned, l.contact_count,
    l.last_contact_at, l.created_at
  from app.leads l left join app.doctors d on d.id = l.doctor_id
  left join app.profiles p on p.id = l.assigned_to"""


def lead_row(r: Record) -> dict[str, object]:
    return {
        "code": r["lead_code"], "name": r["full_name"], "phone": r["phone_e164"], "email": r["email"],
        "source": r["source"], "campaign": r["campaign"], "treatment": r["treatment"], "doctor": r["doctor"],
        "type": r["appointment_type"], "stage": r["stage"], "assigned": r["assigned"],
        "contacts": r["contact_count"], "last_contact_at": r["last_contact_at"].isoformat(),
        "created_at": r["created_at"].isoformat(),
    }  # fmt: skip


@router.get("/leads", response_model=LeadList)
async def leads(
    user: Annotated[Staff, Depends(staff)],
    clinic: Annotated[str, Query(pattern=r"^CL\d{2}$")],
    stage: Annotated[str | None, Query(pattern="^(new|follow_up|booked|visited|lost|invalid)$")] = None,
    source: Annotated[str | None, Query(pattern="^(chatbot|meta_ads|google_ads|manual|whatsapp)$")] = None,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LeadList:
    """Leads of one clinic, newest contact first. `q` matches name, phone, email or lead code."""
    can_see(user, clinic)
    where = "l.clinic_id = $1 and l.deleted_at is null and ($2::text is null or l.source = $2)"
    where += " and ($3 = '' or l.full_name ilike '%'||$3||'%' or l.phone_e164 like '%'||$3||'%'"
    where += " or l.email ilike '%'||$3||'%' or l.lead_code ilike $3)"
    args = [clinic, source, q.strip()]
    pool = await get_pool()
    async with pool.acquire() as conn:
        counts = {r[0]: r[1] for r in await conn.fetch(
            f"select l.stage, count(*) from app.leads l where {where} group by 1", *args
        )}  # fmt: skip
        rows = await conn.fetch(
            f"""{LEAD_SELECT} where {where} and ($4::text is null or l.stage = $4)
                order by l.last_contact_at desc limit $5 offset $6""",
            *args, stage, limit, offset,
        )  # fmt: skip
    return LeadList(
        total=counts.get(stage, 0) if stage else sum(counts.values()),
        stages=[Count(key=s, count=counts.get(s, 0)) for s in STAGES],
        items=[LeadRow.model_validate(lead_row(r)) for r in rows],
    )


@router.get("/leads/{code}", response_model=LeadDetail)
async def lead(user: Annotated[Staff, Depends(staff)], code: str) -> LeadDetail:
    """One lead with its timeline and latest chat. The clinic comes from the lead itself."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        r = await conn.fetchrow(
            f"""{
                LEAD_SELECT.replace(
                    "l.created_at",
                    "l.created_at, l.id, l.clinic_id, l.stage_reason, l.notes,"
                    " l.page_url, l.device, l.verified",
                )
            } where l.lead_code = $1 and l.deleted_at is null""",
            code,
        )
        if r is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found.")
        can_see(user, r["clinic_id"])
        events = await conn.fetch(
            """select e.kind, e.data, p.full_name, e.created_at from app.lead_events e
               left join app.profiles p on p.id = e.actor where e.lead_id = $1 order by e.created_at desc
               limit 100""",
            r["id"],
        )
        chat = await conn.fetch(
            """select m.role, m.text, m.created_at from app.chat_messages m where m.session_id = (
                 select id from app.chat_sessions where lead_id = $1 order by last_at desc limit 1)
               order by m.id""",
            r["id"],
        )
    return LeadDetail.model_validate(
        lead_row(r)
        | {
            "stage_reason": r["stage_reason"], "notes": r["notes"], "page_url": r["page_url"],
            "device": r["device"], "verified": r["verified"],
            "events": [
                {"kind": e[0], "data": json.loads(e[1]) if isinstance(e[1], str) else e[1], "by": e[2],
                 "at": e[3].isoformat()}
                for e in events
            ],
            "chat": [{"role": m[0], "text": m[1], "at": m[2].isoformat()} for m in chat],
        }
    )  # fmt: skip
