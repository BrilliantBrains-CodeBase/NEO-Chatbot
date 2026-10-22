"""Saving a finished flow (B6): lead, request, appointment, task, timeline, questions, email, chat link.
Real database, rolled back after each test, test clinic CL99."""

from typing import Any
from uuid import UUID

import asyncpg
import pytest

from app.chat import engine, leads, store
from app.chat.slots import free_slots_range
from app.core.config import get_settings
from tests.test_chat_slots import FAR, MON, booked, doctor
from tests.test_chat_store import SID, req
from tests.test_db_access import person

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")

PHONE = "+91 9800000001"  # the same number test_chat_slots.booked() uses


def flow(kind: str = "book", **extra: Any) -> dict[str, Any]:
    f = {"kind": kind, "name": "Asha Rao", "phone": PHONE, "email": "asha@example.com"}
    if kind in ("book", "online"):
        f |= {"treatment": "Hair Transplant", "date": MON.isoformat(), "time": "10:15"}
    return f | extra


async def save(db: asyncpg.Connection, f: dict[str, Any]) -> str:
    await store.open_session(db, req())
    return await leads.save_completed(db, req(), f)


async def test_a_booking_saves_everything(tx: asyncpg.Connection) -> None:
    doc = await doctor(tx, "10:00", "12:00")
    code = await save(tx, flow(questions=["Is it painful?"]))
    assert code.startswith("CL99-")
    lead = await tx.fetchrow("select * from app.leads where lead_code = $1", code)
    assert (lead["phone_e164"], lead["phone_cc"], lead["source"]) == ("+919800000001", "+91", "chatbot")
    assert lead["appointment_type"] == "in_clinic" and lead["consent_at"] is not None
    appt = await tx.fetchrow("select * from app.appointments where lead_id = $1", lead["id"])
    assert appt["status"] == "pending" and appt["doctor_id"] == doc
    assert appt["slot"].lower.isoformat() == "2026-10-26T04:45:00+00:00"  # 10:15 India time
    req_row = await tx.fetchrow("select type, data from app.requests where lead_id = $1", lead["id"])
    assert req_row["type"] == "book"
    task = await tx.fetchrow("select type, appointment_id from app.tasks where lead_id = $1", lead["id"])
    assert task["type"] == "confirm_booking" and task["appointment_id"] == appt["id"]
    kinds = await tx.fetch("select kind from app.lead_events where lead_id = $1 order by id", lead["id"])
    assert [k["kind"] for k in kinds] == ["contact", "request", "appointment"]
    q = await tx.fetchrow(
        "select question_text, reason from app.unanswered_questions where lead_id = $1", lead["id"]
    )
    assert q["question_text"] == "Is it painful?"
    mail = await tx.fetchrow(
        "select channel, kind, appointment_id from app.outbox where lead_id = $1", lead["id"]
    )
    assert tuple(mail) == ("email", "request_received", appt["id"])
    assert await tx.fetchval("select lead_id from app.chat_sessions where id = $1", SID) == lead["id"]


async def test_a_repeat_contact_is_the_same_lead(tx: asyncpg.Connection) -> None:
    first = await save(tx, flow("callback"))
    again = await save(tx, flow("question", reason="Do you have parking?"))
    assert first == again
    lead = await tx.fetchrow("select id, contact_count from app.leads where lead_code = $1", first)
    assert lead["contact_count"] == 2
    tasks = await tx.fetch("select type from app.tasks where lead_id = $1", lead["id"])
    assert [t["type"] for t in tasks] == ["call_new_lead", "call_new_lead"]
    assert await tx.fetchval("select count(*) from app.appointments where lead_id = $1", lead["id"]) == 0


async def test_a_taken_time_goes_to_a_free_doctor_or_fails(tx: asyncpg.Connection) -> None:
    first = await doctor(tx, "10:00", "12:00")
    await booked(tx, first, "10:15")  # another patient took 10:15 with the only doctor
    with pytest.raises(leads.SlotTaken):
        await save(tx, flow(phone="+91 9800000002"))
    await doctor(tx, "10:00", "12:00")
    await save(tx, flow(phone="+91 9800000003"))  # a second doctor is free


async def test_any_time_keeps_the_day_only(tx: asyncpg.Connection) -> None:
    code = await save(tx, flow("online", time="any"))
    appt = await tx.fetchrow(
        "select a.type, a.slot, a.preferred_date, a.doctor_id from app.appointments a "
        "join app.leads l on l.id = a.lead_id where l.lead_code = $1",
        code,
    )
    assert (appt["type"], appt["slot"], appt["preferred_date"], appt["doctor_id"]) == (
        "online",
        None,
        MON,
        None,
    )


async def test_cancel_is_matched_to_the_booking(tx: asyncpg.Connection) -> None:
    await save(tx, flow(time="any"))
    await save(tx, flow("cancel", booked_date=MON.isoformat()))
    await save(tx, flow("reschedule", booked_date="2026-10-28", date="2026-10-30", time="11:00"))
    rows = await tx.fetch(
        "select type, match_status, matched_appointment_id is not null as linked from app.requests "
        "where clinic_id = 'CL99' and type in ('cancel', 'reschedule') order by created_at, type"
    )
    assert [tuple(r) for r in rows] == [("cancel", "matched", True), ("reschedule", "no_match", False)]


async def test_new_leads_take_turns_in_the_front_desk(tx: asyncpg.Connection) -> None:
    a: UUID = await person(tx, "ria", "CL99", "front_desk")
    b: UUID = await person(tx, "sam", "CL99", "front_desk")
    await tx.execute("update app.user_clinics set in_round_robin = true where user_id = any($1)", [a, b])
    await tx.execute("update app.user_clinics set in_round_robin = false where clinic_id = 'CL99' "
                     "and user_id <> all($1)", [a, b])  # fmt: skip
    owners = []
    for n in ("1", "2", "3"):
        code = await save(tx, flow("callback", phone=f"+91 980000001{n}"))
        owners.append(await tx.fetchval("select assigned_to from app.leads where lead_code = $1", code))
    assert set(owners[:2]) == {a, b} and owners[2] == owners[0]


async def test_manual_assignment_leaves_the_lead_open(tx: asyncpg.Connection) -> None:
    await tx.execute("update app.clinics set lead_assignment = 'manual' where id = 'CL99'")
    code = await save(tx, flow("callback"))
    assert await tx.fetchval("select assigned_to from app.leads where lead_code = $1", code) is None


def test_confirm_hands_the_finished_flow_to_the_service() -> None:
    f = flow() | {"step": "summary"}
    turn = engine.respond(req("button", clinic="CL01", action="confirm"), {"flow": f})
    assert turn.completed is not None and turn.completed["kind"] == "book" and "flow" not in turn.state
    assert engine.respond(req("button", clinic="CL01", action="menu"), {"flow": f}).completed is None


def test_a_taken_slot_asks_for_the_time_again() -> None:
    f = flow() | {"step": "summary"}
    turn = engine.slot_taken(req(clinic="CL01"), f, {MON.isoformat(): ["11:00"]})
    assert turn.reply.messages[0].text == engine.SLOT_TAKEN
    assert turn.state["flow"]["step"] == "time" and turn.state["flow"]["time"] is None
    assert engine.slot_taken(req(clinic="CL01"), f, {}).state["flow"]["step"] == "date"


OTHER = "s_" + "a" * 32


async def test_a_held_time_is_hidden_from_others_and_kept_for_its_patient(tx: asyncpg.Connection) -> None:
    await doctor(tx, "10:00", "12:00")
    f = flow() | {"step": "summary"}
    assert await leads.hold_slot(tx, req(), f)
    day = MON.isoformat()
    mine = await free_slots_range(tx, "CL99", MON, MON, "in_clinic", FAR, 0, SID)
    others = await free_slots_range(tx, "CL99", MON, MON, "in_clinic", FAR, 0, OTHER)
    assert "10:15" in mine[day] and "10:15" not in others[day]
    other = req().model_copy(update={"session_id": OTHER})
    assert not await leads.hold_slot(tx, other, f)  # the only doctor is held
    with pytest.raises(leads.SlotTaken):
        await leads.save_completed(tx, other, f | {"phone": "+91 9800000002"})
    await save(tx, f)  # the patient who holds it can book it, and the hold is released
    assert await tx.fetchval("select count(*) from app.slot_holds where session_id = $1", SID) == 0


async def test_an_expired_hold_frees_the_time(tx: asyncpg.Connection) -> None:
    await doctor(tx, "10:00", "12:00")
    assert await leads.hold_slot(tx, req(), flow())
    await tx.execute("update app.slot_holds set created_at = now() - interval '1 hour', "
                     "expires_at = now() - interval '1 minute'")  # fmt: skip
    other = req().model_copy(update={"session_id": OTHER})
    assert await leads.hold_slot(tx, other, flow())
