"""CRM API (JSON only). Every route needs a signed-in staff member (app.crm.auth.staff)."""

from typing import Annotated

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
