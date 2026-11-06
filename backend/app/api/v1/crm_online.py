"""Dashboard → Integrations → Cal.com → Set up online consults, JSON only.

Which doctors take online consults through Cal.com, and the clinic's holidays (app.clinic_holidays). The
doctors' online hours, leave and online length are set in Dashboard → Doctors (app.api.v1.crm_doctors); the
chatbot's online slots come from the same tables. Saving here sends each doctor to the clinic's Cal.com: a
schedule (the hours, with holidays and leave blocked) and an event (the consult, Google Meet).
"""

import re
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.db import get_pool
from app.crm import calcom, vault
from app.crm import permissions as perm
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm/console", tags=["crm"])
HM = r"^([01]\d|2[0-3]):[0-5]\d$"


class Hours(BaseModel):
    weekday: int = Field(ge=0, le=6)  # 0 = Sunday
    start: str = Field(pattern=HM)
    end: str = Field(pattern=HM)

    @model_validator(mode="after")
    def _order(self) -> "Hours":
        if self.start >= self.end:
            raise ValueError(f"{self.start} to {self.end}: the end must be after the start.")
        return self


class Leave(BaseModel):
    from_date: date
    to_date: date
    reason: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def _order(self) -> "Leave":
        if self.from_date > self.to_date:
            raise ValueError("A leave must end on or after its first day.")
        return self


class DoctorSetup(BaseModel):
    doctor_id: str
    name: str = ""  # shown only
    online: bool = False
    consult_minutes: int = 30
    hours: list[Hours] = Field(default=[], max_length=50)
    leave: list[Leave] = Field(default=[], max_length=100)

    @field_validator("consult_minutes")
    @classmethod
    def _minutes(cls, v: int) -> int:
        if v not in (5, 10, 15, 20, 30, 45, 60):
            raise ValueError("A consult is 5, 10, 15, 20, 30, 45 or 60 minutes.")
        return v


class Holiday(BaseModel):
    day: date
    reason: str = Field(default="", max_length=200)


class Setup(BaseModel):
    doctors: list[DoctorSetup] = Field(default=[], max_length=50)
    holidays: list[Holiday] = Field(default=[], max_length=200)
    problems: list[str] = []  # from Cal.com, after a save


def _manager(user: Staff, clinic: str) -> None:
    if not (user.bb_admin or user.roles.get(clinic) == "clinic_manager" or perm.granted(user, clinic)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Integrations are for admins and Super Admin.")


async def _setup(clinic: str, problems: list[str] | None = None) -> Setup:
    pool = await get_pool()
    # The consult length is the doctor's online length (Dashboard → Doctors), else the clinic's.
    docs = await pool.fetch(
        """select d.id, d.name, c.event_type_id is not null online,
                  coalesce(d.online_minutes, cl.online_slot_minutes) minutes
           from app.doctors d join app.clinics cl on cl.id = d.clinic_id
           left join app.calcom_doctors c on c.doctor_id = d.id
           where d.clinic_id = $1 and d.active order by d.sort_order, d.name""",
        clinic,
    )
    hours = await pool.fetch(
        """select doctor_id, weekday, to_char(start_time, 'HH24:MI') s, to_char(end_time, 'HH24:MI') e
           from app.doctor_availability where clinic_id = $1 and mode = 'online'
           order by weekday, start_time""",
        clinic,
    )
    leave = await pool.fetch(
        """select doctor_id, from_date, to_date, reason from app.doctor_leave
           where clinic_id = $1 and to_date >= current_date order by from_date""",
        clinic,
    )
    holidays = await pool.fetch(
        "select day, reason from app.clinic_holidays where clinic_id = $1 and day >= current_date "
        "order by day",
        clinic,
    )
    return Setup(
        doctors=[
            DoctorSetup(
                doctor_id=str(d["id"]), name=d["name"], online=d["online"], consult_minutes=d["minutes"],
                hours=[Hours(weekday=h["weekday"], start=h["s"], end=h["e"]) for h in hours
                       if h["doctor_id"] == d["id"]],
                leave=[Leave(from_date=x["from_date"], to_date=x["to_date"], reason=x["reason"])
                       for x in leave if x["doctor_id"] == d["id"]],
            )
            for d in docs
        ],
        holidays=[Holiday(day=h["day"], reason=h["reason"]) for h in holidays],
        problems=problems or [],
    )  # fmt: skip


@router.get("/{clinic}/integrations/calcom/setup", response_model=Setup)
async def get_setup(user: Annotated[Staff, Depends(staff)], clinic: str) -> Setup:
    _manager(user, clinic)
    return await _setup(clinic)


@router.put("/{clinic}/integrations/calcom/setup", response_model=Setup)
async def save_setup(user: Annotated[Staff, Depends(staff)], clinic: str, body: Setup) -> Setup:
    """Saves the clinic's holidays and which doctors take online consults, then sends every doctor to Cal.com
    with their CURRENT online hours, leave and length from Dashboard → Doctors (this screen does not edit
    those, so the two screens never overwrite each other)."""
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn:
        account = await conn.fetchrow(
            "select key_secret from app.calcom_accounts where clinic_id = $1", clinic
        )
        if account is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Connect the clinic's Cal.com first.")
        key = await vault.read(conn, account["key_secret"])
        known = {
            str(r["id"]) for r in await conn.fetch("select id from app.doctors where clinic_id = $1", clinic)
        }
    if not key:
        raise HTTPException(status.HTTP_409_CONFLICT, "The Cal.com key is missing. Please connect again.")
    online = {d.doctor_id for d in body.doctors if d.online}
    if online - known:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "A doctor was not found in this clinic.")
    current = await _setup(clinic)
    for d in current.doctors:
        if d.doctor_id in online and not d.hours:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Add {d.name}'s online hours in Chatbot → Doctors first.",
            )
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        await conn.execute(
            "delete from app.clinic_holidays where clinic_id = $1 and day >= current_date", clinic
        )
        for h in body.holidays:
            await conn.execute(
                """insert into app.clinic_holidays (clinic_id, day, reason) values ($1, $2, $3)
                   on conflict (clinic_id, day) do update set reason = $3""",
                clinic, h.day, h.reason,
            )  # fmt: skip
    # The doctors as saved in Dashboard → Doctors, with this screen's online choice.
    send = Setup(
        doctors=[d.model_copy(update={"online": d.doctor_id in online}) for d in current.doctors],
        holidays=body.holidays,
    )
    problems = await sync(clinic, key, send)
    return await _setup(clinic, problems)


def _blocked(holidays: list[Holiday], leave: list[Leave]) -> list[str]:
    """The days no online consult can be booked (the next year): clinic holidays and the doctor's leave."""
    today, last = date.today(), date.today() + timedelta(days=365)
    days = {h.day for h in holidays if today <= h.day <= last}
    for x in leave:
        d = max(x.from_date, today)
        while d <= min(x.to_date, last):
            days.add(d)
            d += timedelta(days=1)
    return sorted(day.isoformat() for day in days)


async def sync(clinic: str, key: str, body: Setup) -> list[str]:
    """Sends each doctor to Cal.com: online ones get a schedule and an event (created or updated), the others
    are removed from Cal.com. Returns problems (one per doctor that Cal.com refused)."""
    pool = await get_pool()
    problems: list[str] = []
    for d in body.doctors:
        row: Any = await pool.fetchrow(
            "select event_type_id, schedule_id from app.calcom_doctors "
            "where clinic_id = $1 and doctor_id = $2::uuid",
            clinic, d.doctor_id,
        )  # fmt: skip
        if not d.online:
            if row:
                await calcom.remove_doctor(key, row["event_type_id"], row["schedule_id"])
                await pool.execute("delete from app.calcom_doctors where doctor_id = $1::uuid", d.doctor_id)
            continue
        name = d.name or "Doctor"
        slug = re.sub(r"[^a-z0-9]+", "-", f"online consult {name} {d.doctor_id[:6]}".lower()).strip("-")
        try:
            schedule = await calcom.save_schedule(
                key, row["schedule_id"] if row else None, f"{name} · online consults",
                [(h.weekday, h.start, h.end) for h in d.hours], _blocked(body.holidays, d.leave),
            )  # fmt: skip
            event = await calcom.save_event(
                key, row["event_type_id"] if row else None, f"Online consult with {name}", slug,
                d.consult_minutes, schedule,
            )  # fmt: skip
        except calcom.CalcomError as e:
            problems.append(f"{name}: {e}")
            continue
        await pool.execute(
            """insert into app.calcom_doctors (clinic_id, doctor_id, event_type_id, event_title, schedule_id,
                 consult_minutes, synced_at) values ($1, $2::uuid, $3, $4, $5, $6, now())
               on conflict (clinic_id, doctor_id) do update set event_type_id = $3, event_title = $4,
                 schedule_id = $5, consult_minutes = $6, synced_at = now()""",
            clinic, d.doctor_id, event, f"Online consult with {name}", schedule, d.consult_minutes,
        )  # fmt: skip
        # The doctor's online length (Dashboard → Doctors) is the Cal.com event's length.
        await pool.execute(
            "update app.doctors set online_minutes = $2 where id = $1::uuid", d.doctor_id, d.consult_minutes
        )
    return problems
