"""Clinic codes (migration 0040): NFHT was CL01. Outside systems may still send the old code or old lead codes
(a cached chatbot file, the Cal.com webhook, the Google Sheet script, links in older messages): they still
reach the clinic. Everything new uses the new code."""

import re

import pytest
from httpx import AsyncClient

from app.chat.schemas import ChatRequest
from app.core.codes import CLINIC_CODE, current, current_lead
from app.core.db import get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture


def test_old_codes_map_to_the_new_ones() -> None:
    assert current("CL01") == "NFHT" and current("NFHT") == "NFHT" and current("CL99") == "CL99"
    assert current_lead("CL01-00003") == "NFHT-00003"
    assert current_lead("NFHT-00003") == "NFHT-00003" and current_lead("CL99-00001") == "CL99-00001"
    assert current_lead("CL01") == "CL01"  # not a lead code: as is


def test_the_code_format() -> None:
    for ok in ("NFHT", "BF", "BF2", "CL99", "CL101"):
        assert re.fullmatch(CLINIC_CODE, ok), ok
    for bad in ("nfht", "N", "2BF", "NF-HT", "ABCDEFGHIJK"):
        assert not re.fullmatch(CLINIC_CODE, bad), bad


def test_a_cached_widget_with_the_old_code_reaches_the_clinic() -> None:
    req = ChatRequest.model_validate(
        {
            "client_id": "CL01",
            "session_id": "s_" + "0" * 32,
            "visitor_id": "v_" + "0" * 32,
            "event": "start",
            "context": {"page_url": "https://neofollicletransplant.com/", "device": "mobile", "lang": "en"},
        }
    )
    assert req.client_id == "NFHT"


@needs_db
async def test_an_old_lead_code_opens_the_lead(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    code = await pool.fetchval(
        "select lead_code from app.leads where clinic_id = 'NFHT' and deleted_at is null limit 1"
    )
    if admin is None or code is None:
        pytest.skip("no Super Admin or no NFHT lead in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    old = "CL01" + code[len("NFHT") :]
    r = await api.get(f"/v1/crm/leads/{old}", headers=headers)
    assert r.status_code == 200 and r.json()["code"] == code
    found = await api.get(
        "/v1/crm/leads", params={"clinic": "NFHT", "q": old, "owner": "all"}, headers=headers
    )
    assert [i["code"] for i in found.json()["items"]] == [code]
    assert (await api.get("/v1/widget/config/CL01")).status_code == 200  # an old cached chatbot file
