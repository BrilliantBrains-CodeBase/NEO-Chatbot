"""Knowledge base, regular matching (layer 2): the patient's question against the clinic's APPROVED
questions and their other wordings, with typo-tolerant word matching. Only a confident match is
answered; anything else goes on to the lead. Semantic matching is added on top later.
"""

import re
import time
from dataclasses import dataclass

import asyncpg
from rapidfuzz import fuzz

CACHE_S = 60  # approved rows change rarely; a minute keeps CRM edits quick to show
MIN_SCORE = 86  # below this, no answer (a wrong answer is worse than a call back)

# Words that carry no meaning for matching ("is it", "do you" alone must never match anything).
STOP = set(
    "a an the is are am was be do does did can could will would should i me my we you your our it its "
    "this that there here of in on at to for from with and or what how when where who which why "
    "please tell about any have has get know want need hai ka ki ke ko kya hain mujhe aap se".split()
)


@dataclass(frozen=True)
class Answer:
    id: str
    question: str
    answer: str
    score: float


@dataclass(frozen=True)
class _Row:
    id: str
    question: str
    answer: str
    keys: tuple[str, ...]  # the question and each wording, as content words


_cache: dict[str, tuple[float, list[_Row]]] = {}


def words(text: str) -> str:
    return " ".join(w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP)


async def _rows(conn: asyncpg.Connection, clinic_id: str) -> list[_Row]:
    now = time.monotonic()
    hit = _cache.get(clinic_id)
    if hit and now - hit[0] < CACHE_S:
        return hit[1]
    rows = [
        _Row(
            str(r["id"]),
            r["question"],
            r["answer"],
            tuple(k for k in (words(x) for x in [r["question"], *r["variants"].splitlines()]) if k),
        )
        for r in await conn.fetch(
            "select id, question, variants, answer from app.kb_qa "
            "where clinic_id = $1 and status = 'approved'",
            clinic_id,
        )
    ]
    _cache[clinic_id] = (now, rows)
    return rows


def best(rows: list[_Row], text: str) -> Answer | None:
    """The best approved question for the text, if it is a confident match."""
    query = words(text)
    if not query:
        return None
    # One meaningful word ("emi", "visa") is enough only when it points to one or two questions.
    single = len(query.split()) == 1
    if single:
        exact = [r for r in rows if query in r.keys]
        holders = exact or [r for r in rows if any(query in k.split() for k in r.keys)]
        if len(holders) > 2:
            return None  # too general ("transplant"): not a confident answer
        if holders:
            r = holders[0]
            return Answer(r.id, r.question, r.answer, 90.0)
        # not found as a word: still checked below for typos ("adress")
    top: tuple[float, float, _Row] | None = None
    for row in rows:
        for key in row.keys:
            # Whole wording against whole question, tolerant of word order and small typos. One being
            # inside the other also counts (a little lower). Ties go to the closer overall wording.
            close = max(fuzz.token_sort_ratio(query, key), fuzz.ratio(query, key))
            score = close if single and len(query) < 6 else max(close, fuzz.token_set_ratio(query, key) - 4)
            if score >= MIN_SCORE and (top is None or (score, close) > top[:2]):
                top = (score, close, row)
    return Answer(top[2].id, top[2].question, top[2].answer, top[0]) if top else None


async def search(conn: asyncpg.Connection, clinic_id: str, text: str) -> Answer | None:
    return best(await _rows(conn, clinic_id), text)
