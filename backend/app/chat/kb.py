"""Knowledge base, regular matching (layer 2): the patient's question against the clinic's APPROVED
questions and their other wordings, with typo-tolerant word matching. Only a confident match is
answered; anything else goes on to the lead. Semantic matching is added on top later.
"""

import logging
import re
import time
from dataclasses import dataclass

import asyncpg
from rapidfuzz import fuzz

from app.chat import embed
from app.core.db import get_pool

log = logging.getLogger(__name__)
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


# --- Semantic matching (meaning, not words): only when regular matching found nothing -------------------

SEMANTIC_MIN = 0.83  # measured on CL01: right answers scored 0.83 to 0.93, unrelated questions up to 0.79
_filled: dict[str, float] = {}


async def _fill(conn: asyncpg.Connection, clinic_id: str) -> None:
    """Meaning numbers for approved Q/A that have none yet (new or edited), at most once a minute."""
    now = time.monotonic()
    if now - _filled.get(clinic_id, -CACHE_S) < CACHE_S:
        return
    for r in await conn.fetch(
        "select id, question, variants from app.kb_qa "
        "where clinic_id = $1 and status = 'approved' and embedding is null",
        clinic_id,
    ):
        v = await embed.meaning([r["question"], *[x for x in r["variants"].splitlines() if x.strip()]])
        await conn.execute(
            "update app.kb_qa set embedding = $2::extensions.vector where id = $1", r["id"], embed.as_pg(v)
        )
    _filled[clinic_id] = now


async def semantic(conn: asyncpg.Connection, clinic_id: str, text: str) -> tuple[Answer | None, float | None]:
    """The closest approved question by meaning, if close enough; also the best score, for the trace.
    (None, None) while the model is still loading."""
    if not embed.ready():
        return None, None
    await _fill(conn, clinic_id)
    q = embed.as_pg(await embed.vector(text))
    row = await conn.fetchrow(
        """select id, question, answer, 1 - (embedding operator(extensions.<=>) $2::extensions.vector) as sim
           from app.kb_qa where clinic_id = $1 and status = 'approved' and embedding is not null
           order by embedding operator(extensions.<=>) $2::extensions.vector limit 1""",
        clinic_id,
        q,
    )
    if row is None:
        return None, None
    score = round(float(row["sim"]) * 100, 1)
    hit = (
        Answer(str(row["id"]), row["question"], row["answer"], score) if row["sim"] >= SEMANTIC_MIN else None
    )
    return hit, score


async def warm() -> None:
    """At startup: load the model, then fill the meaning of every approved Q/A that has none, so no patient
    waits for it. A failure only leaves semantic matching off; the chat keeps working."""
    await embed.warm()
    if not embed.ready():
        return
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            for clinic_id in await conn.fetch(
                "select distinct clinic_id from app.kb_qa where status = 'approved' and embedding is null"
            ):
                await _fill(conn, clinic_id[0])
    except Exception:
        log.exception("could not fill knowledge base meanings at startup; they are filled on first use")
