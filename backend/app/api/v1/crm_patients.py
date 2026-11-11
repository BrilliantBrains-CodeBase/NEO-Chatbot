"""CRM Patients (JSON only): every person in one clinic, visited or not, and what their visits say.

A person is one row of app.leads (one per phone, or per email when there is no phone, in each clinic). Visits
come from their appointments, so nothing here can fall out of step with Appointments.
"""

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.v1.crm import TZ, Count, can_see, plain_text
from app.core.codes import CLINIC_CODE
from app.core.db import get_pool
from app.crm import permissions as perm
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm", tags=["crm"])

# How regular someone is, from their visits. Inactive comes first: 5 visits, none for a year, is not regular.
ACTIVITIES = ["never", "new", "returning", "regular", "inactive"]
REGULAR_FROM_VISITS = 3
INACTIVE_AFTER_DAYS = 180

SOURCE_FILTER = "^(chatbot|meta_ads|google_ads|manual|whatsapp|website_form|walk_in|phone_call|referral)$"
UUID = "^[0-9a-fA-F-]{36}$"
# What a date range and a sort may name; only these words ever reach the SQL.
DATE_COLUMN = {
    "added": "created_at", "contact": "last_contact_at", "first_visit": "first_visit",
    "last_visit": "last_visit",
    "next_visit": "next_visit",
}  # fmt: skip
SORT_COLUMN = {
    **DATE_COLUMN, "name": "lower(full_name)", "visits": "visits", "no_shows": "no_shows",
    "contacts": "contact_count",
}  # fmt: skip

_DAY = f"coalesce(lower(a.slot), a.preferred_date::timestamp at time zone '{TZ}')"
PEOPLE = f"""
  with seen as (
    select a.lead_id,
      count(*) filter (where a.status = 'visited') visits,
      count(*) filter (where a.status = 'no_show') no_shows,
      min({_DAY}) filter (where a.status = 'visited') first_visit,
      max({_DAY}) filter (where a.status = 'visited') last_visit,
      min({_DAY}) filter (where a.status in ('pending', 'confirmed') and {_DAY} >= now()) next_visit
    from app.appointments a where a.clinic_id = $1 group by a.lead_id
  ), marked as (
    -- Moved to Visited by hand (no appointment marked visited): when that was done is their visit day.
    select e.lead_id, max(e.created_at) at_ from app.lead_events e
    where e.clinic_id = $1 and e.kind = 'stage_change' and e.data->>'to' = 'visited' group by e.lead_id
  ), people as (
    select l.id, l.lead_code, l.full_name, l.phone_e164, l.email, l.source, l.campaign, l.treatment,
      l.doctor_id,
      d.name doctor, l.stage, l.assigned_to, p.full_name assigned, l.contact_count, l.last_contact_at,
      l.created_at, l.consent_at,
      -- A lead moved to Visited by hand has no appointment behind it, but they did come.
      greatest(coalesce(s.visits, 0), (l.stage = 'visited')::int) visits,
      coalesce(s.no_shows, 0) no_shows,
      coalesce(s.first_visit, case when l.stage = 'visited' then m.at_ end) first_visit,
      coalesce(s.last_visit, case when l.stage = 'visited' then m.at_ end) last_visit,
      s.next_visit
    from app.leads l
    left join seen s on s.lead_id = l.id
    left join marked m on m.lead_id = l.id
    left join app.doctors d on d.id = l.doctor_id
    left join app.profiles p on p.id = l.assigned_to
    where l.clinic_id = $1 and l.deleted_at is null
  ), tagged as (
    select *, case
        when visits = 0 then 'never'
        when coalesce(last_visit, last_contact_at) < now() - interval '{INACTIVE_AFTER_DAYS} days'
          then 'inactive'
        when visits >= {REGULAR_FROM_VISITS} then 'regular'
        when visits = 2 then 'returning'
        else 'new'
      end activity
    from people
  )"""


class PatientRow(BaseModel):
    code: str  # lead_code, the id shown to staff
    name: str
    phone: str | None
    email: str | None
    source: str
    campaign: str | None
    treatment: str | None
    doctor: str | None
    stage: str
    assigned: str | None
    activity: str  # never | new | returning | regular | inactive
    visits: int
    no_shows: int
    contacts: int
    consent: bool  # agreed to be contacted
    first_visit: str | None
    last_visit: str | None
    next_visit: str | None
    last_contact_at: str
    created_at: str


class Option(BaseModel):
    id: str
    name: str


class PatientList(BaseModel):
    total: int  # matching every filter
    activities: list[Count]  # each activity, for the tabs (the other filters applied, activity not)
    items: list[PatientRow]
    treatments: list[str]
    campaigns: list[str]
    doctors: list[Option]
    staff: list[Option]
    owners: list[Option] = []  # who may own leads here (active, not a doctor): Assign to on the list


class _Where:
    """Builds the filter with numbered parameters, so a value typed by staff is never part of the SQL."""

    def __init__(self, clinic: str) -> None:
        self.args: list[Any] = [clinic]
        self.parts: list[str] = []

    def arg(self, value: Any) -> str:
        self.args.append(value)
        return f"${len(self.args)}"

    def add(self, sql: str, *values: Any) -> None:
        self.parts.append(sql.format(*[self.arg(v) for v in values]))

    @property
    def sql(self) -> str:
        return " and ".join(self.parts) or "true"


def _seen_by(doctor: Any) -> str:
    """The lead's doctor, or any doctor they had an appointment with."""
    return (
        f"(doctor_id = {doctor} or exists (select 1 from app.appointments x "
        f"where x.lead_id = tagged.id and x.doctor_id = {doctor}))"
    )


@router.get("/patients", response_model=PatientList)
async def patients(
    user: Annotated[Staff, Depends(staff)],
    clinic: Annotated[str, Query(pattern=CLINIC_CODE)],
    q: Annotated[str, Query(max_length=100)] = "",
    activity: Annotated[str | None, Query(pattern="^(never|new|returning|regular|inactive)$")] = None,
    stage: Annotated[str | None, Query(pattern="^(new|follow_up|booked|visited|lost|invalid)$")] = None,
    source: Annotated[str | None, Query(pattern=SOURCE_FILTER)] = None,
    campaign: Annotated[str | None, Query(max_length=200)] = None,
    treatment: Annotated[str | None, Query(max_length=200)] = None,
    doctor: Annotated[str | None, Query(pattern=UUID)] = None,
    assigned: Annotated[str | None, Query(pattern=f"^none$|{UUID}")] = None,  # a person's id, or "none"
    visits_min: Annotated[int | None, Query(ge=0, le=10000)] = None,
    visits_max: Annotated[int | None, Query(ge=0, le=10000)] = None,
    no_shows: Annotated[Literal["yes", "no"] | None, Query()] = None,
    upcoming: Annotated[Literal["yes", "no"] | None, Query()] = None,
    consent: Annotated[Literal["yes", "no"] | None, Query()] = None,
    date_field: Annotated[
        Literal["added", "contact", "first_visit", "last_visit", "next_visit"], Query()
    ] = "added",
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    sort: Annotated[
        Literal[
            "added",
            "contact",
            "first_visit",
            "last_visit",
            "next_visit",
            "name",
            "visits",
            "no_shows",
            "contacts",
        ],
        Query(),
    ] = "added",
    direction: Annotated[Literal["asc", "desc"], Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PatientList:
    """Everyone in one clinic, with their visits. `from` and `to` (days in clinic time, both included) apply
    to the date chosen in `date_field`: someone with no such date (no visit yet) does not match a range on it.
    A doctor sees only the people they treat."""
    can_see(user, clinic)
    pool = await get_pool()
    await perm.require(pool, user, clinic, "patients", "view")  # Who sees what

    w = _Where(clinic)
    if not user.bb_admin and user.roles.get(clinic) == "doctor":
        mine = await pool.fetchval(
            "select id from app.doctors where clinic_id = $1 and user_id = $2::uuid", clinic, user.id
        )
        if mine is None:
            w.parts.append("false")
        else:
            w.parts.append(_seen_by(w.arg(mine)))
    if text := plain_text(q):
        at = w.arg(text)
        w.parts.append(
            f"(full_name ilike '%'||{at}||'%' or email ilike '%'||{at}||'%' or treatment ilike '%'||{at}||'%'"
            f" or phone_e164 like '%'||nullif(regexp_replace({at}, '[\\s-]', '', 'g'), '')||'%'"
            f" or lead_code ilike {at})"
        )
    for column, value in (
        ("stage", stage),
        ("source", source),
        ("campaign", campaign),
        ("treatment", treatment),
    ):
        if value:
            w.add(column + " = {0}", value)
    if doctor:
        w.parts.append(_seen_by(w.arg(doctor) + "::uuid"))
    if assigned == "none":
        w.parts.append("assigned_to is null")
    elif assigned:
        w.add("assigned_to::text = {0}", assigned)
    if visits_min is not None:
        w.add("visits >= {0}", visits_min)
    if visits_max is not None:
        w.add("visits <= {0}", visits_max)
    if no_shows:
        w.parts.append("no_shows > 0" if no_shows == "yes" else "no_shows = 0")
    if upcoming:
        w.parts.append(f"next_visit is {'not ' if upcoming == 'yes' else ''}null")
    if consent:
        w.parts.append(f"consent_at is {'not ' if consent == 'yes' else ''}null")
    day = f"({DATE_COLUMN[date_field]} at time zone '{TZ}')::date"
    if date_from:
        w.add(day + " >= {0}", date_from)
    if date_to:
        w.add(day + " <= {0}", date_to)

    order = f"{SORT_COLUMN[sort]} {direction} nulls last, lead_code desc"
    async with pool.acquire() as conn:
        counts = {
            r[0]: r[1]
            for r in await conn.fetch(
                f"{PEOPLE} select activity, count(*) from tagged where {w.sql} group by 1", *w.args
            )
        }
        only = w.sql
        args = list(w.args)
        if activity:
            args.append(activity)
            only += f" and activity = ${len(args)}"
        args += [limit, offset]
        rows = await conn.fetch(
            f"{PEOPLE} select * from tagged where {only} order by {order} "
            f"limit ${len(args) - 1} offset ${len(args)}",
            *args,
        )
        treatments = await conn.fetch(
            """select distinct treatment from app.leads
               where clinic_id = $1 and deleted_at is null and treatment is not null order by 1""",
            clinic,
        )
        campaigns = await conn.fetch(
            """select distinct campaign from app.leads
               where clinic_id = $1 and deleted_at is null and campaign is not null order by 1""",
            clinic,
        )
        doctors = await conn.fetch(
            "select id, name from app.doctors where clinic_id = $1 and active order by sort_order, name",
            clinic,
        )
        people = await conn.fetch(
            """select distinct p.id, p.full_name from app.leads l join app.profiles p on p.id = l.assigned_to
               where l.clinic_id = $1 and l.deleted_at is null order by 2""",
            clinic,
        )
        owners = await conn.fetch(
            """select p.id, p.full_name from app.user_clinics u join app.profiles p on p.id = u.user_id
               where u.clinic_id = $1 and u.active and u.role <> 'doctor' order by 2""",
            clinic,
        )

    def iso(value: Any) -> str | None:
        return value.isoformat() if value else None

    return PatientList(
        total=counts.get(activity, 0) if activity else sum(counts.values()),
        activities=[Count(key=a, count=counts.get(a, 0)) for a in ACTIVITIES],
        items=[
            PatientRow(
                code=r["lead_code"],
                name=r["full_name"],
                phone=r["phone_e164"],
                email=r["email"],
                source=r["source"],
                campaign=r["campaign"],
                treatment=r["treatment"],
                doctor=r["doctor"],
                stage=r["stage"],
                assigned=r["assigned"],
                activity=r["activity"],
                visits=r["visits"],
                no_shows=r["no_shows"],
                contacts=r["contact_count"],
                consent=r["consent_at"] is not None,
                first_visit=iso(r["first_visit"]),
                last_visit=iso(r["last_visit"]),
                next_visit=iso(r["next_visit"]),
                last_contact_at=r["last_contact_at"].isoformat(),
                created_at=r["created_at"].isoformat(),
            )
            for r in rows
        ],  # fmt: skip
        treatments=[r[0] for r in treatments],
        campaigns=[r[0] for r in campaigns],
        doctors=[Option(id=str(r["id"]), name=r["name"]) for r in doctors],
        staff=[Option(id=str(r["id"]), name=r["full_name"]) for r in people],
        owners=[Option(id=str(r["id"]), name=r["full_name"]) for r in owners],
    )
