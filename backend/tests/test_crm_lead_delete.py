"""Deleting and restoring leads: Clinic Managers and Super Admin only. Real database, test clinics only (the
access tests' world, removed after)."""

from typing import Any

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_crm_access import world  # noqa: F401  (the fixture)
from tests.test_crm_auth import api, needs_db, signed_in_as  # noqa: F401

pytestmark = needs_db


async def test_only_a_manager_or_super_admin_deletes_and_restores_a_lead(
    api: AsyncClient,  # noqa: F811
    world: dict[str, Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = await get_pool()
    code = world["lead"]["lead_code"]
    body = {"clinic": "CL99", "codes": [code]}

    for who in ("desk", "doctor"):  # never Front Desk or a doctor, whatever "Who sees what" says
        h = signed_in_as(monkeypatch, world[who]["id"])
        assert (await api.post("/v1/crm/leads/delete", json=body, headers=h)).status_code == 403, who
        assert (await api.get("/v1/crm/deleted-leads?clinic=CL99", headers=h)).status_code == 403, who
    other = signed_in_as(monkeypatch, world["manager"]["id"])
    theirs = {"clinic": "CL98", "codes": [world["other_lead"]["lead_code"]]}
    assert (await api.post("/v1/crm/leads/delete", json=theirs, headers=other)).status_code == 403

    lead_id = world["lead"]["id"]
    task = await pool.fetchval(  # an open task (e.g. "Online request from the chatbot") is closed too
        """insert into app.tasks (clinic_id, lead_id, type, title, due_at)
           values ('CL99', $1, 'confirm_booking', 'Online request from the chatbot', now()) returning id""",
        lead_id,
    )
    h = signed_in_as(monkeypatch, world["manager"]["id"])
    r = await api.post("/v1/crm/leads/delete", json=body, headers=h)
    assert r.status_code == 200 and r.json() == {"done": [code], "problems": []}
    assert await pool.fetchval("select status from app.tasks where id = $1", task) == "cancelled"
    assert await pool.fetchval("select deleted_at is not null from app.leads where id = $1", lead_id)
    statuses = await pool.fetch("select status from app.appointments where lead_id = $1", lead_id)
    assert {s["status"] for s in statuses} == {"cancelled"}  # the doctor's time is free again
    listed = (await api.get("/v1/crm/leads?clinic=CL99&owner=all", headers=h)).json()
    assert code not in [i["code"] for i in listed["items"]]  # hidden from the Leads screen
    deleted = (await api.get("/v1/crm/deleted-leads?clinic=CL99", headers=h)).json()
    assert [d["code"] for d in deleted][:1] == [code] and deleted[0]["removed_on"]

    again = await api.post("/v1/crm/leads/delete", json=body, headers=h)
    assert again.json()["problems"] == [f"{code}: not found (already deleted?)"]

    bb = signed_in_as(monkeypatch, world["bb"]["id"])
    back = await api.post("/v1/crm/leads/restore", json=body, headers=bb)
    assert back.json() == {"done": [code], "problems": []}
    assert await pool.fetchval("select deleted_at is null from app.leads where id = $1", lead_id)


async def test_the_night_job_removes_leads_deleted_over_30_days_ago_only() -> None:
    """Inside a transaction that is rolled back: a lead deleted 31 days ago goes for good, with its
    appointment; one deleted 5 days ago can still be restored. Needs migration 0043."""
    import asyncpg

    from app.core.config import get_settings

    conn = await asyncpg.connect(get_settings().database_url, statement_cache_size=0)
    if not await conn.fetchval("select to_regprocedure('app.job_purge_deleted_leads()') is not null"):
        await conn.close()
        pytest.skip("migration 0043 is not applied to this database yet")
    tr = conn.transaction()
    await tr.start()
    try:
        add = """insert into app.leads (clinic_id, full_name, phone_e164, source, deleted_at)
                 values ('CL99', $1, $2, 'manual', now() - $3::interval) returning id"""
        old = await conn.fetchval(add, "ZzPurge Old", "+919000007301", "31 days")
        recent = await conn.fetchval(add, "ZzPurge Recent", "+919000007302", "5 days")
        await conn.execute(
            """insert into app.appointments (clinic_id, lead_id, type, status, preferred_date)
               values ('CL99', $1, 'in_clinic', 'cancelled', current_date)""",
            old,
        )
        assert await conn.fetchval("select app.job_purge_deleted_leads()") >= 1
        assert await conn.fetchval("select count(*) from app.leads where id = $1", old) == 0
        assert await conn.fetchval("select count(*) from app.appointments where lead_id = $1", old) == 0
        assert await conn.fetchval("select count(*) from app.leads where id = $1", recent) == 1
    finally:
        await tr.rollback()
        await conn.close()


async def test_a_patient_with_an_owner_and_a_waiting_cancel_is_in_the_inbox(
    api: AsyncClient,  # noqa: F811
    world: dict[str, Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Inbox shows every waiting request, an existing patient's cancel too (with its owner)."""
    pool = await get_pool()
    lead_id, code = world["lead"]["id"], world["lead"]["lead_code"]
    manager = world["manager"]["id"]
    await pool.execute("update app.leads set assigned_to = $2::uuid where id = $1", lead_id, manager)
    h = signed_in_as(monkeypatch, manager)

    def listed(d: dict[str, Any]) -> list[str]:
        return [i["code"] for i in d["items"]]

    inbox = (await api.get("/v1/crm/inbox?clinic=CL99", headers=h)).json()
    assert code not in listed(inbox)  # an owner and nothing waiting: in Leads only
    request = await pool.fetchval(
        """insert into app.requests (clinic_id, lead_id, type, data)
           values ('CL99', $1, 'cancel', '{"booked_date": "2026-11-02"}') returning id""",
        lead_id,
    )
    try:
        inbox = (await api.get("/v1/crm/inbox?clinic=CL99", headers=h)).json()
        row = next(i for i in inbox["items"] if i["code"] == code)
        assert row["assigned"] and [r["type"] for r in row["requests"]] == ["cancel"]
        cancels = (await api.get("/v1/crm/inbox?clinic=CL99&type=cancel", headers=h)).json()
        assert code in listed(cancels)  # under Cancellations too
        await pool.execute("update app.requests set status = 'done' where id = $1", request)
        inbox = (await api.get("/v1/crm/inbox?clinic=CL99", headers=h)).json()
        assert code not in listed(inbox)  # handled: it leaves the Inbox
    finally:
        await pool.execute("delete from app.requests where id = $1", request)
