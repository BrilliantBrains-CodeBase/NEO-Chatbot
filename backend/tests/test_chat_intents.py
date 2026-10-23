"""T2: topics from approved example phrases, for messages no keyword rule caught. T3: fact wordings."""

import asyncpg
import pytest

from app.chat import engine, intents, kb, service
from app.core.config import get_settings
from tests.test_chat_store import req

ROWS = [("identity", "are you a robot"), ("book", "kab aa sakta hoon"), ("thanks", "thanks a ton")]


@pytest.mark.parametrize(
    ("text", "want"),
    [("are you a robot", "identity"), ("Are you a robot?", "identity"), ("are you a robto", "identity"),
     ("kab aa sakta hoon", "book"), ("are you", None), ("do you have parking", None)],
)  # fmt: skip
def test_by_words_is_the_phrase_or_a_small_typo(text: str, want: str | None) -> None:
    hit = intents.by_words(ROWS, text)
    assert (hit.intent if hit else None) == want


def _text(text: str, intent: str | None, kb_answer: str | None = None) -> engine.Turn:
    return engine.respond(req("text", clinic="CL01", text=text), {}, None, kb_answer, intent)


def test_a_topic_does_what_its_rule_does() -> None:
    assert _text("kab aa sakta hoon", "book").state["flow"]["kind"] == "book"  # booking starts at once
    assert "Arya" in _text("bot ho kya", "identity").reply.messages[0].text
    assert _text("thanks a ton yaar", "thanks").reply.messages[0].text == engine.THANKS
    callback = _text("ring me back", "callback")
    assert callback.state["flow"]["kind"] == "callback"


def test_a_topic_never_beats_an_answer_or_the_medical_guard() -> None:
    assert _text("kab aa sakta hoon", "book", kb_answer="Approved answer.").answered_by == "kb"
    assert _text("is it painful", "book").answered_by == "lead"  # medical: never answered
    assert _text("asdfgh", None).answered_by == "lead"
    assert _text("asdfgh", "no_such_topic").answered_by == "lead"  # a topic the clinic does not have


@pytest.mark.parametrize(
    ("text", "state", "want"),
    [("kab aa sakta hoon", {}, True), ("who are you", {}, False), ("thanks", {}, False),
     ("tell me more", {}, False), ("where is the clinic", {}, False),
     ("Asha Rao", {"flow": {"kind": "book", "step": "name"}}, False)],
)  # fmt: skip
def test_only_what_nothing_else_understood_is_looked_up(text: str, state: dict, want: bool) -> None:  # type: ignore[type-arg]
    assert engine.wants_intent(req("text", clinic="CL01", text=text), state, text) is want


@pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")
async def test_only_approved_phrases_and_wordings_count(tx: asyncpg.Connection) -> None:
    intents._rows.clear()
    kb._facts.clear()
    await tx.execute(
        """insert into app.intent_examples (clinic_id, intent, example, status, approved_at) values
           ('CL99', 'identity', 'are you a robot', 'approved', now()),
           ('CL99', 'book', 'kab aa sakta hoon', 'draft', null)"""
    )
    await tx.execute(
        """insert into app.kb_facts (clinic_id, key, value, variants, status, approved_at)
           values ('CL99', 'social', 'Instagram: @test', $1, 'approved', now())""",
        "insta id\ninstagram",
    )
    hit, _ = await intents.find(tx, "CL99", "are you a robot")
    assert hit and hit.intent == "identity" and hit.how == "words"
    assert (await intents.find(tx, "CL99", "kab aa sakta hoon"))[0] is None  # a draft never counts
    fact = await kb.fact(tx, "CL99", "insta id")
    assert fact and fact.answer == "Instagram: @test"
    medical: list[service.Step] = [{"step": "medical", "result": "matched"}]
    r = req("text", clinic="CL01", text="are you a robot")
    assert await service._intent(tx, r, {}, "are you a robot", medical) is None  # never after the guard
    assert medical == [{"step": "medical", "result": "matched"}]  # and not even looked up
    intents._rows.clear()
    kb._facts.clear()


def test_a_phrase_can_name_the_exact_button_under_a_general_rule() -> None:
    assert intents.refines(("node", "cost"), "cost_receding")
    assert intents.refines(("node", "treat"), "t_prp_treatment") and intents.refines(("node", "treat"), "hf")
    assert intents.refines(("start", "book"), "reschedule")
    assert not intents.refines(("node", "cost"), "t_prp_treatment")
    assert not intents.refines(("node", "clinic"), "x")
    receding = _text("my hairline is going back, cost?", "cost_receding", kb_answer="General cost answer.")
    assert receding.answered_by == "rule" and "1,000 to 1,800" in receding.reply.messages[0].text
    prp = _text("plasma treatment for hair", "t_prp_treatment")
    assert prp.reply.messages[0].text.startswith("**PRP Treatment**")


def test_treatment_topics_use_letters_only() -> None:
    assert intents.treatment_topic("PRP Treatment") == "t_prp_treatment"
    assert intents.treatment_topic("QR678 Treatment") == "t_qr_treatment"
    assert len(intents.treatment_topic("Direct Hair Transplant (DHI / FUE)")) <= 30


@pytest.mark.parametrize("text", ["why is my hair falling", "why am i going bald", "is my hair loss normal"])
def test_cause_and_normal_questions_are_medical(text: str) -> None:
    assert _text(text, "hf").answered_by == "lead"
