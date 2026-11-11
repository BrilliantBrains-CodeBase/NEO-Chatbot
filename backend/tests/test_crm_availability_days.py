"""Doctors Availability by Day, Week and Month: one doctor's days, 1 to 42 at a time. Real database, test
clinics only (the access tests' world, removed after)."""

from typing import Any

import pytest
from httpx import AsyncClient

from tests.test_crm_access import world  # noqa: F401  (the fixture)
from tests.test_crm_auth import api, needs_db, signed_in_as  # noqa: F401

pytestmark = needs_db


async def test_a_doctors_days_come_as_a_day_a_week_or_a_months_calendar(
    api: AsyncClient,  # noqa: F811
    world: dict[str, Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = signed_in_as(monkeypatch, world["manager"]["id"])
    url = f"/v1/crm/availability/{world['my_record']}?clinic=CL99&start=2026-11-02"
    for days in (1, 7, 42):
        got = (await api.get(f"{url}&days={days}", headers=h)).json()
        assert len(got["days"]) == days and got["days"][0]["date"] == "2026-11-02"
    assert len((await api.get(url, headers=h)).json()["days"]) == 7  # a week, as before
    assert (await api.get(f"{url}&days=43", headers=h)).status_code == 422
