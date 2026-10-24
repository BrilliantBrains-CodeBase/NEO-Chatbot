"""Google Sheet leads (POST /v1/integrations/sheet-leads), on the test clinic (CL99)."""

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.db import get_pool
from tests.test_crm_auth import api, needs_db

__all__ = ["api"]  # the client fixture

ROW = {
    "id": "l:123",
    "created_time": "2026-10-24T10:00:00+05:30",
    "campaign_name": "Diwali hair offer",
    "ad_name": "Video 1",
    "full_name": "Sheet  Lead",
    "phone_number": "p:+919000000005",
    "email": "Sheet@Example.com",
    "which_treatment_are_you_interested_in?": "Beard transplant",
}


@needs_db
async def test_sheet_row_makes_then_updates_a_lead(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "sheet_webhook_secret", "test-secret")
    url = "/v1/integrations/sheet-leads"
    body = {"clinic": "CL99", "secret": "test-secret", "sheet": "Meta leads", "row_number": 2, "row": ROW}
    assert (await api.post(url, json=body | {"secret": "wrong"})).status_code == 401
    bad = body | {"row": ROW | {"phone_number": "", "email": ""}}
    assert (await api.post(url, json=bad)).status_code == 422
    pool = await get_pool()
    r = await api.post(url, json=body)
    assert r.status_code == 200 and r.json()["created"] is True
    code = r.json()["lead_code"]
    try:
        lead = await pool.fetchrow("select * from app.leads where lead_code = $1", code)
        assert (lead["full_name"], lead["phone_e164"], lead["email"], lead["source"], lead["campaign"]) == (
            "Sheet Lead", "+919000000005", "sheet@example.com", "meta_ads", "Diwali hair offer",
        )  # fmt: skip
        assert "Beard transplant" in lead["notes"]
        # Same phone again: no second lead.
        again = await api.post(url, json=body | {"row_number": 3})
        assert again.json() == {"lead_code": code, "created": False}
        # The row edited (phone corrected) and sent with its code: that lead is updated.
        fixed = body | {"lead_code": code, "row": ROW | {"phone_number": "9000000006"}}
        assert (await api.post(url, json=fixed)).json() == {"lead_code": code, "created": False}
        lead = await pool.fetchrow("select * from app.leads where lead_code = $1", code)
        assert lead["phone_e164"] == "+919000000006" and lead["contact_count"] == 3
    finally:
        lead_id = await pool.fetchval("select id from app.leads where lead_code = $1", code)
        await pool.execute("select app.delete_patient_data($1)", lead_id)
