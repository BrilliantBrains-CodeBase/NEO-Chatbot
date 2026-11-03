"""Knowledge base answers, regular matching (R2a)."""

import json

import asyncpg
import pytest

from app.chat import embed, engine, kb, service, store
from app.chat.kb import _Row, best, words
from app.core.config import get_settings
from tests.test_chat_store import SID, req

ROWS = [
    _Row(str(i), q, a, tuple(words(x) for x in [q, *v]))
    for i, (q, v, a) in enumerate(
        [
            ("How much does a hair transplant cost?", ["kitne ka hai"], "Rs 60 to 100 per graft."),
            ("Do you offer EMI?", ["emi available"], "Yes, EMI is available."),
            ("Where is the clinic located?", ["address"], "Marathahalli."),
            ("What is PRP?", ["prp treatment"], "Platelet-rich plasma."),
            ("What does PRP or GFC cost?", ["prp price"], "Agreed at consultation."),
        ]
    )
]


@pytest.mark.parametrize(
    ("text", "question"),
    [
        ("hair transplant cost?", "How much does a hair transplant cost?"),
        ("transplant kitne ka hai", "How much does a hair transplant cost?"),
        ("emi", "Do you offer EMI?"),
        ("adress", "Where is the clinic located?"),  # typo
        ("prp kya hai", "What is PRP?"),
        ("is it", None),
        ("hello", None),
        ("do you treat acne", None),
    ],
)
def test_regular_matching(text: str, question: str | None) -> None:
    hit = best(ROWS, text)
    assert (hit.question if hit else None) == question


def test_rules_come_first_then_the_kb_then_the_lead() -> None:
    turn = engine.respond(req("text", clinic="CL01", text="visa"), {}, None, "Yes, EMI is available.")
    assert turn.answered_by == "kb" and turn.reply.messages[0].text == "Yes, EMI is available."
    booking = engine.respond(req("text", clinic="CL01", text="book an appointment"), {}, None, "x")
    assert booking.answered_by != "kb"  # a rule (start booking) wins over a KB answer
    nothing = engine.respond(req("text", clinic="CL01", text="visa"), {}, None, None)
    assert nothing.answered_by == "lead"


def test_a_kb_answer_mid_booking_keeps_the_step() -> None:
    flow = {"kind": "book", "step": "name"}
    turn = engine.respond(
        req("text", clinic="CL01", text="do you provide visa help?"), {"flow": flow}, None, "EMI: yes."
    )
    assert turn.answered_by == "kb" and turn.reply.messages[0].text == "EMI: yes."
    assert turn.state["flow"]["step"] == "name" and "questions" not in turn.state["flow"]


@pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")
async def test_only_approved_rows_answer_and_medical_never_asks_the_kb(tx: asyncpg.Connection) -> None:
    kb._cache.clear()
    await tx.execute(
        """insert into app.kb_qa (clinic_id, question, variants, answer, status, approved_at) values
           ('CL99', 'Is there parking?', 'parking', 'Yes, free parking.', 'approved', now()),
           ('CL99', 'Do you have a lift?', 'lift', 'Draft only.', 'draft', null)"""
    )
    assert (await kb.search(tx, "CL99", "parking available?")).answer == "Yes, free parking."  # type: ignore[union-attr]
    assert await kb.search(tx, "CL99", "lift") is None
    assert (
        await service._kb(tx, req("text", text="is parking painful"), []) is None
    )  # medical word: never the KB
    kb._cache.clear()


async def _ask(db: asyncpg.Connection, text: str, state: dict[str, object] | None = None) -> None:
    r = req("text", clinic="CL01", text=text)
    await store.open_session(db, r)
    steps: list[service.Step] = []
    hit = await service._kb(db, r, steps)
    turn = engine.respond(r, state or {}, None, hit.answer if hit else None)
    await service._trace(db, r, turn, hit, steps, 0.0)


@pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")
async def test_every_question_is_traced_step_by_step(tx: asyncpg.Connection) -> None:
    kb._cache.clear()
    await tx.execute(  # its own answer, undone with the test: never the clinic's changing content
        """insert into app.kb_qa (clinic_id, question, variants, answer, status, approved_at)
           values ('CL01', 'Do you provide visa assistance?', '', 'Yes, we help.', 'approved', now())"""
    )
    for text in ("do you provide visa assistance", "is it painful", "talk to someone", "sell shampoo?"):
        await _ask(tx, text)
    await _ask(tx, "Asha Rao", {"flow": {"kind": "book", "step": "name"}})  # a form answer: not traced
    rows = await tx.fetch(
        "select answered_by, kb_qa_id is not null as kb, steps from app.rag_traces "
        "where session_id = $1 order by id",
        SID,
    )
    assert [(r["answered_by"], r["kb"]) for r in rows] == [
        ("kb", True), ("medical", False), ("rule", False), ("lead", False)
    ]  # fmt: skip
    first = [s["step"] for s in json.loads(rows[0]["steps"])]
    assert first == ["emergency_medical", "rules", "kb_regular"]
    await tx.execute("delete from app.chat_sessions where id = $1", SID)  # 3-day cleanup or privacy delete
    assert await tx.fetchval("select count(*) from app.rag_traces where session_id = $1", SID) == 0
    kb._cache.clear()


@pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")
async def test_semantic_matching_by_meaning(tx: asyncpg.Connection) -> None:
    await embed.warm()
    kb._cache.clear()
    kb._filled.clear()
    qa = await tx.fetchval(
        """insert into app.kb_qa (clinic_id, question, variants, answer, status, approved_at)
           values ('CL99', 'Where is the clinic located?', 'address\nlocation\nhow to reach\ndirections',
                   'Marathahalli.', 'approved', now())
           returning id"""
    )
    hit, score = await kb.semantic(tx, "CL99", "how do I reach your clinic")
    assert hit is not None and hit.answer == "Marathahalli." and score is not None and score >= 83
    assert await tx.fetchval("select embedding is not null from app.kb_qa where id = $1", qa)
    miss, low = await kb.semantic(tx, "CL99", "who won the cricket match")
    assert miss is None and low is not None and low < 83  # the near miss is still reported for the trace
    steps: list[service.Step] = []
    await service._kb(tx, req("text", text="who won the cricket match"), steps)  # no word match
    assert [s["step"] for s in steps] == [
        "emergency_medical", "kb_regular", "kb_fact_regular", "kb_semantic", "kb_fact_semantic"
    ]  # fmt: skip
    await tx.execute("update app.kb_qa set variants = 'map' where id = $1", qa)  # staff edit
    assert await tx.fetchval("select embedding is null from app.kb_qa where id = $1", qa)
    kb._cache.clear()
    kb._filled.clear()


def test_a_bare_fact_value_gets_its_name() -> None:
    assert kb.fact_text("email", "info@x.com") == "Email: info@x.com"
    assert kb.fact_text("clinic_name", "Neo Follicle Clinic, Bengaluru.") == "Neo Follicle Clinic, Bengaluru."


@pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")
async def test_facts_answer_by_their_name_only_when_approved(tx: asyncpg.Connection) -> None:
    kb._facts.clear()
    await tx.execute(
        """insert into app.kb_facts (clinic_id, key, value, status, approved_at) values
           ('CL99', 'clinic_name', 'Test Clinic, Bengaluru.', 'approved', now()),
           ('CL99', 'email', 'hello@test.example', 'approved', now()),
           ('CL99', 'wifi_password', 'Draft only.', 'draft', null)"""
    )
    name = await kb.fact(tx, "CL99", "clinic name")
    assert name and name.answer == "Test Clinic, Bengaluru." and name.source == "fact"
    email = await kb.fact(tx, "CL99", "email id")
    assert email and email.answer == "Email: hello@test.example"
    assert await kb.fact(tx, "CL99", "wifi password") is None  # a draft never answers
    assert await kb.fact(tx, "CL99", "do you treat acne") is None
    steps: list[service.Step] = []
    hit = await service._kb(tx, req("text", text="what is the clinic name"), steps)
    assert hit and hit.source == "fact"
    assert [s["step"] for s in steps][-1] == "kb_fact_regular"
    kb._facts.clear()
