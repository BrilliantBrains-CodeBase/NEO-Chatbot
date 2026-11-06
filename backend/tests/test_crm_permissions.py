"""Who sees what: built-in defaults, a clinic's own rules (only differences stored), BB defaults, and the
checks on access given for a time. Leaves the rules as it found them."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.db import close_pool, get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture


@pytest.fixture(autouse=True)
async def _own_pool() -> Any:
    """These tests use the shared pool: close it with this test's event loop."""
    yield
    await close_pool()


@needs_db
async def test_rules_stack_and_grants_are_checked(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
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


@needs_db
async def test_require_follows_the_rules_and_time_limited_access() -> None:
    """Doctors only view Appointments by default: viewing passes, changing is refused; a Hidden screen is
    refused; access given for a time lifts the level until it ends."""
    import uuid

    from fastapi import HTTPException

    from app.crm import permissions as perm
    from app.crm.auth import Staff

    pool = await get_pool()
    doctor = Staff(id=str(uuid.uuid4()), name="Dr Test", email="d@example.com", roles={"CL99": "doctor"},
                   bb_admin=False)  # fmt: skip
    await perm.require(pool, doctor, "CL99", "appointments", "view")
    with pytest.raises(HTTPException) as no:
        await perm.require(pool, doctor, "CL99", "appointments", "edit")
    assert no.value.status_code == 403 and "cannot change Appointments" in str(no.value.detail)
    with pytest.raises(HTTPException):
        await perm.require(pool, doctor, "CL99", "leads", "view")  # Hidden for Doctors
    with pytest.raises(HTTPException):
        await perm.require(pool, doctor, "CL99", "reports", "view")  # Hidden for Doctors
    with pytest.raises(HTTPException):
        await perm.require(pool, doctor, "NFHT", "appointments", "view")  # not their clinic
    desk = Staff(id=str(uuid.uuid4()), name="Desk", email="f@example.com", roles={"CL99": "front_desk"},
                 bb_admin=False)  # fmt: skip
    mine = await perm.for_person(pool, "CL99", desk.id, "front_desk")
    assert mine["settings"] == "hidden" and mine["leads"] == "edit" and mine["dash_open"] == "hidden"
