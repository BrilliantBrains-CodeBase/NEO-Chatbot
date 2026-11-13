"""Chatbot → Clinic info → Lead questions: the questions the bot could not answer. Clinic Managers and Super
Admin only. Real database, test clinic CL99 (the access tests' world), everything made here removed after."""

from typing import Any

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_crm_access import world  # noqa: F401  (the fixture)
from tests.test_crm_auth import api, needs_db, signed_in_as  # noqa: F401

pytestmark = needs_db
URL = "/v1/crm/console/CL99/lead-questions"


async def test_lead_questions_are_listed_answered_and_turned_into_a_draft(
    api: AsyncClient,  # noqa: F811
    world: dict[str, Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = await get_pool()
    lead_id = world["lead"]["id"]
    add = """insert into app.unanswered_questions (clinic_id, question_text, reason, lead_id, session_id)
             values ('CL99', $1, $2, $3, 'zz-lq-test') returning id"""
    mine = await pool.fetchval(add, "ZzLQ do you sell shampoo", "no_match", lead_id)
    medical = await pool.fetchval(add, "ZzLQ is it painful", "medical", None)
    qa_id = None
    try:
        for who in ("desk", "doctor"):  # never Front Desk or a doctor
            h = signed_in_as(monkeypatch, world[who]["id"])
            assert (await api.get(URL, headers=h)).status_code == 403, who

        h = signed_in_as(monkeypatch, world["manager"]["id"])
        got = (await api.get(URL, params={"q": "ZzLQ"}, headers=h)).json()
        assert [i["question"] for i in got["items"]] == ["ZzLQ is it painful", "ZzLQ do you sell shampoo"]
        first = next(i for i in got["items"] if i["id"] == mine)
        assert first["lead_code"] == world["lead"]["lead_code"] and first["answered"] is False
        assert next(i for i in got["items"] if i["id"] == medical)["lead_code"] is None  # no number left

        r = await api.put(f"{URL}/{mine}", json={"answered": True}, headers=h)
        assert r.status_code == 200
        new = (await api.get(URL, params={"q": "ZzLQ"}, headers=h)).json()["items"]
        assert [i["id"] for i in new] == [medical]  # "New" hides it
        done = (await api.get(URL, params={"q": "ZzLQ", "show": "answered"}, headers=h)).json()["items"]
        assert [i["id"] for i in done] == [mine]

        bb = signed_in_as(monkeypatch, world["bb"]["id"])
        r = await api.post(f"{URL}/{medical}/kb", json={}, headers=bb)
        assert r.status_code == 200, r.text
        qa_id = r.json()["qa_id"]
        qa = await pool.fetchrow(
            "select question, status, clinic_id from app.kb_qa where id = $1::uuid", qa_id
        )
        assert (qa["question"], qa["status"], qa["clinic_id"]) == ("ZzLQ is it painful", "draft", "CL99")
        assert await pool.fetchval("select reviewed from app.unanswered_questions where id = $1", medical)
        assert (await api.put(f"{URL}/999999999", json={"answered": True}, headers=bb)).status_code == 404
    finally:
        await pool.execute("delete from app.unanswered_questions where session_id = 'zz-lq-test'")
        if qa_id:
            await pool.execute("delete from app.kb_qa where id = $1::uuid", qa_id)
