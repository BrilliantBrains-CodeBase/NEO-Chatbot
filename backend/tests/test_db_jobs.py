"""Scheduled jobs (migration 0009): each job function on old and new data, and the schedules.

Rolled back after each test; data in CL99. Timestamps are set in the past instead of waiting.
Skipped when DATABASE_URL is not set.
"""

import asyncpg
import pytest

from app.core.config import get_settings
from tests.test_db_audit import new_lead

pytestmark = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")


async def test_jobs_are_scheduled(tx: asyncpg.Connection) -> None:
    jobs = {r["jobname"]: r["schedule"] for r in await tx.fetch("select jobname, schedule from cron.job")}
    assert jobs["neo_delete_old_chat"] == "30 21 * * *"  # 03:00 India time
    assert jobs["neo_mark_missed"] == "*/15 * * * *"
    assert jobs["neo_unlink_unanswered"] == "45 21 * * *"
    assert jobs["neo_clear_outbox"] == "0 22 * * *"


async def test_chat_older_than_3_days_is_deleted_and_recent_chat_kept(tx: asyncpg.Connection) -> None:
    for sid, days in (("s_" + "1" * 32, 4), ("s_" + "2" * 32, 2)):
        await tx.execute(
            """insert into app.chat_sessions (id, clinic_id, visitor_id, started_at, last_at)
               values ($1, 'CL99', $2,
                       now() - make_interval(days => $3), now() - make_interval(days => $3))""",
            sid,
            "v_" + "0" * 32,
            days,
        )
        await tx.execute(
            """insert into app.chat_messages (session_id, clinic_id, role, text, event, created_at)
               values ($1, 'CL99', 'patient', 'Hi', 'text', now() - make_interval(days => $2))""",
            sid,
            days,
        )
    await tx.fetchval("select app.job_delete_old_chat()")
    left = {r["id"] for r in await tx.fetch("select id from app.chat_sessions where clinic_id = 'CL99'")}
    assert left == {"s_" + "2" * 32}
    assert await tx.fetchval("select count(*) from app.chat_messages where clinic_id = 'CL99'") == 1


async def test_passed_pending_bookings_become_missed(tx: asyncpg.Connection) -> None:
    lead = await new_lead(tx)
    sql = """insert into app.appointments
               (clinic_id, lead_id, type, slot, preferred_date, status, confirmed_at)
             values ('CL99', $1, 'in_clinic', $2::text::tstzrange, $3::text::date, $4, $5::text::timestamptz)
             returning id"""
    past = await tx.fetchval(sql, lead, "[2020-01-01 10:00+00,2020-01-01 10:15+00)", None, "pending", None)
    future = await tx.fetchval(sql, lead, "[2099-01-01 10:00+00,2099-01-01 10:15+00)", None, "pending", None)
    any_time_past = await tx.fetchval(sql, lead, None, "2020-01-01", "pending", None)
    confirmed_past = await tx.fetchval(
        sql, lead, "[2020-01-02 10:00+00,2020-01-02 10:15+00)", None, "confirmed", "2020-01-01 00:00+00"
    )
    await tx.fetchval("select app.job_mark_missed()")
    status = {
        r["id"]: r["status"]
        for r in await tx.fetch("select id, status from app.appointments where lead_id = $1", lead)
    }
    assert status[past] == "missed"
    assert status[any_time_past] == "missed"
    assert status[future] == "pending"
    assert status[confirmed_past] == "confirmed"  # only pending ones are marked


async def test_old_unanswered_questions_are_unlinked(tx: asyncpg.Connection) -> None:
    lead = await new_lead(tx)
    sql = """insert into app.unanswered_questions (clinic_id, question_text, reason, lead_id, created_at)
             values ('CL99', 'Q', 'no_match', $1, now() - make_interval(days => $2)) returning id"""
    old, recent = await tx.fetchval(sql, lead, 91), await tx.fetchval(sql, lead, 10)
    await tx.fetchval("select app.job_unlink_unanswered()")
    links = {
        r["id"]: r["lead_id"]
        for r in await tx.fetch("select id, lead_id from app.unanswered_questions where clinic_id = 'CL99'")
    }
    assert links[old] is None
    assert links[recent] == lead


async def test_old_sent_messages_are_cleared_failed_kept(tx: asyncpg.Connection) -> None:
    sql = """insert into app.outbox (clinic_id, channel, kind, status, sent_at, last_error)
             values ('CL99', 'email', 'reminder_24h', $1, $2::text::timestamptz, $3) returning id"""
    sent = await tx.fetchval(sql, "sent", "2020-01-01 00:00+00", None)
    failed = await tx.fetchval(sql, "failed", None, "timeout")
    await tx.execute("alter table app.outbox disable trigger outbox_touch")
    await tx.execute(
        "update app.outbox set updated_at = now() - interval '31 days' where id in ($1, $2)", sent, failed
    )
    await tx.execute("alter table app.outbox enable trigger outbox_touch")
    await tx.fetchval("select app.job_clear_outbox()")
    left = {r["id"] for r in await tx.fetch("select id from app.outbox where clinic_id = 'CL99'")}
    assert left == {failed}
