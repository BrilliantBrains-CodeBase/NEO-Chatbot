"""Login & security → Clinics: a code from the name, a copy of another clinic's setup and chat (never its own
details), deactivate. Removes the test clinic afterwards."""

from typing import Any

import pytest
from httpx import AsyncClient

from app.api.v1.crm_clinics import next_code
from app.core.db import close_pool, get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture


def test_the_code_comes_from_the_name() -> None:
    assert next_code("Neo Follicle Hair Transplant", set()) == "NFHT"
    assert next_code("BB Fertility", {"NFHT"}) == "BF"
    assert next_code("Bright Face", {"BF"}) == "BF2"  # taken: a number is added
    assert next_code("Best Fit", {"BF", "BF2"}) == "BF3"
    assert next_code("Apollo", set()) == "AP"  # one word: its first two letters
    assert next_code("1st Dental Care", set()) == "DC"  # starts with a letter


@needs_db
async def test_add_a_clinic_copied_from_another(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    before = {r["id"] for r in await pool.fetch("select id from app.clinics")}
    new: Any = None
    try:
        body = {"name": "Test New Clinic", "bot_name": "Mira", "copy_from": "NFHT", "phone": "+919000000111"}
        r = await api.post("/v1/crm/clinics", json=body, headers=headers)
        assert r.status_code == 201, r.text
        new = next(c for c in r.json() if c["id"] not in before)
        assert (
            new["id"] == next_code("Test New Clinic", before) and new["active"] and new["bot_name"] == "Mira"
        )
        assert new["id"].startswith("TNC")  # the first letter of each word
        row = await pool.fetchrow("select * from app.clinics where id = $1", new["id"])
        src = await pool.fetchrow("select * from app.clinics where id = 'NFHT'")
        assert row["slot_minutes"] == src["slot_minutes"]  # its setup is copied
        assert row["website"] is None  # its details are not
        pub = await pool.fetchval("select published from app.clinic_settings where clinic_id = $1", new["id"])
        import json

        pub = json.loads(pub)
        assert set(pub) <= {"flow", "appearance", "template", "menu", "chat"}  # no contact, services, reviews
        assert pub["appearance"]["look"]["name"] == "Mira" and pub["chat"]["canvas"] is True
        r = await api.put(f"/v1/crm/clinics/{new['id']}", json={"active": False}, headers=headers)
        assert next(c for c in r.json() if c["id"] == new["id"])["active"] is False
    finally:
        if new:
            await pool.execute("delete from app.clinic_settings where clinic_id = $1", new["id"])
            await pool.execute("delete from app.clinics where id = $1", new["id"])
        await close_pool()


@needs_db
async def test_delete_only_an_empty_clinic(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    before = {r["id"] for r in await pool.fetch("select id from app.clinics")}
    try:
        body = {"name": "Test Delete Clinic", "bot_name": "Zed", "copy_from": "NFHT"}
        r = await api.post("/v1/crm/clinics", json=body, headers=headers)
        new = next(c["id"] for c in r.json() if c["id"] not in before)
        r = await api.delete(f"/v1/crm/clinics/{new}", headers=headers)
        assert r.status_code == 200 and all(c["id"] != new for c in r.json())
        assert (await api.delete("/v1/crm/clinics/NFHT", headers=headers)).status_code == 403
    finally:
        for c in {r["id"] for r in await pool.fetch("select id from app.clinics")} - before:
            await pool.execute("delete from app.clinic_settings where clinic_id = $1", c)
            await pool.execute("delete from app.clinics where id = $1", c)
        await close_pool()
