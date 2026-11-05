"""Email through Gmail: connect (App password in Vault), test, fallback to the BB Gmail, clear errors."""

import smtplib

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from app.crm import email
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture


@needs_db
async def test_gmail_connect_test_and_fallback(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    if await pool.fetchval("select 1 from app.email_senders where clinic_id is null or clinic_id = 'CL99'"):
        pytest.skip("a real Gmail is connected; not changed by tests")
    headers = signed_in_as(monkeypatch, str(admin))
    sent: list[tuple[str, str]] = []

    def fake_send(address: str, password: str, from_name: str, to: str, subject: str, text: str) -> None:
        if password == "wrongwrongwrongw":
            raise smtplib.SMTPAuthenticationError(535, b"bad")
        sent.append((address, to))

    monkeypatch.setattr(email, "_send", fake_send)
    clinic = "/v1/crm/console/CL99/integrations/email"
    try:
        bb = {"address": "bb@example.com", "app_password": "abcd efgh ijkl mnop", "from_name": "BB"}
        assert (await api.put("/v1/crm/security/email", json=bb, headers=headers)).json()["connected"]
        # CL99 has no Gmail: its emails come from the BB Gmail
        r = await api.post(f"{clinic}/test", json={"to": "x@example.com"}, headers=headers)
        assert r.status_code == 200 and sent[-1] == ("bb@example.com", "x@example.com")
        mine = {"address": "clinic@example.com", "app_password": "wrongwrongwrongw"}
        await api.put(clinic, json=mine, headers=headers)
        r = await api.post(f"{clinic}/test", json={"to": "x@example.com"}, headers=headers)
        assert r.status_code == 422 and "App password" in r.json()["detail"]
        log = (await api.get(clinic, headers=headers)).json()["log"]
        assert [x["ok"] for x in log[:2]] == [False, True]
        secret = await pool.fetchval("select secret from app.email_senders where clinic_id = 'CL99'")
        assert await pool.fetchval("select 1 from vault.secrets where id = $1", secret)  # kept in Vault
    finally:
        await api.delete(clinic, headers=headers)
        await api.delete("/v1/crm/security/email", headers=headers)
        await pool.execute("delete from app.email_log where clinic_id = 'CL99' or clinic_id is null")
