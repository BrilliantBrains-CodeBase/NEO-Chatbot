"""The CRM home (Dashboard): this period next to the one before, the day-by-day series, appointment outcomes,
today's schedule and the month calendar. Test clinic CL99 (tests.test_crm_access.world)."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_crm_access import world
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api", "world"]  # the fixtures

pytestmark = needs_db


async def test_the_dashboard_compares_with_the_period_before(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    pool = await get_pool()
    headers = signed_in_as(monkeypatch, world["bb"]["id"])
    was = (await api.get("/v1/crm/dashboard?clinic=CL99&days=7", headers=headers)).json()
    phone = f"+9196{uuid.uuid4().int % 10**8:08d}"
    old = await pool.fetchval(  # a lead from 9 days ago: in the period before, not this one
        """insert into app.leads (clinic_id, full_name, phone_e164, source, stage, created_at)
           values ('CL99', 'Earlier Patient', $1, 'manual', 'booked', now() - interval '9 days')
           returning id""",
        phone,
    )
    try:
        r = await api.get("/v1/crm/dashboard?clinic=CL99&days=7", headers=headers)
        assert r.status_code == 200
        d = r.json()
        assert len(d["series"]) == 7 and d["series"][0]["day"] == d["start"]
        assert d["before"]["leads"] == was["before"]["leads"] + 1
        assert d["before"]["converted"] == was["before"]["converted"] + 1
        assert d["now"]["leads"] == was["now"]["leads"] == d["new_leads"]
        assert sum(s["leads"] for s in d["series"]) == d["now"]["leads"]
        assert sum(s["leads_before"] for s in d["series"]) == d["before"]["leads"]
        # world's lead and its two appointments, made today
        assert d["series"][-1]["leads"] >= 1 and d["now"]["bookings"] >= 2
        assert any(o["key"] == "pending" and o["count"] >= 2 for o in d["outcomes"])
        mine = [t for t in d["today"] if t["lead_code"] == world["lead"]["lead_code"]]
        assert len(mine) == 2 and all(t["end"] and t["doctor_id"] for t in mine)
        assert {t["doctor_id"] for t in mine} == {world["my_record"], world["other_record"]}
    finally:
        await pool.execute("delete from app.leads where id = $1", old)


async def test_the_month_calendar(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    headers = signed_in_as(monkeypatch, world["bb"]["id"])
    r = await api.get("/v1/crm/dashboard/calendar?clinic=CL99", headers=headers)
    assert r.status_code == 200
    m = r.json()
    assert m["month"] == m["today"][:7]
    days = {c["key"]: c["count"] for c in m["days"]}
    assert days.get(m["today"], 0) >= 2  # world's two appointments
    r = await api.get("/v1/crm/dashboard/calendar?clinic=CL99&month=2020-02", headers=headers)
    assert r.status_code == 200 and r.json() == {"month": "2020-02", "today": m["today"], "days": []}
    bad = await api.get("/v1/crm/dashboard/calendar?clinic=CL99&month=2020-13", headers=headers)
    assert bad.status_code == 422
