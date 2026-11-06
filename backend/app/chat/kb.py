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
from app.chat.live_facts import live_facts
from app.core.db import get_pool

log = logging.getLogger(__name__)
CACHE_S = 60  # approved rows change rarely; a minute keeps CRM edits quick to show
MIN_SCORE = 86  # below this, no answer (a wrong answer is worse than a call back)

# Words that carry no meaning for matching ("is it", "do you" alone must never match anything).
STOP = set(
    "a an the is are am was be do does did can could will would should i me my we you your our it its "
    "this that there here of in on at to for from with and or what how when where who which why "
    "please tell about any have has get know want hai ka ki ke ko kya hain mujhe aap se".split()
)


# Words too general to stand alone: "which treatments are there" is not "Are celebrity treatments different?".
GENERAL = set(
    "treatment treatments procedure procedures option options service services hair clinic doctor "
    "transplant information info details".split()
)


# Words that add nothing next to a one-word wording ("address pls", "prp kya hai batao").
FILLER = set(
    "pls plz please kya batao bataiye bolo details detail info information sir madam mam ji clinic "
    "yours ok okay now available availability id link number".split()
)


@dataclass(frozen=True)
class Answer:
    id: str
    question: str  # the approved question, or the fact's name ("clinic name")
    answer: str
    score: float
    source: str = "qa"  # "qa" (app.kb_qa) or "fact" (app.kb_facts)


@dataclass(frozen=True)
class _Row:
    id: str
    question: str
    answer: str
    keys: tuple[str, ...]  # the question and each wording, as content words


_cache: dict[str, tuple[float, list[_Row]]] = {}

# An answer may link facts by key, e.g. "Consultation fee is {consult_fee}." (Knowledge Strategy: one fact,
# many answers). The link is filled from the approved fact when the bot replies; an answer with a link to a
# fact that is missing or not approved is never given (the bot goes on as if nothing matched: a call back).
LINK = re.compile(r"\{([a-z][a-z0-9_]{1,49})\}")
_values: dict[str, tuple[float, dict[str, str]]] = {}


def links(answer: str) -> list[str]:
    """The fact keys an answer links, in order, once each."""
    return list(dict.fromkeys(LINK.findall(answer)))


def fill(answer: str, values: dict[str, str]) -> str | None:
    """The answer with its fact links filled in; None when a linked fact is missing."""
    if any(k not in values for k in links(answer)):
        return None
    return LINK.sub(lambda m: values[m.group(1)], answer)


def forget(clinic_id: str) -> None:
    """Drops this clinic's cached Knowledge base (after a Dashboard change), so the bot reads it now."""
    for cache in (_cache, _values, _facts, _filled):
        cache.pop(clinic_id, None)


async def fact_values(conn: asyncpg.Connection, clinic_id: str) -> dict[str, str]:
    """The clinic's approved facts, key -> value (cached for a minute, like the rest)."""
    now = time.monotonic()
    hit = _values.get(clinic_id)
    if hit and now - hit[0] < CACHE_S:
        return hit[1]
    values = {
        r["key"]: r["value"]
        for r in await conn.fetch(
            "select key, value from app.kb_facts where clinic_id = $1 and status = 'approved'", clinic_id
        )
    }
    values |= await live_facts(conn, clinic_id)  # the Dashboard and CRM win over a fact with the same key
    _values[clinic_id] = (now, values)
    return values


def words(text: str) -> str:
    return " ".join(w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP)


async def _rows(conn: asyncpg.Connection, clinic_id: str) -> list[_Row]:
    now = time.monotonic()
    hit = _cache.get(clinic_id)
    if hit and now - hit[0] < CACHE_S:
        return hit[1]
    values = await fact_values(conn, clinic_id)
    rows = []
    for r in await conn.fetch(
        "select id, question, variants, answer from app.kb_qa where clinic_id = $1 and status = 'approved'",
        clinic_id,
    ):
        answer = fill(r["answer"], values)
        if answer is None:  # a linked fact is missing: this answer is not given
            continue
        keys = tuple(k for k in (words(x) for x in [r["question"], *r["variants"].splitlines()]) if k)
        rows.append(_Row(str(r["id"]), r["question"], answer, keys))
    _cache[clinic_id] = (now, rows)
    return rows


def best(rows: list[_Row], text: str) -> Answer | None:
    """The best approved question for the text, if it is a confident match."""
    query = words(text)
    if not query:
        return None
    # One meaningful word ("emi", "visa") is enough only when it points to one or two questions.
    single = len(query.split()) == 1
    if single and query in GENERAL:
        return None
    if single:
        exact = [r for r in rows if query in r.keys]
        holders = [r for r in rows if any(query in k.split() for k in r.keys)]
        # A word in several questions ("surgery", "process") is not a confident answer, even when one wording
        # is only that word; one exact wording among at most two holders is ("emi").
        if exact and len(holders) <= 2:
            r = exact[0]
            return Answer(r.id, r.question, r.answer, 90.0)
        if not exact and len(holders) == 1:
            r = holders[0]
            return Answer(r.id, r.question, r.answer, 90.0)
        # not found as a word: still checked below for typos ("adress")
    asked = set(query.split())
    top: tuple[float, float, _Row] | None = None
    for row in rows:
        own = FILLER | {w for k in row.keys for w in k.split()}  # its own words also fit ("transplant kitne")
        for key in row.keys:
            # Whole wording against whole question, tolerant of word order and small typos. One being
            # inside the other also counts (a little lower). Ties go to the closer overall wording.
            close = max(fuzz.token_sort_ratio(query, key), fuzz.ratio(query, key))
            # A one-word wording inside a longer message counts only when the rest is filler or words of the
            # same question: "address pls" is the address, "email address" or "does prp hurt" is not.
            inside = len(key.split()) > 1 or asked - {key} <= own
            within = fuzz.token_set_ratio(query, key) - 4 if inside else 0
            # One word is never matched by being inside a longer wording ("surgery" is not "need surgery").
            score = close if single else max(close, within)
            if score >= MIN_SCORE and (top is None or (score, close) > top[:2]):
                top = (score, close, row)
    return Answer(top[2].id, top[2].question, top[2].answer, top[0]) if top else None


async def search(conn: asyncpg.Connection, clinic_id: str, text: str) -> Answer | None:
    return best(await _rows(conn, clinic_id), text)


# --- Semantic matching (meaning, not words): only when regular matching found nothing -------------------

SEMANTIC_MIN = 0.83  # measured on NFHT: right answers scored 0.83 to 0.93, unrelated questions up to 0.79
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
    answer = fill(row["answer"], await fact_values(conn, clinic_id))
    if row["sim"] < SEMANTIC_MIN or answer is None:  # not close enough, or a linked fact is missing
        return None, score
    return Answer(str(row["id"]), row["question"], answer, score), score


# --- Facts (layer 1): approved single facts (clinic name, email, languages...), matched by their NAME and
# their other wordings (T3: "insta id" -> social), never by their text.
# Measured on NFHT: patient questions scored 0.78 to 1.00 against the right fact's name ("clinic name") and at
# most 0.73 against any fact when no fact fits; against name + full text the two overlapped, so the name only.

FACT_MIN = 0.76
FACT_GAP = 0.05  # and clearly closer than the next fact
_facts: dict[str, tuple[float, list[_Row]]] = {}
_fact_wordings: dict[str, list[str]] = {}  # fact id -> its name and other wordings
_fact_vectors: dict[str, list[float]] = {}  # by wording


def fact_text(key: str, value: str) -> str:
    """A fact as the patient sees it. A bare value (an email, a link) gets its name in front."""
    value = value.strip()
    if " " in value:
        return value
    return f"{key.replace('_', ' ').capitalize()}: {value}"


async def _fact_rows(conn: asyncpg.Connection, clinic_id: str) -> list[_Row]:
    now = time.monotonic()
    hit = _facts.get(clinic_id)
    if hit and now - hit[0] < CACHE_S:
        return hit[1]
    rows = []
    for r in await conn.fetch(
        "select id, key, value, variants from app.kb_facts where clinic_id = $1 and status = 'approved'",
        clinic_id,
    ):
        name = r["key"].replace("_", " ")
        said = [name, *[v.strip() for v in r["variants"].splitlines() if v.strip()]]
        keys = tuple(k for k in (words(w) for w in said) if k)
        rows.append(_Row(str(r["id"]), name, fact_text(r["key"], r["value"]), keys))
        _fact_wordings[str(r["id"])] = said
    _facts[clinic_id] = (now, rows)
    return rows


async def fact(conn: asyncpg.Connection, clinic_id: str, text: str) -> Answer | None:
    """The approved fact whose name the question uses ("clinic name", "email id"), if confident."""
    hit = best(await _fact_rows(conn, clinic_id), text)
    return Answer(hit.id, hit.question, hit.answer, hit.score, "fact") if hit else None


async def fact_semantic(
    conn: asyncpg.Connection, clinic_id: str, text: str
) -> tuple[Answer | None, float | None]:
    """The approved fact closest by meaning ("which languages do you speak" -> languages spoken), if close
    enough and clearly ahead of the next one; also the best score, for the trace."""
    if not embed.ready():
        return None, None
    rows = await _fact_rows(conn, clinic_id)
    if not rows:
        return None, None
    ranked = await _fact_scores(await embed.vector(text), rows)
    top, row = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    score = round(top * 100, 1)
    if top >= FACT_MIN and top - second >= FACT_GAP:
        return Answer(row.id, row.question, row.answer, score, "fact"), score
    return None, score


async def _fact_scores(q: list[float], rows: list[_Row]) -> list[tuple[float, _Row]]:
    """Every fact with how close it is to the question, closest first. A fact is as close as its closest
    wording (its name or another wording)."""
    missing = sorted({w for r in rows for w in _fact_wordings[r.id] if w not in _fact_vectors})
    if missing:
        for w, v in zip(missing, await embed.vectors(missing), strict=True):
            _fact_vectors[w] = [float(x) for x in v]
    scored = [(max(_cos(q, _fact_vectors[w]) for w in _fact_wordings[r.id]), r) for r in rows]
    return sorted(scored, key=lambda x: -x[0])


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / ((sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5) or 1.0)


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
