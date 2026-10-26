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
        assert start["draft"]["template"]["id"] == "tiles" and isinstance(start["menu"], list)
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
        t = await api.put(url + "/template", json={"id": "pills"}, headers=headers)
        assert t.json()["draft"]["template"]["id"] == "pills"
        assert (await api.put(url + "/template", json={"id": "grid"}, headers=headers)).status_code == 422
        menu = {
            "welcome": "Hello",
            "figures": [{"value": "4.8★", "label": "Google rating"}],
            "buttons": [
                {"label": "Book", "action": "submenu", "sub": [{"label": "In clinic", "action": "book"}]}
            ],
        }
        m = await api.put(url + "/menu", json=menu, headers=headers)
        assert m.status_code == 200 and m.json()["draft"]["menu"]["buttons"][0]["sub"][0]["action"] == "book"
        bad_menu = menu | {"buttons": [{"label": "X", "action": "fly"}]}
        assert (await api.put(url + "/menu", json=bad_menu, headers=headers)).status_code == 422
        contact = start["draft"]["contact"]
        assert len(contact["hours"]) == 7 and contact["emergency_number"] == "108"
        c = await api.put(url + "/contact", json=contact | {"phone": "+919000000010"}, headers=headers)
        assert c.status_code == 200 and c.json()["draft"]["contact"]["phone"] == "+919000000010"
        assert (
            await api.put(url + "/contact", json=contact | {"phone": "98765"}, headers=headers)
        ).status_code == 422
        services = {
            "items": [{"name": "PRP Treatment", "price": 5000, "show_price": True}],
            "booking_options": ["PRP"],
        }
        sv = await api.put(url + "/services", json=services, headers=headers)
        assert sv.status_code == 200 and sv.json()["draft"]["services"]["items"][0]["price"] == 5000
        bad_sv = {"items": [{"name": "X", "page": "http://plain"}]}
        assert (await api.put(url + "/services", json=bad_sv, headers=headers)).status_code == 422
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
