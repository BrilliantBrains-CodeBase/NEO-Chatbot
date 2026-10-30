"""Login & security → Clinics: the next free code, a copy of another clinic's setup and chat (never its own
details), deactivate. Removes the test clinic afterwards."""

from typing import Any

import pytest
from httpx import AsyncClient

from app.api.v1.crm_clinics import next_code
from app.core.db import close_pool, get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture


def test_next_code_skips_the_test_clinic() -> None:
    assert next_code({"CL01"}) == "CL02"
    assert next_code({f"CL{n:02d}" for n in range(1, 99)} | {"CL99"}) == "CL100"


@needs_db
async def test_add_a_clinic_copied_from_another(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    before = {r["id"] for r in await pool.fetch("select id from app.clinics")}
    new: Any = None
    try:
        body = {"name": "Test New Clinic", "bot_name": "Mira", "copy_from": "CL01", "phone": "+919000000111"}
        r = await api.post("/v1/crm/clinics", json=body, headers=headers)
        assert r.status_code == 201, r.text
        new = next(c for c in r.json() if c["id"] not in before)
        assert new["id"] == next_code(before) and new["active"] and new["bot_name"] == "Mira"
        row = await pool.fetchrow("select * from app.clinics where id = $1", new["id"])
        src = await pool.fetchrow("select * from app.clinics where id = 'CL01'")
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
