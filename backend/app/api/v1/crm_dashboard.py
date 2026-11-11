"""The CRM home (Dashboard), JSON only: one clinic's numbers for the last 7, 30 or 90 days, each next to the
period before it, a day-by-day series for the charts, appointment outcomes, today's schedule, and a month's
bookings for the calendar.

A period is whole days in clinic time, today included: "7 days" is today and the 6 days before it.
"""

import re
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.v1.crm import IN_INBOX, STAGES, TZ, Count, can_see
from app.core.codes import CLINIC_CODE
from app.core.db import get_pool
from app.crm import permissions as perm
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm", tags=["crm"])

CLINIC = CLINIC_CODE
DAY = f"coalesce((lower(a.slot) at time zone '{TZ}')::date, a.preferred_date)"  # an appointment's day
AT = f"::date::timestamp at time zone '{TZ}'"  # a clinic day's start, as a moment
COUNTED = "('rejected', 'rescheduled')"  # not a booking: refused, or replaced by its new time


class TodayAppt(BaseModel):
    time: str | None  # "11:30", None when the patient chose "Any time"
    end: str | None = None  # "11:45"
    patient: str
    lead_code: str
    doctor: str | None
    doctor_id: str | None = None
    type: str  # in_clinic | online
    status: str
    treatment: str | None


class Totals(BaseModel):
    """One period's headline numbers."""

    leads: int  # new leads
    converted: int  # of those, now Booked or Visited
    bookings: int  # appointments made (not refused, not replaced by a new time)
    visits: int  # appointments marked Visited, on their day
    chats: int
    chat_leads: int  # chats that became a lead


class Day(BaseModel):
    day: str  # 2026-11-06
    leads: int
    leads_before: int  # the same day of the period before (for the dashed line)
    bookings: int
    visits: int
    chats: int


class Dashboard(BaseModel):
    clinic: str
    days: int
    start: str  # the period's first day
    new_leads: int  # = now.leads, kept for older screens
    inbox_pending: int
    callbacks_waiting: int
    followups_due: int  # leads in the Follow Up stage (Leads → Follow Up)
    now: Totals
    before: Totals  # the same number of days just before
    series: list[Day]
    outcomes: list[Count]  # appointments on days in the period, by status
    today: list[TodayAppt]
    sources: list[Count]
    funnel: list[Count]
    treatments: list[Count]
    chats: int
    chat_leads: int
    chat_answered_by: list[Count]  # flow, rule, kb, ... (bot replies in the period)
    unanswered: int


async def _allowed(user: Staff, clinic: str) -> None:
    can_see(user, clinic)
    await perm.require(await get_pool(), user, clinic, "dashboard", "view")  # Who sees what


def _by_day(rows: list[Any]) -> dict[date, int]:
    return {r[0]: r[1] for r in rows}


@router.get("/dashboard", response_model=Dashboard)
async def dashboard(
    user: Annotated[Staff, Depends(staff)],
    clinic: Annotated[str, Query(pattern=CLINIC)],
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> Dashboard:
    """The Dashboard for one clinic: the last `days` days (today included) and the same before them."""
    await _allowed(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn:
        today: date = await conn.fetchval(f"select (now() at time zone '{TZ}')::date")
        start = today - timedelta(days=days - 1)
        first = start - timedelta(days=days)  # the period before starts here
        # $1 clinic, $2 the period's first day, $3 the period before's first day
        args = (clinic, start, first)
        k = await conn.fetchrow(
            """select
              (select count(*) from app.leads l where l.clinic_id=$1 and l.deleted_at is null
                 and l.stage not in ('lost','invalid') and """ + IN_INBOX + """) ip,
              (select count(*) from app.requests r join app.leads l on l.id = r.lead_id
                 where r.clinic_id=$1 and r.status='pending' and r.type='callback'
                   and l.assigned_to is not null) cb,
              (select count(*) from app.leads where clinic_id=$1 and deleted_at is null
                 and stage='follow_up' and assigned_to is not null) fu,
              (select count(*) from app.unanswered_questions where clinic_id=$1 and not reviewed) un""",
            clinic,
        )  # fmt: skip
        leads = await conn.fetchrow(
            f"""select count(*) filter (where created_at >= ($2{AT})) n,
                   count(*) filter (where created_at < ($2{AT})) b,
                   count(*) filter (where created_at >= ($2{AT}) and stage in ('booked','visited')) cn,
                   count(*) filter (where created_at < ($2{AT}) and stage in ('booked','visited')) cb
                from app.leads where clinic_id=$1 and deleted_at is null and created_at >= ($3{AT})""",
            *args,
        )
        books = await conn.fetchrow(
            f"""select count(*) filter (where created_at >= ($2{AT}) and status not in {COUNTED}) n,
                   count(*) filter (where created_at < ($2{AT}) and status not in {COUNTED}) b,
                   count(*) filter (where status = 'visited' and {DAY} >= $2 and {DAY} <= $4) vn,
                   count(*) filter (where status = 'visited' and {DAY} >= $3 and {DAY} < $2) vb
                from app.appointments a
                where clinic_id=$1 and (created_at >= ($3{AT}) or {DAY} >= $3)""",
            *args, today,
        )  # fmt: skip
        chats = await conn.fetchrow(
            f"""select count(*) filter (where started_at >= ($2{AT})) n,
                   count(*) filter (where started_at < ($2{AT})) b,
                   count(*) filter (where started_at >= ($2{AT}) and lead_id is not null) ln,
                   count(*) filter (where started_at < ($2{AT}) and lead_id is not null) lb
                from app.chat_sessions where clinic_id=$1 and started_at >= ($3{AT})""",
            *args,
        )

        async def per_day(sql: str) -> dict[date, int]:
            return _by_day(await conn.fetch(sql, clinic, first))

        day_of = f" at time zone '{TZ}')::date"
        lead_days = await per_day(
            f"""select (created_at{day_of}, count(*) from app.leads
                where clinic_id=$1 and deleted_at is null and created_at >= ($2{AT}) group by 1"""
        )
        book_days = await per_day(
            f"""select (created_at{day_of}, count(*) from app.appointments
                where clinic_id=$1 and status not in {COUNTED} and created_at >= ($2{AT}) group by 1"""
        )
        visit_days = await per_day(
            f"""select {DAY}, count(*) from app.appointments a
                where clinic_id=$1 and status = 'visited' and {DAY} >= $2 group by 1"""
        )
        chat_days = await per_day(
            f"""select (started_at{day_of}, count(*) from app.chat_sessions
                where clinic_id=$1 and started_at >= ($2{AT}) group by 1"""
        )
        outcomes = [
            Count(key=r[0], count=r[1])
            for r in await conn.fetch(
                f"""select status, count(*) from app.appointments a
                    where clinic_id=$1 and status <> 'rescheduled' and {DAY} between $2 and $3
                    group by 1 order by 2 desc""",
                clinic, start, today,
            )
        ]  # fmt: skip
        schedule = await conn.fetch(
            f"""select to_char(lower(a.slot) at time zone '{TZ}', 'HH24:MI') tm,
                   to_char(upper(a.slot) at time zone '{TZ}', 'HH24:MI') te, l.full_name, l.lead_code,
                   d.name doctor, d.id::text doctor_id, a.type, a.status, l.treatment
                from app.appointments a join app.leads l on l.id = a.lead_id
                left join app.doctors d on d.id = a.doctor_id
                where a.clinic_id=$1 and a.status in ('pending','confirmed','visited') and {DAY} = $2
                order by lower(a.slot) nulls last""",
            clinic, today,
        )  # fmt: skip

        leads_in = "from app.leads where clinic_id=$1 and deleted_at is null and created_at >= ($2" + AT + ")"

        async def group(sql: str) -> list[Count]:
            return [Count(key=r[0] or "", count=r[1]) for r in await conn.fetch(sql, clinic, start)]

        sources = await group(f"select source, count(*) {leads_in} group by 1 order by 2 desc")
        stages = {c.key: c.count for c in await group(f"select stage, count(*) {leads_in} group by 1")}
        treatments = await group(
            f"select treatment, count(*) {leads_in} and treatment is not null"
            " group by 1 order by 2 desc limit 5"
        )
        answered = await group(
            f"""select answered_by, count(*) from app.chat_messages where clinic_id=$1 and role='bot'
                and answered_by is not null and created_at >= ($2{AT}) group by 1 order by 2 desc"""
        )

    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        series.append(
            Day(
                day=d.isoformat(),
                leads=lead_days.get(d, 0),
                leads_before=lead_days.get(d - timedelta(days=days), 0),
                bookings=book_days.get(d, 0),
                visits=visit_days.get(d, 0),
                chats=chat_days.get(d, 0),
            )
        )
    now = Totals(
        leads=leads["n"], converted=leads["cn"], bookings=books["n"], visits=books["vn"],
        chats=chats["n"], chat_leads=chats["ln"],
    )  # fmt: skip
    before = Totals(
        leads=leads["b"], converted=leads["cb"], bookings=books["b"], visits=books["vb"],
        chats=chats["b"], chat_leads=chats["lb"],
    )  # fmt: skip
    return Dashboard(
        clinic=clinic,
        days=days,
        start=start.isoformat(),
        new_leads=now.leads,
        inbox_pending=k["ip"],
        callbacks_waiting=k["cb"],
        followups_due=k["fu"],
        now=now,
        before=before,
        series=series,
        outcomes=outcomes,
        today=[
            TodayAppt(
                time=r["tm"],
                end=r["te"],
                patient=r["full_name"],
                lead_code=r["lead_code"],
                doctor=r["doctor"],
                doctor_id=r["doctor_id"],
                type=r["type"],
                status=r["status"],
                treatment=r["treatment"],
            )
            for r in schedule
        ],
        sources=sources,
        funnel=[Count(key=s, count=stages.get(s, 0)) for s in STAGES],
        treatments=treatments,
        chats=now.chats,
        chat_leads=now.chat_leads,
        chat_answered_by=answered,
        unanswered=k["un"],
    )


class Month(BaseModel):
    month: str  # 2026-11
    today: str  # 2026-11-06, in clinic time
    days: list[Count]  # 2026-11-03 -> appointments that day (only days with any)


MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


@router.get("/dashboard/calendar", response_model=Month)
async def calendar(
    user: Annotated[Staff, Depends(staff)],
    clinic: Annotated[str, Query(pattern=CLINIC)],
    month: Annotated[str | None, Query(max_length=7)] = None,
) -> Month:
    """Appointments per day in one month (this month when left out), for the Dashboard's calendar. Refused and
    cancelled bookings and ones moved to a new time are not counted."""
    await _allowed(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn:
        today: date = await conn.fetchval(f"select (now() at time zone '{TZ}')::date")
        if month is None:
            first = today.replace(day=1)
        elif m := MONTH.match(month):
            first = date(int(m[1]), int(m[2]), 1)
        else:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The month is like 2026-11.")
        after = (first + timedelta(days=32)).replace(day=1)
        rows = await conn.fetch(
            f"""select {DAY}, count(*) from app.appointments a
                where clinic_id=$1 and status in ('pending','confirmed','visited','no_show','missed')
                  and {DAY} >= $2 and {DAY} < $3 group by 1 order by 1""",
            clinic, first, after,
        )  # fmt: skip
    return Month(
        month=first.strftime("%Y-%m"),
        today=today.isoformat(),
        days=[Count(key=r[0].isoformat(), count=r[1]) for r in rows],
    )
