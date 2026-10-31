"""Dashboard → Knowledge base: facts and Q&A saved as drafts, approved by a manager, Q&A answers that link
facts ({consult_fee}) filled when the bot replies, and never given while a linked fact is missing. Uses the
hidden test clinic CL99 and removes what it made."""

import pytest
from httpx import AsyncClient

from app.chat import kb
from app.core.db import close_pool, get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture

URL = "/v1/crm/console/CL99/kb"


def test_links_are_filled_only_when_every_fact_is_known() -> None:
    assert kb.links("Fee {fee}, EMI {emi}, again {fee}.") == ["fee", "emi"]
    assert kb.fill("Fee is {fee}.", {"fee": "Rs 700"}) == "Fee is Rs 700."
    assert kb.fill("Fee is {fee}.", {}) is None
    assert kb.fill("No links here.", {}) == "No links here."


@needs_db
async def test_knowledge_base_drafts_approval_and_fact_links(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    try:
        fact = {"key": "test_consult_fee", "category": "cost", "value": "Rs 700", "variants": "fee\n fee \n"}
        r = await api.post(f"{URL}/facts", json=fact, headers=headers)
        assert r.status_code == 200, r.text
        [f] = [x for x in r.json()["facts"] if x["key"] == "test_consult_fee"]
        assert f["status"] == "draft" and f["variants"] == "fee" and r.json()["can_approve"]
        assert (await api.post(f"{URL}/facts", json=fact, headers=headers)).status_code == 409  # same key

        qa = {
            "question": "How much is the test consultation?",
            "variants": "test consultation price",
            "answer": "The test consultation fee is {test_consult_fee}.",
            "category": "cost",
        }
        r = await api.post(f"{URL}/qa", json=qa, headers=headers)
        [q] = [x for x in r.json()["qa"] if x["question"] == qa["question"]]
        assert q["links"] == ["test_consult_fee"] and q["missing"] == ["test_consult_fee"]
        assert next(x for x in r.json()["facts"] if x["id"] == f["id"])["used_by"] == 1

        # A Q&A that links a fact not approved yet cannot be approved.
        r = await api.post(f"{URL}/qa/{q['id']}/approve", headers=headers)
        assert r.status_code == 422 and "{test_consult_fee}" in r.text
        await api.post(f"{URL}/facts/{f['id']}/approve", headers=headers)
        r = await api.post(f"{URL}/qa/{q['id']}/approve", headers=headers)
        assert r.status_code == 200, r.text

        async with pool.acquire() as conn:  # the bot answers with the fact filled in
            hit = await kb.search(conn, "CL99", "how much is the test consultation")
        assert hit is not None and hit.answer == "The test consultation fee is Rs 700."

        # A changed fact is a draft again: the answer linking it is not given until it is approved.
        r = await api.put(f"{URL}/facts/{f['id']}", json=fact | {"value": "Rs 900"}, headers=headers)
        assert next(x for x in r.json()["qa"] if x["id"] == q["id"])["missing"] == ["test_consult_fee"]
        async with pool.acquire() as conn:
            assert await kb.search(conn, "CL99", "how much is the test consultation") is None
        await api.post(f"{URL}/facts/{f['id']}/approve", headers=headers)
        async with pool.acquire() as conn:
            hit = await kb.search(conn, "CL99", "test consultation price")
        assert hit is not None and hit.answer == "The test consultation fee is Rs 900."

        r = await api.post(f"{URL}/qa/{q['id']}/retire", headers=headers)  # retired: never answered
        assert next(x for x in r.json()["qa"] if x["id"] == q["id"])["status"] == "retired"
        async with pool.acquire() as conn:
            assert await kb.search(conn, "CL99", "how much is the test consultation") is None
        assert (await api.post(f"{URL}/qa/not-an-id/approve", headers=headers)).status_code == 404
    finally:
        await pool.execute(
            "delete from app.kb_qa where clinic_id = 'CL99' and question like '%test consultation%'"
        )
        await pool.execute("delete from app.kb_facts where clinic_id = 'CL99' and key = 'test_consult_fee'")
        kb.forget("CL99")
        await close_pool()


@needs_db
async def test_upload_rows_become_drafts(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    fact = {"row": 2, "kind": "fact", "key": "test_up_fee", "category": "cost", "value": "Rs 800"}
    qa = {
        "row": 3,
        "kind": "qa",
        "question": "Test upload question?",
        "value": "Fee {test_up_fee}.",
        "category": "",
    }
    bad = {"row": 4, "kind": "fact", "key": "Bad Key!", "value": "x"}
    try:
        r = await api.post(f"{URL}/import", json={"rows": [fact, qa, bad]}, headers=headers)
        assert r.status_code == 200, r.text
        got = r.json()
        assert (got["added"], got["updated"], got["unchanged"]) == (2, 0, 0)
        assert len(got["problems"]) == 1 and got["problems"][0].startswith("Row 4: key")
        [f] = [x for x in got["knowledge"]["facts"] if x["key"] == "test_up_fee"]
        assert f["status"] == "draft" and f["used_by"] == 1

        again = [fact | {"value": "Rs 900"}, qa | {"question": "TEST upload   question?"}]
        got = (await api.post(f"{URL}/import", json={"rows": again}, headers=headers)).json()
        assert (got["added"], got["updated"], got["unchanged"]) == (0, 1, 1)
        assert next(x for x in got["knowledge"]["facts"] if x["key"] == "test_up_fee")["value"] == "Rs 900"
    finally:
        await pool.execute(
            "delete from app.kb_qa where clinic_id = 'CL99' and question = 'Test upload question?'"
        )
        await pool.execute("delete from app.kb_facts where clinic_id = 'CL99' and key = 'test_up_fee'")
        kb.forget("CL99")
        await close_pool()


@needs_db
async def test_dashboard_answers_are_live_facts(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Clinic details, hours, services and doctors are read from the Dashboard / CRM, never typed again."""
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    try:
        got = (await api.get(URL, headers=headers)).json()
        live = {x["key"]: x for x in got["live"]}
        name = await pool.fetchval("select name from app.clinics where id = 'CL99'")
        assert live["clinic_name"]["value"] == name and "Clinics" in live["clinic_name"]["source"]
        assert "timings_monday" in live and live["consultation_length"]["value"].startswith("About ")

        r = await api.post(f"{URL}/facts", json={"key": "clinic_name", "value": "Other"}, headers=headers)
        assert r.status_code == 409 and "change it there" in r.text  # answered in the Dashboard
        rows = [{"row": 2, "kind": "fact", "key": "clinic_name", "value": "Other"}]
        got = (await api.post(f"{URL}/import", json={"rows": rows}, headers=headers)).json()
        assert got["added"] == 0 and "change it there" in got["problems"][0]

        qa = {
            "question": "Test what is the clinic called?",
            "answer": "We are {clinic_name}.",
            "category": "other",
        }
        r = await api.post(f"{URL}/qa", json=qa, headers=headers)
        [q] = [x for x in r.json()["qa"] if x["question"] == qa["question"]]
        assert q["missing"] == []  # a Dashboard key counts as approved
        assert (await api.post(f"{URL}/qa/{q['id']}/approve", headers=headers)).status_code == 200
        async with pool.acquire() as conn:
            hit = await kb.search(conn, "CL99", "test what is the clinic called")
        assert hit is not None and hit.answer == f"We are {name}."
    finally:
        await pool.execute(
            "delete from app.kb_qa where clinic_id = 'CL99' and question like 'Test what is the clinic%'"
        )
        kb.forget("CL99")
        await close_pool()
