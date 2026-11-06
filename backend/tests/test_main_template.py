"""The main template: a clinic copied from Neo Follicle follows its canvas, Templates and Appearance (in its
own names) until it changes a part; "Follow main again" undoes that; only Super Admin publishes the main for
all.
Removes the test clinic afterwards."""

import re
from typing import Any

import pytest
from httpx import AsyncClient

from app.chat import main_template
from app.chat.main_template import _swap
from app.core.db import close_pool, get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture


@pytest.fixture(autouse=True)
async def _fresh_pool() -> Any:
    yield
    await close_pool()


def test_swap_names_whole_words_only() -> None:
    swaps = [
        (re.compile(r"(?<!\w)Arya AI(?!\w)", re.I), "Mira"),
        (re.compile(r"(?<!\w)Arya(?!\w)", re.I), "Mira"),
    ]
    got = _swap({"a": "Hi, I'm Arya AI", "b": ["arya here", "Aryan stays"], "c": 3}, swaps)
    assert got == {"a": "Hi, I'm Mira", "b": ["Mira here", "Aryan stays"], "c": 3}


@needs_db
async def test_follow_make_own_and_follow_again(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    before = {r["id"] for r in await pool.fetch("select id from app.clinics")}
    code = None
    try:
        body = {"name": "Test Follow Clinic", "bot_name": "Mira", "copy_from": "NFHT"}
        r = await api.post("/v1/crm/clinics", json=body, headers=headers)
        assert r.status_code == 201, r.text
        code = next(c["id"] for c in r.json() if c["id"] not in before)
        url = f"/v1/crm/console/{code}"

        s = (await api.get(f"{url}/settings", headers=headers)).json()
        assert sorted(s["follows"]) == ["appearance", "flow", "template"]
        assert all(s["draft"][k] == s["published"][k] for k in main_template.PARTS)  # nothing to publish
        assert s["draft"]["appearance"]["look"]["name"] == "Mira"  # its own bot name
        main = await pool.fetchval("select shared from app.clinic_settings where clinic_id = 'NFHT'")
        assert ("Neo Follicle" in str(main)) == ("Test Follow Clinic" in str(s["draft"]["flow"]))  # swapped

        # Saving a followed part makes it the clinic's own; the live chat keeps the main's until publish
        tpl = s["draft"]["template"]
        r = await api.put(f"{url}/settings/template", json=tpl, headers=headers)
        assert r.status_code == 200, r.text
        assert "template" not in r.json()["follows"] and "flow" in r.json()["follows"]

        # Follow main again, and make a part its own without changing it
        r = await api.put(f"{url}/main-template", json={"part": "template", "follow": True}, headers=headers)
        assert "template" in r.json()["follows"]
        r = await api.put(f"{url}/main-template", json={"part": "flow", "follow": False}, headers=headers)
        assert "flow" not in r.json()["follows"]
        async with pool.acquire() as conn:
            assert (await main_template.live_flow(conn, code)).get("nodes")  # its own copy, still live

        # Only the main is published for all; the main itself follows nothing
        r = await api.post(f"{url}/publish?for_all=true", headers=headers)
        assert r.status_code == 400
        r = await api.put(
            "/v1/crm/console/NFHT/main-template", json={"part": "flow", "follow": True}, headers=headers
        )
        assert r.status_code == 400
    finally:
        if code:
            await api.delete(f"/v1/crm/clinics/{code}", headers=headers)
