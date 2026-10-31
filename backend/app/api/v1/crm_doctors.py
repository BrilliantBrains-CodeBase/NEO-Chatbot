"""Dashboard → Doctors: a clinic's doctors with all their settings in one place: profile, slot lengths
(in-clinic and online, each the clinic default or their own), weekly in-clinic and online hours and leave.

Rules (user, 2026-10-31): 5 and 10 minute slots are allowed; a doctor's in-clinic and online hours never
overlap (checked on save, so a doctor is never offered twice for the same time). A doctor connected to Cal.com
gets their online hours, leave and online length sent there after a save (as Integrations → Online does).
"""

import json
from datetime import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.v1 import crm_online
from app.api.v1.crm_online import Holiday, Hours, Leave
from app.core.db import get_pool
from app.crm import vault
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm/console", tags=["crm"])

LENGTHS = (5, 10, 15, 20, 30, 45, 60)
DAYS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")


def _length(v: int | None) -> int | None:
    if v is not None and v not in LENGTHS:
        raise ValueError("A slot is 5, 10, 15, 20, 30, 45 or 60 minutes.")
    return v


class Figure(BaseModel):
    label: str = Field(min_length=1, max_length=40)  # e.g. Years experience
    value: str = Field(min_length=1, max_length=20)  # e.g. 20+


class Doctor(BaseModel):
    id: str = ""  # empty when adding
    name: str = Field(min_length=2, max_length=100)
    role_title: str = Field(default="Doctor", min_length=2, max_length=100)
    qualifications: str = Field(default="", max_length=300)
    photo: str = Field(default="", max_length=300, pattern=r"^(https://\S+)?$")
    about: str = Field(default="", max_length=1000)
    stats: list[Figure] = Field(default=[], max_length=6)
    active: bool = True
    in_clinic_minutes: int | None = None  # None: the clinic's in-clinic length
    online_minutes: int | None = None  # None: the clinic's online length
    in_clinic: list[Hours] = Field(default=[], max_length=50)
    online: list[Hours] = Field(default=[], max_length=50)
    leave: list[Leave] = Field(default=[], max_length=100)
    calcom: bool = False  # shown only: connected to Cal.com (Integrations → Online)

    _len = field_validator("in_clinic_minutes", "online_minutes")(_length)


class DoctorIn(Doctor):
    """A doctor as saved: the hours must not overlap. (Reading uses Doctor, so hours saved before this rule
    still show and can be fixed.)"""

    @model_validator(mode="after")
    def _no_overlap(self) -> "DoctorIn":
        """In-clinic and online hours (and two rows of the same kind) never overlap on a weekday."""
        rows = [("in-clinic", h) for h in self.in_clinic] + [("online", h) for h in self.online]
        for i, (k1, a) in enumerate(rows):
            for k2, b in rows[i + 1 :]:
                if a.weekday == b.weekday and a.start < b.end and b.start < a.end:
                    raise ValueError(
                        f"{DAYS[a.weekday]}: {k1} {a.start}–{a.end} overlaps {k2} {b.start}–{b.end}. "
                        "A doctor cannot be in the clinic and online at the same time."
                    )
        return self


class Defaults(BaseModel):
    slot_minutes: int  # the clinic's in-clinic length
    online_slot_minutes: int

    _len = field_validator("slot_minutes", "online_slot_minutes")(_length)


class Doctors(BaseModel):
    defaults: Defaults
    doctors: list[Doctor]
    problems: list[str] = []  # from Cal.com, after a save


def _manager(user: Staff, clinic: str) -> None:
    from app.crm import permissions as perm

    if not (user.bb_admin or user.roles.get(clinic) == "clinic_manager" or perm.granted(user, clinic)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Doctors are managed by clinic managers and BB Admin.")


def _profile(raw: Any) -> dict[str, Any]:
    return raw if isinstance(raw, dict) else json.loads(raw or "{}")


async def _list(clinic: str, problems: list[str] | None = None) -> Doctors:
    pool = await get_pool()
    c = await pool.fetchrow("select slot_minutes, online_slot_minutes from app.clinics where id = $1", clinic)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinic not found.")
    docs = await pool.fetch(
        """select d.id, d.name, d.role_title, d.qualifications, d.profile, d.active, d.in_clinic_minutes,
                  d.online_minutes, c.event_type_id is not null calcom
           from app.doctors d left join app.calcom_doctors c on c.doctor_id = d.id
           where d.clinic_id = $1 order by d.active desc, d.sort_order, d.name""",
        clinic,
    )
    hours = await pool.fetch(
        """select doctor_id, mode, weekday, to_char(start_time, 'HH24:MI') s, to_char(end_time, 'HH24:MI') e
           from app.doctor_availability where clinic_id = $1 order by weekday, start_time""",
        clinic,
    )
    leave = await pool.fetch(
        """select doctor_id, from_date, to_date, reason from app.doctor_leave
           where clinic_id = $1 and to_date >= current_date order by from_date""",
        clinic,
    )

    def hrs(doctor: Any, mode: str) -> list[Hours]:
        return [
            Hours(weekday=h["weekday"], start=h["s"], end=h["e"])
            for h in hours
            if h["doctor_id"] == doctor and h["mode"] == mode
        ]

    out = []
    for d in docs:
        p = _profile(d["profile"])
        out.append(
            Doctor(
                id=str(d["id"]), name=d["name"], role_title=d["role_title"],
                qualifications=d["qualifications"], photo=p.get("photo", ""), about=p.get("about", ""),
                stats=[Figure(**s) for s in p.get("stats", []) if s.get("label") and s.get("value")][:6],
                active=d["active"], in_clinic_minutes=d["in_clinic_minutes"],
                online_minutes=d["online_minutes"], in_clinic=hrs(d["id"], "in_clinic"),
                online=hrs(d["id"], "online"),
                leave=[Leave(from_date=x["from_date"], to_date=x["to_date"], reason=x["reason"])
                       for x in leave if x["doctor_id"] == d["id"]],
                calcom=d["calcom"],
            )
        )  # fmt: skip
    return Doctors(
        defaults=Defaults(slot_minutes=c["slot_minutes"], online_slot_minutes=c["online_slot_minutes"]),
        doctors=out,
        problems=problems or [],
    )


async def _save(conn: Any, clinic: str, doctor_id: str, body: Doctor) -> None:
    """Writes the doctor's hours and upcoming leave (all replaced by what was sent)."""
    await conn.execute("delete from app.doctor_availability where doctor_id = $1::uuid", doctor_id)
    for mode, rows in (("in_clinic", body.in_clinic), ("online", body.online)):
        for h in rows:
            await conn.execute(
                """insert into app.doctor_availability
                     (doctor_id, clinic_id, weekday, mode, start_time, end_time)
                   values ($1::uuid, $2, $3, $4, $5, $6)""",
                doctor_id, clinic, h.weekday, mode, time.fromisoformat(h.start), time.fromisoformat(h.end),
            )  # fmt: skip
    await conn.execute(
        "delete from app.doctor_leave where doctor_id = $1::uuid and to_date >= current_date", doctor_id
    )
    for x in body.leave:
        await conn.execute(
            """insert into app.doctor_leave (doctor_id, clinic_id, from_date, to_date, reason)
               values ($1::uuid, $2, $3, $4, $5)""",
            doctor_id, clinic, x.from_date, x.to_date, x.reason,
        )  # fmt: skip


async def _calcom(clinic: str, doctor_id: str) -> list[str]:
    """Sends a Cal.com-connected doctor's online hours, leave and length to Cal.com. Returns problems."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        linked = await conn.fetchval("select 1 from app.calcom_doctors where doctor_id = $1::uuid", doctor_id)
        account = await conn.fetchrow(
            "select key_secret from app.calcom_accounts where clinic_id = $1", clinic
        )
        key = await vault.read(conn, account["key_secret"]) if linked and account else None
    if not linked:
        return []
    if not key:
        return ["Cal.com was not updated: connect the clinic's Cal.com again (Integrations)."]
    data = await _list(clinic)
    d = next(x for x in data.doctors if x.id == doctor_id)
    if not d.online:
        return [f"{d.name}: Cal.com was not updated because there are no online hours."]
    setup = crm_online.Setup(
        doctors=[
            crm_online.DoctorSetup(
                doctor_id=d.id, name=d.name, online=True, hours=d.online, leave=d.leave,
                consult_minutes=d.online_minutes or data.defaults.online_slot_minutes,
            )
        ],
        holidays=[Holiday(day=h["day"], reason=h["reason"]) for h in await pool.fetch(
            "select day, reason from app.clinic_holidays where clinic_id = $1 and day >= current_date", clinic
        )],
    )  # fmt: skip
    return await crm_online.sync(clinic, key, setup)


@router.get("/{clinic}/doctors", response_model=Doctors)
async def list_doctors(user: Annotated[Staff, Depends(staff)], clinic: str) -> Doctors:
    _manager(user, clinic)
    return await _list(clinic)


@router.post("/{clinic}/doctors", response_model=Doctors)
async def add_doctor(user: Annotated[Staff, Depends(staff)], clinic: str, body: DoctorIn) -> Doctors:
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        doctor_id = await conn.fetchval(
            """insert into app.doctors (clinic_id, name, role_title, qualifications, profile, active,
                 in_clinic_minutes, online_minutes, sort_order)
               values ($1, $2, $3, $4, $5::jsonb, $6, $7, $8,
                 (select coalesce(max(sort_order), 0) + 1 from app.doctors where clinic_id = $1))
               returning id::text""",
            clinic, body.name.strip(), body.role_title.strip(), body.qualifications.strip(),
            json.dumps({"photo": body.photo, "about": body.about.strip(),
                        "stats": [s.model_dump() for s in body.stats]}),
            body.active, body.in_clinic_minutes, body.online_minutes,
        )  # fmt: skip
        await _save(conn, clinic, doctor_id, body)
    return await _list(clinic)


@router.put("/{clinic}/doctors/{doctor_id}", response_model=Doctors)
async def save_doctor(
    user: Annotated[Staff, Depends(staff)], clinic: str, doctor_id: str, body: DoctorIn
) -> Doctors:
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        old = await conn.fetchval(
            "select profile from app.doctors where id::text = $1 and clinic_id = $2", doctor_id, clinic
        )
        if old is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found in this clinic.")
        # Other profile keys (e.g. the full-profile link) are kept.
        profile = {**_profile(old), "photo": body.photo, "about": body.about.strip(),
                   "stats": [s.model_dump() for s in body.stats]}  # fmt: skip
        await conn.execute(
            """update app.doctors set name = $3, role_title = $4, qualifications = $5, profile = $6::jsonb,
                 active = $7, in_clinic_minutes = $8, online_minutes = $9
               where id = $1::uuid and clinic_id = $2""",
            doctor_id, clinic, body.name.strip(), body.role_title.strip(), body.qualifications.strip(),
            json.dumps(profile), body.active, body.in_clinic_minutes, body.online_minutes,
        )  # fmt: skip
        await _save(conn, clinic, doctor_id, body)
    return await _list(clinic, await _calcom(clinic, doctor_id))


@router.put("/{clinic}/doctors-defaults", response_model=Doctors)
async def save_defaults(user: Annotated[Staff, Depends(staff)], clinic: str, body: Defaults) -> Doctors:
    """The clinic's slot lengths, used by every doctor without their own."""
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        await conn.execute(
            "update app.clinics set slot_minutes = $2, online_slot_minutes = $3 where id = $1",
            clinic, body.slot_minutes, body.online_slot_minutes,
        )  # fmt: skip
    return await _list(clinic)
