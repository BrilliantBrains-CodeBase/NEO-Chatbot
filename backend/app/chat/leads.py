"""Saving a finished flow: lead, request, appointment, task, timeline, questions, email and the chat link.

Runs inside the chat turn's transaction, so either everything is saved or nothing is.
"""

import json
from datetime import date, datetime, time
from typing import Any
from uuid import UUID

import asyncpg

from app.chat import understand
from app.chat.schemas import ChatRequest

Flow = dict[str, Any]


class SlotTaken(Exception):
    """Every doctor's time at the chosen slot was taken a moment ago."""


async def _clinic(conn: asyncpg.Connection, clinic_id: str) -> asyncpg.Record:
    row: asyncpg.Record = await conn.fetchrow(
        "select id, timezone, slot_minutes, lead_assignment from app.clinics where id = $1", clinic_id
    )
    return row


async def _assignee(conn: asyncpg.Connection, clinic: asyncpg.Record) -> UUID | None:
    """Who gets a new lead, per the clinic's setting. Round robin: the front desk member whose last lead is
    the oldest (locked, so two leads at once go to two people)."""
    if clinic["lead_assignment"] == "manual":
        return None
    if clinic["lead_assignment"] == "manager":
        uid: UUID | None = await conn.fetchval(
            """select uc.user_id from app.user_clinics uc join app.profiles p on p.id = uc.user_id
               where uc.clinic_id = $1 and uc.role = 'clinic_manager' and uc.active and p.active
               order by uc.created_at limit 1""",
            clinic["id"],
        )
        return uid
    row = await conn.fetchrow(
        """select uc.user_id from app.user_clinics uc join app.profiles p on p.id = uc.user_id and p.active
           where uc.clinic_id = $1 and uc.role = 'front_desk' and uc.active and uc.in_round_robin
           order by uc.rr_last_assigned_at nulls first, uc.created_at limit 1
           for update of uc""",
        clinic["id"],
    )
    if row is None:
        return None
    await conn.execute(
        "update app.user_clinics set rr_last_assigned_at = now() where user_id = $1 and clinic_id = $2",
        row["user_id"],
        clinic["id"],
    )
    found: UUID = row["user_id"]
    return found


async def _lead(
    conn: asyncpg.Connection, req: ChatRequest, f: Flow, clinic: asyncpg.Record
) -> tuple[UUID, bool]:
    """One lead per phone per clinic: a repeat contact counts up; otherwise a new lead (code from the DB)."""
    cc, number = f["phone"].split(" ", 1)
    phone = cc + number
    # Two chats with the same number at once wait for each other instead of both inserting.
    await conn.execute("select pg_advisory_xact_lock(hashtext($1 || $2))", req.client_id, phone)
    existing = await conn.fetchrow(
        """select id from app.leads
           where clinic_id = $1 and phone_e164 = $2 and deleted_at is null for update""",
        req.client_id,
        phone,
    )
    if existing:
        await conn.execute(
            """update app.leads set contact_count = contact_count + 1, last_contact_at = now(),
                 email = coalesce(email, $2), treatment = coalesce($3, treatment)
               where id = $1""",
            existing["id"],
            f.get("email"),
            f.get("treatment"),
        )
        found: UUID = existing["id"]
        return found, False
    booking = f["kind"] in ("book", "online")
    new_id: UUID = await conn.fetchval(
        """insert into app.leads (clinic_id, full_name, phone_e164, phone_cc, email, source, treatment,
             appointment_type, page_url, device, consent_at, assigned_to)
           values ($1, $2, $3, $4, $5, 'chatbot', $6, $7, $8, $9, $10, $11) returning id""",
        req.client_id,
        f["name"],
        phone,
        cc,
        f.get("email"),
        f.get("treatment"),
        ("online" if f["kind"] == "online" else "in_clinic") if booking else None,
        req.context.page_url,
        req.context.device,
        datetime.now().astimezone() if booking else None,
        await _assignee(conn, clinic),
    )
    return new_id, True


async def _book(conn: asyncpg.Connection, f: Flow, clinic: asyncpg.Record, lead: UUID, request: UUID) -> UUID:
    """A pending appointment. With an exact time, a free doctor is chosen and the database's double-booking
    rule makes the final check; "Any time" keeps the day only and staff choose the slot."""
    mode = "online" if f["kind"] == "online" else "in_clinic"
    day = date.fromisoformat(f["date"])
    if f["time"] == "any":
        appt: UUID = await conn.fetchval(
            """insert into app.appointments (clinic_id, lead_id, request_id, type, preferred_date)
               values ($1, $2, $3, $4, $5) returning id""",
            clinic["id"], lead, request, mode, day,
        )  # fmt: skip
        return appt
    start = time.fromisoformat(f["time"])
    doctors = await conn.fetch(
        """select distinct da.doctor_id from app.doctor_availability da
           join app.doctors d on d.id = da.doctor_id and d.active
           where da.clinic_id = $1 and da.mode = $2 and da.weekday = $3
             and da.start_time <= $4 and da.end_time >= $4 + make_interval(mins => $5)
             and not exists (select 1 from app.doctor_leave l
                             where l.doctor_id = da.doctor_id and $6 between l.from_date and l.to_date)""",
        clinic["id"], mode, (day.weekday() + 1) % 7, start, clinic["slot_minutes"], day,
    )  # fmt: skip
    for d in doctors:
        try:
            async with conn.transaction():  # a savepoint: a taken slot does not undo the rest
                taken: UUID = await conn.fetchval(
                    """insert into app.appointments (clinic_id, lead_id, request_id, doctor_id, type, slot)
                       values ($1, $2, $3, $4, $5, tstzrange(($6::date + $7::time) at time zone $8,
                               ($6::date + $7::time + make_interval(mins => $9)) at time zone $8, '[)'))
                       returning id""",
                    clinic["id"], lead, request, d["doctor_id"], mode, day, start, clinic["timezone"],
                    clinic["slot_minutes"],
                )  # fmt: skip
                return taken
        except asyncpg.exceptions.ExclusionViolationError:
            continue
    raise SlotTaken


async def save_completed(conn: asyncpg.Connection, req: ChatRequest, f: Flow) -> str:
    """Saves a finished flow. Returns the lead code. Raises SlotTaken (nothing of the booking is kept then,
    because the caller's transaction is rolled back)."""
    clinic = await _clinic(conn, req.client_id)
    lead, new = await _lead(conn, req, f, clinic)
    kind = f["kind"]
    match, matched = None, None
    if kind in ("cancel", "reschedule"):
        matched = await conn.fetchval(
            """select a.id from app.appointments a join app.clinics c on c.id = a.clinic_id
               where a.lead_id = $1 and a.status in ('pending', 'confirmed')
                 and coalesce((lower(a.slot) at time zone c.timezone)::date, a.preferred_date) = $2
               order by a.created_at desc limit 1""",
            lead,
            date.fromisoformat(f["booked_date"]),
        )
        match = "matched" if matched else "no_match"
    data = {
        k: f.get(k) for k in ("name", "phone", "email", "treatment", "reason", "date", "time", "booked_date")
    }
    request: UUID = await conn.fetchval(
        """insert into app.requests (clinic_id, lead_id, type, data, match_status, matched_appointment_id,
             question_text, session_id)
           values ($1, $2, $3, $4::jsonb, $5, $6, $7, $8) returning id""",
        req.client_id, lead, kind, json.dumps({k: v for k, v in data.items() if v}), match, matched,
        f.get("reason") if kind == "question" else None, req.session_id,
    )  # fmt: skip
    appointment = await _book(conn, f, clinic, lead, request) if kind in ("book", "online") else None

    owner = await conn.fetchval("select assigned_to from app.leads where id = $1", lead)
    await conn.execute(
        """insert into app.tasks (clinic_id, lead_id, appointment_id, type, title, due_at, assigned_to)
           values ($1, $2, $3, $4, $5, now() + interval '30 minutes', $6)""",
        req.client_id, lead, appointment, "confirm_booking" if appointment else "call_new_lead",
        f"{kind.capitalize()} request from the chatbot", owner,
    )  # fmt: skip
    events = [
        ("contact", {"source": "chatbot", "new": new}),
        ("request", {"type": kind, "request_id": str(request)}),
    ]
    if appointment:
        events.append(("appointment", {"appointment_id": str(appointment), "status": "pending"}))
    for ev_kind, ev in events:
        await conn.execute(
            "insert into app.lead_events (clinic_id, lead_id, kind, data) values ($1, $2, $3, $4::jsonb)",
            req.client_id, lead, ev_kind, json.dumps(ev),
        )  # fmt: skip

    questions = list(f.get("questions", [])) + (
        [f["reason"]] if kind == "question" and f.get("reason") else []
    )
    for q in questions:
        await conn.execute(
            """insert into app.unanswered_questions (clinic_id, question_text, reason, lead_id, session_id)
               values ($1, $2, $3, $4, $5)""",
            req.client_id, q[:1000], "medical" if understand.MEDICAL.search(q.lower()) else "no_match", lead,
            req.session_id,
        )  # fmt: skip

    if f.get("email"):
        payload = {"to": f["email"], "name": f["name"], "kind": kind, "treatment": f.get("treatment"),
                   "date": f.get("date"), "time": f.get("time")}  # fmt: skip
        await conn.execute(
            """insert into app.outbox (clinic_id, channel, kind, lead_id, appointment_id, payload, dedupe_key)
               values ($1, 'email', 'request_received', $2, $3, $4::jsonb, $5)
               on conflict (dedupe_key) do nothing""",
            req.client_id, lead, appointment, json.dumps(payload), f"request_received:{request}",
        )  # fmt: skip
    await conn.execute(
        "update app.chat_sessions set lead_id = $2 where id = $1 and clinic_id = $3",
        req.session_id, lead, req.client_id,
    )  # fmt: skip
    code: str = await conn.fetchval("select lead_code from app.leads where id = $1", lead)
    return code
