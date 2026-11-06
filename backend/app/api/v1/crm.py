"""CRM API (JSON only). Every route needs a signed-in staff member (app.crm.auth.staff)."""

import csv
import io
import json
import re
from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from typing import Annotated, Any, Literal

from asyncpg import Connection, Record
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.chat.content import content
from app.chat.flows import EMAIL, normal_phone
from app.core.codes import CLINIC_CODE, current_lead
from app.core.db import get_pool
from app.crm import permissions as perm
from app.crm import webhooks, whatsapp
from app.crm.auth import ROLE_LABEL, Staff, staff

router = APIRouter(prefix="/crm", tags=["crm"])


class ClinicAccess(BaseModel):
    id: str  # NFHT
    name: str  # Neo Follicle Hair Transplant
    role: str  # bb_admin
    role_label: str  # Super Admin
    access: dict[str, str] = {}  # Who sees what: screen -> hidden / view / edit (time-limited too)


class Me(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None = None  # +919876543210
    photo: str | None = None  # a small data:image, resized in the browser (My profile)
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
    """Who is signed in and which clinics they see. Super Admin: every active clinic (not test clinics)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("select id, name from app.clinics where active and not is_test order by id")
        mine = await conn.fetchrow(
            """select p.phone, f.photo from app.profiles p
               left join app.profile_photos f on f.user_id = p.id where p.id = $1::uuid""",
            user.id,
        )
        # Team's "Last sign-in": asked on sign-in and when the CRM opens (written at most every 5 minutes).
        await conn.execute(
            """update app.profiles set last_seen_at = now()
               where id = $1::uuid
                 and (last_seen_at is null or last_seen_at < now() - interval '5 minutes')""",
            user.id,
        )
    clinics = []
    for r in rows:
        role = "bb_admin" if user.bb_admin else user.roles.get(r["id"])
        if role:
            access = await perm.for_person(pool, r["id"], user.id, role)
            clinics.append(
                ClinicAccess(
                    id=r["id"], name=r["name"], role=role, role_label=ROLE_LABEL[role], access=access
                )
            )
    top = min(user.roles.values(), key=RANK.index)
    return Me(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=mine["phone"] if mine else None,
        photo=mine["photo"] if mine else None,
        initials=initials(user.name),
        bb_admin=user.bb_admin,
        role_label=ROLE_LABEL[top],
        clinics=clinics,
    )


class Count(BaseModel):
    key: str
    count: int


TZ = "Asia/Kolkata"
STAGES = ["new", "follow_up", "booked", "visited", "lost", "invalid"]


class MeChange(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    # Left out: unchanged; null: removed.
    phone: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{6,14}$")


@router.patch("/me", response_model=Me)
async def change_me(user: Annotated[Staff, Depends(staff)], body: MeChange) -> Me:
    """My profile: my own name and phone. Email: confirmed through Supabase Auth (POST /me/email first); roles
    are changed by a manager in Team."""
    name = " ".join(body.name.split())
    if len(name) < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Please enter your name.")
    pool = await get_pool()
    async with pool.acquire() as conn:
        if "phone" in body.model_fields_set:
            await conn.execute(
                "update app.profiles set full_name = $2, phone = $3 where id = $1::uuid",
                user.id,
                name,
                body.phone,
            )
        else:
            await conn.execute("update app.profiles set full_name = $2 where id = $1::uuid", user.id, name)
    return await me(replace(user, name=name))


class PhotoIn(BaseModel):
    photo: str | None = Field(default=None, max_length=60_000)  # null: back to initials


PHOTO = re.compile(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$")


@router.put("/me/photo", response_model=Me)
async def change_photo(user: Annotated[Staff, Depends(staff)], body: PhotoIn) -> Me:
    """My profile photo, shown in the top bar. The browser resizes it first (a square, about 10 KB)."""
    pool = await get_pool()
    if body.photo is None:
        await pool.execute("delete from app.profile_photos where user_id = $1::uuid", user.id)
        return await me(user)
    if not PHOTO.match(body.photo):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Upload a PNG, JPG or WebP image.")
    await pool.execute(
        """insert into app.profile_photos (user_id, photo) values ($1::uuid, $2)
           on conflict (user_id) do update set photo = $2""",
        user.id, body.photo,
    )  # fmt: skip
    return await me(user)


class EmailIn(BaseModel):
    email: str = Field(max_length=120)


@router.post("/me/email", status_code=status.HTTP_204_NO_CONTENT)
async def check_new_email(user: Annotated[Staff, Depends(staff)], body: EmailIn) -> Response:
    """Before My profile asks Supabase Auth to change the sign-in email: the address must be valid, new and
    not someone else's. Supabase then emails a confirmation link; once clicked, the profile follows (0038)."""
    email = body.email.strip().lower()
    if not EMAIL.match(email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Please enter a valid email address.")
    if email == user.email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That is already your email.")
    pool = await get_pool()
    if await pool.fetchval("select 1 from app.profiles where email = $1 and id <> $2::uuid", email, user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Another account already uses that email.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def in_clinic(user: Staff, clinic: str) -> bool:
    """Lead codes are readable, so another clinic's lead answers "not found": nothing about it shows."""
    return user.bb_admin or clinic in user.roles


async def own_doctor(conn: Any, user: Staff, clinic: str) -> tuple[bool, str | None]:
    """Whether this person is limited to their own doctor record here, and that record (if linked)."""
    if user.bb_admin or user.roles.get(clinic) != "doctor":
        return False, None
    mine = await conn.fetchval(
        "select id from app.doctors where clinic_id = $1 and user_id = $2::uuid", clinic, user.id
    )
    return True, str(mine) if mine else None


def can_see(user: Staff, clinic: str) -> None:
    if not (user.bb_admin or clinic in user.roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this clinic.")


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
    assigned_id: str | None
    contacts: int
    last_contact_at: str
    created_at: str
    pending: int = 0  # requests waiting for the owner (book, cancel, call back...): "Needs action"
    doctor_id: str | None = None  # the preferred doctor's id (Edit details)


class LeadList(BaseModel):
    total: int  # matching the filters
    stages: list[Count]  # every stage, for the tabs (search and source applied, stage not)
    items: list[LeadRow]
    treatments: list[str] = []  # every treatment this clinic's leads have, for the filter


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


SOURCE_FILTER = "^(chatbot|meta_ads|google_ads|manual|whatsapp|website_form)$"
LEAD_SELECT = """select l.lead_code, l.full_name, l.phone_e164, l.email, l.source, l.campaign, l.treatment,
    d.name doctor, l.doctor_id, l.appointment_type, l.stage, p.full_name assigned, l.assigned_to,
    l.contact_count,
    l.last_contact_at, (select count(*) from app.requests rq where rq.lead_id = l.id
      and rq.status = 'pending') pending, l.created_at
  from app.leads l left join app.doctors d on d.id = l.doctor_id
  left join app.profiles p on p.id = l.assigned_to"""


def lead_row(r: Record) -> dict[str, object]:
    return {
        "code": r["lead_code"], "name": r["full_name"], "phone": r["phone_e164"], "email": r["email"],
        "source": r["source"], "campaign": r["campaign"], "treatment": r["treatment"], "doctor": r["doctor"],
        "type": r["appointment_type"], "stage": r["stage"], "assigned": r["assigned"],
        "assigned_id": str(r["assigned_to"]) if r["assigned_to"] else None,
        "contacts": r["contact_count"], "last_contact_at": r["last_contact_at"].isoformat(),
        "created_at": r["created_at"].isoformat(), "pending": r["pending"],
        "doctor_id": str(r["doctor_id"]) if r["doctor_id"] else None,
    }  # fmt: skip


def plain_text(q: str) -> str:
    """What staff typed, searched as plain text: % and _ are not wildcards, a backslash is no escape."""
    return q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# Whose leads: those with an owner (Leads), those waiting in the Inbox for one, or both.
Owner = Literal["assigned", "unassigned", "all"]
REQUEST_TYPES = ("book", "online", "cancel", "reschedule", "callback", "question")
# Leads with a request waiting: of any type, or of one.
RequestFilter = Literal["any", "book", "online", "cancel", "reschedule", "callback", "question"]


def owner_where(owner: Owner) -> str:
    return {"assigned": " and l.assigned_to is not null", "unassigned": " and l.assigned_to is null"}.get(
        owner, ""
    )


def request_where(request: RequestFilter | None) -> str:
    """Only from the fixed list above (validated by the route), so it is safe in the SQL."""
    if request is None:
        return ""
    if request != "any" and request not in REQUEST_TYPES:
        raise ValueError(request)
    kind = "" if request == "any" else f" and rq.type = '{request}'"
    waiting = "select 1 from app.requests rq where rq.lead_id = l.id and rq.status = 'pending'"
    return f" and exists ({waiting}{kind})"


def _lead_filter(
    clinic: str,
    source: str | None,
    q: str,
    date_from: date | None,
    date_to: date | None,
    treatment: str | None,
    owner: Owner = "all",
    request: RequestFilter | None = None,
) -> tuple[str, list[Any]]:
    """The Leads filters, shared by the list and the export. Leads shows assigned leads; unassigned ones wait
    in the Inbox (an Admin can list them here too)."""
    where = "l.clinic_id = $1 and l.deleted_at is null and ($2::text is null or l.source = $2)"
    where += " and ($3 = '' or l.full_name ilike '%'||$3||'%'"
    where += " or l.phone_e164 like '%'||nullif(regexp_replace($3, '[\\s-]', '', 'g'), '')||'%'"
    where += " or l.treatment ilike '%'||$3||'%' or l.email ilike '%'||$3||'%' or l.lead_code ilike $3)"
    where += f" and ($4::date is null or (l.created_at at time zone '{TZ}')::date >= $4)"
    where += f" and ($5::date is null or (l.created_at at time zone '{TZ}')::date <= $5)"
    where += " and ($6::text is null or l.treatment = $6)"
    where += owner_where(owner) + request_where(request)
    # A search for an old lead code (CL01-00003) finds the lead under its new one.
    return where, [clinic, source, plain_text(current_lead(q.strip())), date_from, date_to, treatment]


# The newest lead first; imported leads share one moment, so the code keeps the pages in a fixed order.
LEAD_ORDER = "order by l.created_at desc, l.lead_code desc"


@router.get("/leads", response_model=LeadList)
async def leads(
    user: Annotated[Staff, Depends(staff)],
    clinic: Annotated[str, Query(pattern=CLINIC_CODE)],
    stage: Annotated[str | None, Query(pattern="^(new|follow_up|booked|visited|lost|invalid)$")] = None,
    source: Annotated[str | None, Query(pattern=SOURCE_FILTER)] = None,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    treatment: Annotated[str | None, Query(max_length=200)] = None,
    owner: Owner = "assigned",
    request: RequestFilter | None = None,
) -> LeadList:
    """Leads of one clinic, newest first. `q` matches name, phone (spaces and dashes ignored),
    treatment, email or lead code; `from` and `to` (days in clinic time, both included) keep leads created in
    that range; `treatment` keeps leads of exactly that treatment. `owner`: assigned leads (default; the
    unassigned wait in the Inbox), unassigned or all. `request`: leads with a request waiting ("any", or one
    type), the "Needs action" filter."""
    can_see(user, clinic)
    await perm.require(await get_pool(), user, clinic, "leads", "view")  # Who sees what
    where, args = _lead_filter(clinic, source, q, date_from, date_to, treatment, owner, request)
    pool = await get_pool()
    async with pool.acquire() as conn:
        counts = {r[0]: r[1] for r in await conn.fetch(
            f"select l.stage, count(*) from app.leads l where {where} group by 1", *args
        )}  # fmt: skip
        rows = await conn.fetch(
            f"""{LEAD_SELECT} where {where} and ($7::text is null or l.stage = $7)
                {LEAD_ORDER} limit $8 offset $9""",
            *args, stage, limit, offset,
        )  # fmt: skip
        treatments = await conn.fetch(
            """select distinct treatment from app.leads
               where clinic_id = $1 and deleted_at is null and treatment is not null order by 1""",
            clinic,
        )
    return LeadList(
        total=counts.get(stage, 0) if stage else sum(counts.values()),
        stages=[Count(key=s, count=counts.get(s, 0)) for s in STAGES],
        items=[LeadRow.model_validate(lead_row(r)) for r in rows],
        treatments=[r[0] for r in treatments],
    )


def bulk_access(user: Staff, clinic: str) -> None:
    """Export and import move many patients' details at once: Super Admin and admins only."""
    can_see(user, clinic)
    if not user.bb_admin and user.roles.get(clinic) != "clinic_manager":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin can export or import leads.")


SOURCE_LABEL = {
    "chatbot": "Chatbot", "meta_ads": "Meta Ads", "google_ads": "Google Ads", "manual": "Manual",
    "whatsapp": "WhatsApp", "website_form": "Website form",
}  # fmt: skip
EXPORT_COLUMNS = ["Code", "Name", "Phone", "Email", "Treatment", "Source", "Campaign", "Doctor", "Stage",
                  "Assigned", "Created", "Last contact"]  # fmt: skip


def cell(value: object) -> str:
    """A spreadsheet runs a cell starting with = + - or @ as a formula: patients' typed text stays text."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def export_phone(e164: str | None, cc: str | None) -> str:
    """With a space after the country code: Excel keeps it as text instead of showing 9.19E+11."""
    if not e164:
        return ""
    return f"{cc} {e164[len(cc) :]}" if cc and e164.startswith(cc) else e164


# The columns the export needs on top of the list's.
EXPORT_SELECT = LEAD_SELECT.replace(
    "l.created_at",
    f"l.phone_cc, to_char(l.created_at at time zone '{TZ}', 'YYYY-MM-DD HH24:MI') created,"
    f" to_char(l.last_contact_at at time zone '{TZ}', 'YYYY-MM-DD HH24:MI') contacted",
)


def csv_file(name: str, columns: list[str], rows: list[list[object]]) -> Response:
    """A CSV download for Excel. Cells that hold typed text go through cell first."""
    out = io.StringIO()
    sheet = csv.writer(out)
    sheet.writerow(columns)
    sheet.writerows(rows)
    return Response(
        "\ufeff" + out.getvalue(),  # the mark tells Excel the file is UTF-8
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )


def _csv_file(clinic: str, rows: list[Record]) -> Response:
    return csv_file(f"leads-{clinic}", EXPORT_COLUMNS, [
        [
            r["lead_code"], cell(r["full_name"]), export_phone(r["phone_e164"], r["phone_cc"]),
            cell(r["email"]), cell(r["treatment"]), SOURCE_LABEL.get(r["source"], r["source"]),
            cell(r["campaign"]), cell(r["doctor"]), r["stage"], cell(r["assigned"]), r["created"],
            r["contacted"],
        ]
        for r in rows
    ])  # fmt: skip


class ExportPicked(BaseModel):
    clinic: str = Field(pattern=CLINIC_CODE)
    codes: list[str] = Field(min_length=1, max_length=5000)


@router.post("/leads/export")
async def export_picked_leads(user: Annotated[Staff, Depends(staff)], body: ExportPicked) -> Response:
    """The leads ticked on the Leads screen, as a CSV (a lead of another clinic is never included)."""
    bulk_access(user, body.clinic)
    await perm.require(await get_pool(), user, body.clinic, "leads", "view")  # Who sees what
    rows = await (await get_pool()).fetch(
        f"""{EXPORT_SELECT} where l.clinic_id = $1 and l.deleted_at is null and l.lead_code = any($2::text[])
            {LEAD_ORDER}""",
        body.clinic, body.codes,
    )  # fmt: skip
    return _csv_file(body.clinic, rows)


@router.get("/leads/export")
async def export_leads(
    user: Annotated[Staff, Depends(staff)],
    clinic: Annotated[str, Query(pattern=CLINIC_CODE)],
    stage: Annotated[str | None, Query(pattern="^(new|follow_up|booked|visited|lost|invalid)$")] = None,
    source: Annotated[str | None, Query(pattern=SOURCE_FILTER)] = None,
    q: Annotated[str, Query(max_length=100)] = "",
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
    treatment: Annotated[str | None, Query(max_length=200)] = None,
    owner: Owner = "assigned",
    request: RequestFilter | None = None,
) -> Response:
    """Every lead matching the Leads filters (all pages), as a CSV for Excel."""
    bulk_access(user, clinic)
    await perm.require(await get_pool(), user, clinic, "leads", "view")  # Who sees what
    where, args = _lead_filter(clinic, source, q, date_from, date_to, treatment, owner, request)
    rows = await (await get_pool()).fetch(
        f"{EXPORT_SELECT} where {where} and ($7::text is null or l.stage = $7) {LEAD_ORDER}", *args, stage
    )
    return _csv_file(clinic, rows)


@router.get("/leads/{code}", response_model=LeadDetail)
async def lead_detail(user: Annotated[Staff, Depends(staff)], code: str) -> LeadDetail:
    """One lead with its timeline and latest chat. The clinic comes from the lead itself."""
    # A renamed clinic's old lead code (CL01-00003, from an older message or link) opens the lead.
    code = current_lead(code)
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
        if r is None or not in_clinic(user, r["clinic_id"]):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found.")
        await perm.require(await get_pool(), user, r["clinic_id"], "leads", "view")  # Who sees what
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


LOST = ["not_reachable", "not_interested", "price", "chose_another_clinic", "other"]
INVALID = ["wrong_number", "spam", "duplicate", "test", "booking_rejected"]


def can_edit(user: Staff, clinic: str) -> None:
    """Changes to leads: Super Admin, admin and front desk. Doctors only read."""
    can_see(user, clinic)
    if not user.bb_admin and user.roles.get(clinic) == "doctor":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Doctors can view leads but not change them.")


class StaffOption(BaseModel):
    id: str
    name: str
    role_label: str


@router.get("/staff", response_model=list[StaffOption])
async def staff_list(
    user: Annotated[Staff, Depends(staff)], clinic: Annotated[str, Query(pattern=CLINIC_CODE)]
) -> list[StaffOption]:
    """People a lead can be assigned to: active staff of the clinic, not doctors."""
    can_see(user, clinic)
    await perm.require(await get_pool(), user, clinic, "leads", "view")  # Who sees what
    pool = await get_pool()
    rows = await pool.fetch(
        """select p.id, p.full_name, u.role from app.user_clinics u join app.profiles p on p.id = u.user_id
           where u.clinic_id = $1 and u.active and p.active and u.role <> 'doctor' order by p.full_name""",
        clinic,
    )
    return [StaffOption(id=str(r[0]), name=r[1], role_label=ROLE_LABEL[r[2]]) for r in rows]


class LeadChange(BaseModel):
    stage: Literal["new", "follow_up", "booked", "visited", "lost", "invalid"] | None = None
    stage_reason: str | None = None  # needed for lost and invalid, from LOST / INVALID
    assigned_to: str | None = None  # a staff id, or "" to unassign
    # Details (Edit details): only the ones sent change; "" clears email, treatment, doctor or type.
    name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)  # the number without its country code
    phone_cc: str = Field(default="+91", pattern=r"^\+[1-9][0-9]{0,3}$")
    email: str | None = Field(default=None, max_length=200)
    treatment: str | None = Field(default=None, max_length=100)
    doctor_id: str | None = None
    type: Literal["in_clinic", "online", ""] | None = None


DETAILS = ("name", "phone", "email", "treatment", "doctor_id", "type")
DETAIL_LABEL = {
    "full_name": "Name", "phone_e164": "Phone", "email": "Email", "treatment": "Treatment",
    "doctor_id": "Doctor", "appointment_type": "Type",
}  # fmt: skip


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class CallIn(BaseModel):
    outcome: Literal["answered", "no_answer", "busy", "wrong_number"]
    text: str = Field(default="", max_length=2000)


async def _lead_for_edit(conn: Connection, user: Staff, code: str) -> Record:
    r = await conn.fetchrow(
        """select id, clinic_id, stage, assigned_to, full_name, phone_e164, phone_cc, email, treatment,
             doctor_id, appointment_type from app.leads where lead_code = $1 and deleted_at is null
           for update""",
        code,
    )
    if r is None or not in_clinic(user, r["clinic_id"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found.")
    can_edit(user, r["clinic_id"])
    await perm.require(await get_pool(), user, r["clinic_id"], "leads", "edit")  # Who sees what
    await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)  # audit: who did it
    return r


async def _event(
    conn: Connection, lead: Mapping[str, Any], user: Staff, kind: str, data: dict[str, object]
) -> None:
    await conn.execute(
        "insert into app.lead_events (clinic_id, lead_id, kind, data, actor)"
        " values ($1, $2, $3, $4::jsonb, $5::uuid)",
        lead["clinic_id"], lead["id"], kind, json.dumps(data), user.id,
    )  # fmt: skip


@router.patch("/leads/{code}", response_model=LeadDetail)
async def change_lead(user: Annotated[Staff, Depends(staff)], code: str, body: LeadChange) -> LeadDetail:
    """Change the stage (Lost and Invalid need a reason) or the owner. Each change goes on the timeline."""
    code = current_lead(code)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        lead = await _lead_for_edit(conn, user, code)
        if body.stage and body.stage != lead["stage"]:
            reasons = LOST if body.stage == "lost" else INVALID if body.stage == "invalid" else []
            if reasons and body.stage_reason not in reasons:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a reason for this stage.")
            reason = body.stage_reason if reasons else None
            await conn.execute(
                "update app.leads set stage = $2, stage_reason = $3, updated_at = now() where id = $1",
                lead["id"], body.stage, reason,
            )  # fmt: skip
            await _event(
                conn, lead, user, "stage_change", {"from": lead["stage"], "to": body.stage, "reason": reason}
            )
        if body.assigned_to is not None:
            to = body.assigned_to or None
            if to and not await conn.fetchval(
                """select 1 from app.user_clinics where user_id::text = $1 and clinic_id = $2 and active
                   and role <> 'doctor'""",
                to, lead["clinic_id"],
            ):  # fmt: skip
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "That person cannot take leads here."
                )
            if to != (str(lead["assigned_to"]) if lead["assigned_to"] else None):
                await conn.execute(
                    "update app.leads set assigned_to = $2::uuid, updated_at = now() where id = $1",
                    lead["id"],
                    to,
                )
                name = await conn.fetchval("select full_name from app.profiles where id::text = $1", to)
                await _event(conn, lead, user, "assigned", {"to": name or "Unassigned"})
        if body.model_fields_set & set(DETAILS):
            await _change_details(conn, lead, user, body)
    return await lead_detail(user, code)


async def _change_details(conn: Connection, lead: Record, user: Staff, body: LeadChange) -> None:
    """Edit details: what the first call corrected or added. Each change goes on the timeline (old -> new)."""
    sent = body.model_fields_set
    new: dict[str, Any] = {}
    if "name" in sent:
        name = " ".join((body.name or "").split())
        if not 2 <= len(name) <= 100:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter the patient's name.")
        new["full_name"] = name
    if "phone" in sent:
        phone = normal_phone(body.phone or "", body.phone_cc)
        if not phone:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter a valid mobile number.")
        cc, number = phone.split(" ", 1)
        other = await conn.fetchval(
            """select lead_code from app.leads where clinic_id = $1 and phone_e164 = $2 and deleted_at is null
                 and id <> $3""",
            lead["clinic_id"], cc + number, lead["id"],
        )  # fmt: skip
        if other:
            raise HTTPException(status.HTTP_409_CONFLICT, f"This number is already lead {other}.")
        new["phone_e164"], new["phone_cc"] = cc + number, cc
    if "email" in sent:
        email = (body.email or "").strip().lower() or None
        if email and not EMAIL.match(email):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter a valid email or leave it empty."
            )
        new["email"] = email
    if "treatment" in sent:
        new["treatment"] = " ".join((body.treatment or "").split()) or None
    if "doctor_id" in sent:
        doctor = body.doctor_id or None
        if doctor and not await conn.fetchval(
            "select 1 from app.doctors where id::text = $1 and clinic_id = $2 and active",
            doctor, lead["clinic_id"],
        ):  # fmt: skip
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose one of the clinic's doctors.")
        new["doctor_id"] = doctor
    if "type" in sent:
        new["appointment_type"] = body.type or None

    def text(v: Any) -> str | None:
        return None if v is None else str(v)

    changed = {k: v for k, v in new.items() if text(lead[k]) != text(v)}
    if not changed:
        return
    marks = ", ".join(
        f"{k} = ${i + 2}" + ("::uuid" if k == "doctor_id" else "") for i, k in enumerate(changed)
    )
    await conn.execute(
        f"update app.leads set {marks}, updated_at = now() where id = $1", lead["id"], *changed.values()
    )

    async def shown(k: str, v: Any) -> str:
        if v is None:
            return "—"
        if k == "doctor_id":
            return str(await conn.fetchval("select name from app.doctors where id::text = $1", str(v)) or "—")
        if k == "appointment_type":
            return "Online" if v == "online" else "In-clinic"
        return str(v)

    record = {
        DETAIL_LABEL[k]: [await shown(k, lead[k]), await shown(k, v)]
        for k, v in changed.items()
        if k in DETAIL_LABEL
    }
    # A timeline note (the kinds of events are fixed), with the before and after kept for the record.
    summary = "; ".join(f"{k}: {a} → {b}" for k, (a, b) in record.items())
    await _event(conn, lead, user, "note", {"text": f"Details changed: {summary}", "changes": record})


@router.post("/leads/{code}/notes", response_model=LeadDetail)
async def add_note(user: Annotated[Staff, Depends(staff)], code: str, body: NoteIn) -> LeadDetail:
    code = current_lead(code)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        lead = await _lead_for_edit(conn, user, code)
        await _event(conn, lead, user, "note", {"text": body.text.strip()})
    return await lead_detail(user, code)


@router.post("/leads/{code}/calls", response_model=LeadDetail)
async def log_call(user: Annotated[Staff, Depends(staff)], code: str, body: CallIn) -> LeadDetail:
    code = current_lead(code)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        lead = await _lead_for_edit(conn, user, code)
        await _event(conn, lead, user, "call", {"outcome": body.outcome, "text": body.text.strip()})
        await conn.execute("update app.leads set last_contact_at = now() where id = $1", lead["id"])
    return await lead_detail(user, code)


class Option(BaseModel):
    id: str
    name: str


class LeadOptions(BaseModel):
    treatments: list[str]
    doctors: list[Option]


@router.get("/lead-options", response_model=LeadOptions)
async def lead_options(
    user: Annotated[Staff, Depends(staff)], clinic: Annotated[str, Query(pattern=CLINIC_CODE)]
) -> LeadOptions:
    """Choices for the Add lead and Edit details forms and the booking forms: the clinic's treatments (as in
    the chatbot) and active doctors. Treatments: the clinic's content file where it has one, else what its
    published chat offers to book (Clinic info → Services: booking options, else the treatments listed)."""
    can_see(user, clinic)
    await perm.require(await get_pool(), user, clinic, "leads", "view")  # Who sees what
    c = content(clinic) or {}
    pool = await get_pool()
    rows = await pool.fetch(
        "select id, name from app.doctors where clinic_id = $1 and active order by sort_order, name", clinic
    )
    treatments = list(c.get("config", {}).get("treatments", []))
    if not treatments:
        raw = await pool.fetchval(
            "select published->'services' from app.clinic_settings where clinic_id = $1", clinic
        )
        services = json.loads(raw) if isinstance(raw, str) else (raw or {})
        offered = [o for o in services.get("booking_options") or [] if o not in ("Not sure yet", "Other")]
        listed = [i["name"] for i in services.get("items") or [] if i.get("show", True) and i.get("name")]
        treatments = list(dict.fromkeys(offered or listed))
    return LeadOptions(treatments=treatments, doctors=[Option(id=str(r[0]), name=r[1]) for r in rows])


class NewLead(BaseModel):
    clinic: str = Field(pattern=CLINIC_CODE)
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(max_length=20)  # 10-digit Indian mobile, or digits with phone_cc
    phone_cc: str = Field(default="+91", pattern=r"^\+[1-9][0-9]{0,3}$")
    email: str | None = Field(default=None, max_length=200)
    source: Literal["manual", "whatsapp", "meta_ads", "google_ads", "chatbot"] = "manual"
    campaign: str | None = Field(default=None, max_length=100)
    treatment: str | None = Field(default=None, max_length=100)
    doctor_id: str | None = None
    type: Literal["in_clinic", "online"] | None = None
    note: str = Field(default="", max_length=2000)


@router.post("/leads", response_model=LeadDetail, status_code=status.HTTP_201_CREATED)
async def add_lead(user: Annotated[Staff, Depends(staff)], body: NewLead) -> LeadDetail:
    """A lead added by staff (walk-in, call, WhatsApp). The same phone in the clinic is a duplicate:
    409 with the existing lead's code in the message, so staff open that one instead."""
    can_edit(user, body.clinic)
    phone = normal_phone(body.phone, body.phone_cc)
    if not phone:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter a valid mobile number.")
    email = (body.email or "").strip().lower() or None
    if email and not EMAIL.match(email):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter a valid email or leave it empty.")
    cc, number = phone.split(" ", 1)
    e164 = cc + number
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        existing = await conn.fetchval(
            "select lead_code from app.leads where clinic_id = $1 and phone_e164 = $2 and deleted_at is null",
            body.clinic, e164,
        )  # fmt: skip
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, f"This number is already lead {existing}.")
        r = await conn.fetchrow(
            """insert into app.leads (clinic_id, full_name, phone_e164, phone_cc, email, source, campaign,
                 treatment, doctor_id, appointment_type, assigned_to, notes)
               values ($1, $2, $3, $4, $5, $6, $7, $8, $9::uuid, $10,
                 (select user_id from app.user_clinics where user_id = $11::uuid and clinic_id = $1
                    and active and role <> 'doctor'), $12)
               returning id, clinic_id, lead_code""",
            body.clinic, " ".join(body.name.split()), e164, cc, email, body.source, body.campaign or None,
            body.treatment or None, body.doctor_id or None, body.type, user.id, body.note.strip(),
        )  # fmt: skip
        await _event(conn, r, user, "contact", {"source": body.source, "by_staff": True})
    webhooks.emit(r["clinic_id"], "lead_new", {
        "lead_code": r["lead_code"], "name": " ".join(body.name.split()), "phone": e164, "email": email,
        "treatment": body.treatment or None, "campaign": body.campaign or None, "source": body.source,
    })  # fmt: skip
    return await lead_detail(user, r["lead_code"])


class ImportRow(BaseModel):
    row: int = Field(ge=1)  # its line in the file, for the report
    name: str = Field(default="", max_length=500)
    phone: str = Field(default="", max_length=500)
    email: str = Field(default="", max_length=500)
    treatment: str = Field(default="", max_length=500)
    campaign: str = Field(default="", max_length=500)
    source: str = Field(default="", max_length=500)


class LeadImport(BaseModel):
    clinic: str = Field(pattern=CLINIC_CODE)
    rows: list[ImportRow] = Field(min_length=1, max_length=2000)
    confirm: bool = False  # False: only checks the rows and saves nothing


class ImportNote(BaseModel):
    row: int
    name: str
    reason: str


class LeadImportResult(BaseModel):
    ready: int  # new leads in the file
    added: int  # saved (0 until confirmed)
    duplicates: list[ImportNote]  # reason: the existing lead's code, or the line that has the same number
    invalid: list[ImportNote]


def _import_phone(text: str) -> str | None:
    """A number as a spreadsheet may hold it: +91 98765 43210, +919876543210, 919876543210, 09876543210, or
    another country's as "+971 501234567" (without the space its country code cannot be told)."""
    m = re.fullmatch(r"\s*(\+[1-9]\d{0,3})[\s-]+(.+)", text)
    if m:
        return normal_phone(m[2], m[1])
    digits = re.sub(r"[\s()\-]", "", text)
    digits = re.sub(r"^(\+91|91(?=\d{10}$)|0(?=\d{10}$))", "", digits)
    return normal_phone(digits, "+91")


@router.post("/leads/import", response_model=LeadImportResult)
async def import_leads(user: Annotated[Staff, Depends(staff)], body: LeadImport) -> LeadImportResult:
    """Leads from a CSV (the CRM reads the file and sends its rows). A number already in the clinic, or twice
    in the file, is skipped, and a row with a problem is reported; the others are saved only with `confirm`.
    Each lead saved then gets the lead_new webhook and the clinic's "Imported lead" WhatsApp template (when
    one is on), one after another in the background. Skipped numbers get nothing, so importing the same file
    again messages nobody twice."""
    bulk_access(user, body.clinic)
    await perm.require(await get_pool(), user, body.clinic, "leads", "edit")  # Who sees what
    invalid: list[ImportNote] = []
    duplicates: list[ImportNote] = []
    new: dict[str, tuple[ImportRow, str, str, str | None, str]] = {}  # by phone
    for r in body.rows:
        name = " ".join(r.name.split())
        email = r.email.strip().lower() or None
        phone = _import_phone(r.phone)
        reason = (
            "Name is missing or too short." if not 2 <= len(name) <= 100
            else "Phone is not a valid mobile number." if not phone
            else "Email is not valid." if email and (len(email) > 200 or not EMAIL.match(email))
            else "Treatment is too long." if len(r.treatment.strip()) > 100
            else "Campaign is too long." if len(r.campaign.strip()) > 100
            else ""
        )  # fmt: skip
        if reason or not phone:
            invalid.append(ImportNote(row=r.row, name=name[:100], reason=reason))
            continue
        cc, number = phone.split(" ", 1)
        e164 = cc + number
        if e164 in new:
            duplicates.append(
                ImportNote(row=r.row, name=name, reason=f"same number as line {new[e164][0].row}")
            )
            continue
        new[e164] = (r, name, cc, email, r.source.strip().lower().replace(" ", "_"))
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        known = await conn.fetch(
            """select phone_e164, lead_code from app.leads
               where clinic_id = $1 and deleted_at is null and phone_e164 = any($2::text[])""",
            body.clinic, list(new),
        )  # fmt: skip
        for k in known:
            r, name, *_ = new.pop(k["phone_e164"])
            duplicates.append(ImportNote(row=r.row, name=name, reason=k["lead_code"]))
        saved: list[Record] = []
        if body.confirm and new:
            items = list(new.items())
            saved = await conn.fetch(
                """insert into app.leads (clinic_id, full_name, phone_e164, phone_cc, email, source, campaign,
                     treatment)
                   select $1, n, p, c, e, s, nullif(g, ''), nullif(t, '')
                   from unnest($2::text[], $3::text[], $4::text[], $5::text[], $6::text[], $7::text[],
                     $8::text[])
                     as x(n, p, c, e, s, g, t)
                   on conflict do nothing
                   returning id, lead_code, full_name, phone_e164, phone_cc, email, source, campaign,
                     treatment""",
                body.clinic,
                [v[1] for _, v in items],
                [e164 for e164, _ in items],
                [v[2] for _, v in items],
                [v[3] for _, v in items],
                [v[4] if v[4] in SOURCE_LABEL else "manual" for _, v in items],
                [v[0].campaign.strip() for _, v in items],
                [v[0].treatment.strip() for _, v in items],
            )
            await conn.execute(
                """insert into app.lead_events (clinic_id, lead_id, kind, data, actor)
                   select $1, id, 'contact', '{"by_staff": true, "imported": true}'::jsonb, $3::uuid
                   from unnest($2::uuid[]) as x(id)""",
                body.clinic, [r["id"] for r in saved], user.id,
            )  # fmt: skip
    if saved:  # after the save, so nobody hears about a lead that was not kept
        webhooks.emit_each(body.clinic, "lead_new", [
            {"lead_code": r["lead_code"], "name": r["full_name"], "phone": r["phone_e164"],
             "email": r["email"], "treatment": r["treatment"], "campaign": r["campaign"],
             "source": r["source"]}
            for r in saved
        ])  # fmt: skip
        whatsapp.notify_each(body.clinic, "imported_lead", [
            (export_phone(r["phone_e164"], r["phone_cc"]),
             {"lead_code": r["lead_code"], "name": r["full_name"], "treatment": r["treatment"]})
            for r in saved
        ])  # fmt: skip
    return LeadImportResult(ready=len(new), added=len(saved), duplicates=duplicates, invalid=invalid)
