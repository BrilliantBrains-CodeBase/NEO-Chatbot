"""Deleting leads (user, 2026-11-11): Clinic Managers and Super Admin only, whatever "Who sees what" says.
A deleted lead is hidden from every screen at once (app.leads.deleted_at) and can be restored for 30 days,
then a nightly job removes it for good. Deleting cancels the lead's upcoming appointments (an online
consult's Cal.com booking too) so the doctor's time is free again, and closes its open Inbox requests and
tasks; past visits stay in its history. Every change is in the audit log with who made it.
"""

import logging
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.v1.crm import can_see
from app.api.v1.crm_inbox import account
from app.core.codes import CLINIC_CODE, current_lead
from app.core.db import get_pool
from app.crm import calcom
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm", tags=["crm"])
log = logging.getLogger(__name__)
KEEP_DAYS = 30  # restorable this long; the nightly job removes it after


class Codes(BaseModel):
    clinic: str = Field(pattern=CLINIC_CODE)
    codes: list[str] = Field(min_length=1, max_length=200)


class Done(BaseModel):
    done: list[str]  # lead codes changed
    problems: list[str]  # one line per lead that could not be changed, and why


class Deleted(BaseModel):
    code: str
    name: str
    phone: str | None
    stage: str
    deleted_at: str
    removed_on: str  # the day it is removed for good


def managers_only(user: Staff, clinic: str) -> None:
    """Delete and restore: a Clinic Manager of this clinic, or Super Admin. Never Front Desk or a doctor."""
    can_see(user, clinic)
    if not user.bb_admin and user.roles.get(clinic) != "clinic_manager":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a clinic manager can delete or restore leads.")


async def _as(conn: asyncpg.Connection, user: Staff) -> None:
    await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)  # audit: who did it


@router.post("/leads/delete", response_model=Done)
async def delete_leads(user: Annotated[Staff, Depends(staff)], body: Codes) -> Done:
    """Hides the leads (restorable for 30 days), cancels their upcoming appointments and closes their open
    requests and tasks."""
    managers_only(user, body.clinic)
    codes = sorted({current_lead(c) for c in body.codes})
    pool = await get_pool()
    calendar: list[tuple[str, object]] = []  # (Cal.com booking, doctor)
    async with pool.acquire() as conn, conn.transaction():
        await _as(conn, user)
        leads = await conn.fetch(
            """select id, lead_code from app.leads
               where clinic_id = $1 and lead_code = any($2::text[]) and deleted_at is null for update""",
            body.clinic, codes,
        )  # fmt: skip
        ids = [r["id"] for r in leads]
        cancelled = await conn.fetch(
            """update app.appointments a set status = 'cancelled', updated_at = now()
               from app.clinics c
               where c.id = a.clinic_id and a.lead_id = any($1::uuid[])
                 and a.status in ('pending', 'confirmed')
                 and coalesce(lower(a.slot), a.preferred_date::timestamp at time zone c.timezone)
                     >= date_trunc('day', now() at time zone c.timezone) at time zone c.timezone
               returning a.calendar_event_id, a.doctor_id""",
            ids,
        )  # fmt: skip
        calendar = [(r[0], r[1]) for r in cancelled if r[0]]
        await conn.execute(
            """update app.requests set status = 'rejected'
               where lead_id = any($1::uuid[]) and status = 'pending'""",
            ids,
        )
        await conn.execute(
            """update app.tasks set status = 'cancelled', completed_at = now()
               where lead_id = any($1::uuid[]) and status = 'open'""",
            ids,
        )
        await conn.execute(
            "update app.leads set deleted_at = now(), updated_at = now() where id = any($1::uuid[])", ids
        )
    for uid, doctor in calendar:  # after the save: Cal.com refusing never keeps a lead the manager deleted
        try:
            async with pool.acquire() as conn:
                acc = await account(conn, body.clinic, doctor)  # the clinic's own Cal.com, as when booked
            await calcom.cancel(uid, "Cancelled by the clinic", acc)
        except Exception:  # noqa: BLE001 (the lead is deleted; a Cal.com problem is only logged)
            log.warning("Cal.com booking %s could not be cancelled after a lead was deleted", uid)
    found = {r["lead_code"] for r in leads}
    return Done(
        done=sorted(found), problems=[f"{c}: not found (already deleted?)" for c in codes if c not in found]
    )


@router.get("/deleted-leads", response_model=list[Deleted])
async def deleted_leads(
    user: Annotated[Staff, Depends(staff)], clinic: Annotated[str, Query(pattern=CLINIC_CODE)]
) -> list[Deleted]:
    """The leads deleted in the last 30 days, newest first: what can still be restored."""
    managers_only(user, clinic)
    rows = await (await get_pool()).fetch(
        f"""select lead_code, full_name, phone_e164, stage, deleted_at,
              (deleted_at + interval '{KEEP_DAYS} days')::date removed_on
            from app.leads where clinic_id = $1 and deleted_at > now() - interval '{KEEP_DAYS} days'
            order by deleted_at desc limit 500""",
        clinic,
    )
    return [
        Deleted(code=r["lead_code"], name=r["full_name"], phone=r["phone_e164"], stage=r["stage"],
                deleted_at=r["deleted_at"].isoformat(), removed_on=r["removed_on"].isoformat())
        for r in rows
    ]  # fmt: skip


@router.post("/leads/restore", response_model=Done)
async def restore_leads(user: Annotated[Staff, Depends(staff)], body: Codes) -> Done:
    """Brings deleted leads back as they were (their cancelled appointments stay cancelled). A lead whose
    phone now belongs to a newer lead cannot come back: that newer lead is the person's record."""
    managers_only(user, body.clinic)
    codes = sorted({current_lead(c) for c in body.codes})
    done: list[str] = []
    problems: list[str] = []
    pool = await get_pool()
    async with pool.acquire() as conn:
        for code in codes:
            async with conn.transaction():
                await _as(conn, user)
                row = await conn.fetchrow(
                    """select id from app.leads where clinic_id = $1 and lead_code = $2
                         and deleted_at > now() - interval '30 days' for update""",
                    body.clinic, code,
                )  # fmt: skip
                if row is None:
                    problems.append(f"{code}: not in Recently deleted")
                    continue
                try:
                    async with (
                        conn.transaction()
                    ):  # a savepoint: the phone rule refusing undoes this one only
                        await conn.execute(
                            "update app.leads set deleted_at = null, updated_at = now() where id = $1",
                            row["id"],
                        )
                except asyncpg.UniqueViolationError:
                    problems.append(f"{code}: its phone or email now belongs to another lead")
                    continue
                done.append(code)
    return Done(done=done, problems=problems)
