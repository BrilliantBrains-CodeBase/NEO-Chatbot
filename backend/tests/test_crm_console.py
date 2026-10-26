"""Dashboard settings (draft, save, publish), on the test clinic CL99. Published versions are a permanent
record (they cannot be deleted), so each run adds versions to CL99; the draft row is cleared after."""

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture


@needs_db
async def test_appearance_draft_and_publish(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    url = "/v1/crm/console/CL99/settings"
    await pool.execute("delete from app.clinic_settings where clinic_id = 'CL99'")
    try:
        start = (await api.get(url, headers=headers)).json()
        look = start["draft"]["appearance"]["look"]
        assert start["version"] == 0 and look["enabled"] is True and len(look["avatar_letter"]) == 1
        bad = await api.put(url + "/appearance", json={"colours": {"main": "blue"}}, headers=headers)
        assert bad.status_code == 422
        r = await api.put(
            url + "/appearance",
            json={
                "look": {"name": "Test Bot"},
                "colours": {"main": "#112233"},
                "launcher": {"label_text": "Hi"},
            },
            headers=headers,
        )
        d = r.json()
        assert r.status_code == 200 and d["changed"] is True
        a = d["draft"]["appearance"]
        assert (a["look"]["name"], a["colours"]["main"], a["launcher"]["label_text"]) == (
            "Test Bot",
            "#112233",
            "Hi",
        )
        assert a["colours"]["highlight"] == "#FFCC70"  # untouched fields keep their defaults
        p = await api.post("/v1/crm/console/CL99/publish", headers=headers)
        assert p.status_code == 200 and p.json()["version"] >= 1 and p.json()["changed"] is False
        assert p.json()["published"]["appearance"]["look"]["name"] == "Test Bot"
        assert (await api.post("/v1/crm/console/CL99/publish", headers=headers)).status_code == 409
        assert (
            await pool.fetchval(
                "select settings -> 'appearance' -> 'look' ->> 'name' from app.clinic_setting_versions"
                " where clinic_id = 'CL99' order by version desc limit 1"
            )
            == "Test Bot"
        )
    finally:
        await pool.execute("delete from app.clinic_settings where clinic_id = 'CL99'")
