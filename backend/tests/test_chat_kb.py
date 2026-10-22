"""Knowledge base answers, regular matching (R2a)."""

import asyncpg
import pytest

from app.chat import engine, kb, service
from app.chat.kb import _Row, best, words
from app.core.config import get_settings
from tests.test_chat_store import req

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
    assert await service._kb(tx, req("text", text="is parking painful")) is None  # medical word: never the KB
    kb._cache.clear()
