"""Who sees what: built-in defaults, a clinic's own rules (only differences stored), BB defaults, and the
checks on access given for a time. Leaves the rules as it found them."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture


@needs_db
async def test_rules_stack_and_grants_are_checked(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    before = await pool.fetchval("select permissions from app.platform where id = 1")
    url = "/v1/crm/permissions/CL99"
    try:
        r = (await api.get(url, headers=headers)).json()
        assert (
            r["effective"]["front_desk"]["settings"] == "hidden"
            and r["effective"]["doctor"]["dash_open"] == "hidden"
        )
        table = r["effective"]
        table["front_desk"]["reports"] = "hidden"
        table["doctor"]["dash_open"] = "view"  # Doctors may open the Dashboard in this clinic
        r = (await api.put(url, json={"rules": table}, headers=headers)).json()
        assert r["own"] == {
            "front_desk": {"reports": "hidden"},
            "doctor": {"dash_open": "view"},
        }  # only changes
        r = (await api.put(url, json={"rules": {}}, headers=headers)).json()  # "Use the defaults"
        assert r["own"] == {} and r["effective"]["front_desk"]["reports"] == "view"
        defaults = r["defaults"]
        defaults["front_desk"]["patients"] = "view"
        r = (
            await api.put("/v1/crm/permissions/defaults/CL99", json={"rules": defaults}, headers=headers)
        ).json()
        assert r["effective"]["front_desk"]["patients"] == "view"  # every clinic follows the new default
        soon = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        far = (datetime.now(UTC) + timedelta(days=120)).isoformat()
        g = {"user_id": str(admin), "screen": "reports", "level": "edit", "until": soon}
        assert (await api.post(f"{url}/grants", json=g | {"until": far}, headers=headers)).status_code == 422
        assert (
            await api.post(f"{url}/grants", json=g | {"screen": "nope"}, headers=headers)
        ).status_code == 422
        stranger = g | {"user_id": "00000000-0000-0000-0000-000000000000"}
        assert (await api.post(f"{url}/grants", json=stranger, headers=headers)).status_code == 404
    finally:
        await pool.execute("update app.platform set permissions = $1 where id = 1", before or "{}")
        await pool.execute("delete from app.clinic_permissions where clinic_id = 'CL99'")
        await pool.execute("delete from app.access_grants where clinic_id = 'CL99'")
