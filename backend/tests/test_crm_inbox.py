"""CRM Inbox: list, approve, reject and done, on a temporary lead in the test clinic (CL99)."""

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture


@needs_db
async def test_inbox_approve_reject_and_done(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    lead = await pool.fetchval(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Inbox Test', '+919000000003', 'chatbot') returning id"""
    )
    try:
        ids = {}
        for kind in ("book", "callback", "online"):
            ids[kind] = str(
                await pool.fetchval(
                    """insert into app.requests (clinic_id, lead_id, type, data)
                       values ('CL99', $1, $2, '{"date": "2026-11-02", "time": "any"}')
                       returning id""",
                    lead,
                    kind,
                )
            )
        await pool.execute(
            """insert into app.appointments (clinic_id, lead_id, request_id, type, preferred_date)
               values ('CL99', $1, $2::uuid, 'in_clinic', '2026-11-02')""",
            lead,
            ids["book"],
        )
        r = await api.get("/v1/crm/inbox?clinic=CL99", headers=headers)
        assert r.status_code == 200
        pending = {c["key"]: c["count"] for c in r.json()["pending"]}
        assert pending["book"] >= 1 and pending["callback"] >= 1
        mine = [i for i in r.json()["items"] if i["id"] in ids.values()]
        assert {i["type"] for i in mine} == {"book", "callback", "online"}

        r = await api.post(f"/v1/crm/requests/{ids['book']}/approve", headers=headers)
        assert r.status_code == 200 and r.json()["status"] == "done"
        assert r.json()["appointment"]["status"] == "confirmed"
        assert await pool.fetchval("select stage from app.leads where id = $1", lead) == "booked"
        again = await api.post(f"/v1/crm/requests/{ids['book']}/approve", headers=headers)
        assert again.status_code == 409  # already handled

        wrong = await api.post(f"/v1/crm/requests/{ids['callback']}/approve", headers=headers)
        assert wrong.status_code == 422
        r = await api.post(
            f"/v1/crm/requests/{ids['callback']}/done", json={"outcome": "answered"}, headers=headers
        )
        assert r.json()["status"] == "done"
        r = await api.post(
            f"/v1/crm/requests/{ids['online']}/reject", json={"reason": "No slots"}, headers=headers
        )
        assert r.json()["status"] == "rejected"
        kinds = [k for (k,) in await pool.fetch("select kind from app.lead_events where lead_id = $1", lead)]
        assert kinds.count("request") == 3 and "call" in kinds
    finally:
        await pool.execute("select app.delete_patient_data($1)", lead)
