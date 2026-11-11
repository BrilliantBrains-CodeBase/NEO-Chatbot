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

    h = signed_in_as(monkeypatch, world["manager"]["id"])
    r = await api.post("/v1/crm/leads/delete", json=body, headers=h)
    assert r.status_code == 200 and r.json() == {"done": [code], "problems": []}
    lead_id = world["lead"]["id"]
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
