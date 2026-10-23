"""T2: what a message is about (bot identity, booking, contact...) from APPROVED example phrases per topic
(app.intent_examples), for messages the keyword rules did not catch: "r u a bot", "kab aa sakta hoon".
Words first (the phrase itself, or a small typo of it), then meaning: each example is compared on its own and
a topic needs a close example AND a clear lead over the next topic. Staff add and approve the phrases; the
bot never adds any by itself.
"""

import time
from dataclasses import dataclass

import asyncpg
import numpy as np
from rapidfuzz import fuzz

from app.chat import embed

CACHE_S = 60  # approved phrases change rarely; a minute keeps CRM edits quick to show
WORDS_MIN = 92  # the phrase itself with a small typo ("r u a bto")
# Measured on CL01 (scripts/eval_chat --big --draft): right topics scored 0.83 to 0.97; "my hair is thinning
# what should i do" (not to be answered) scored 0.827. Medical messages never reach this step.
MEANING_MIN = 0.83
MEANING_GAP = 0.03  # clearly closer to this topic than to any other

# What each topic does in the chat (engine): a reply of its own, a menu topic, or a flow.
SMALL_TALK = {"greeting", "thanks", "bye", "ok"}
STARTS = {"online", "cancel", "reschedule", "callback"}


@dataclass(frozen=True)
class Hit:
    intent: str
    example: str
    score: float
    how: str  # "words" or "meaning"


_rows: dict[str, tuple[float, list[tuple[str, str]]]] = {}
_vectors: dict[str, np.ndarray] = {}  # by example text


def norm(text: str) -> str:
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text.lower()).split())


async def examples(conn: asyncpg.Connection, clinic_id: str) -> list[tuple[str, str]]:
    """(intent, example) for every approved phrase of the clinic."""
    now = time.monotonic()
    hit = _rows.get(clinic_id)
    if hit and now - hit[0] < CACHE_S:
        return hit[1]
    rows = [
        (r["intent"], norm(r["example"]))
        for r in await conn.fetch(
            "select intent, example from app.intent_examples where clinic_id = $1 and status = 'approved'",
            clinic_id,
        )
    ]
    _rows[clinic_id] = (now, rows)
    return rows


def by_words(rows: list[tuple[str, str]], text: str) -> Hit | None:
    """The phrase itself, or a small typo of it, as the whole message."""
    t = norm(text)
    if not t:
        return None
    best: Hit | None = None
    for intent, ex in rows:
        score = 100.0 if t == ex else fuzz.ratio(t, ex)
        if score >= WORDS_MIN and (best is None or score > best.score):
            best = Hit(intent, ex, score, "words")
    return best


async def by_meaning(rows: list[tuple[str, str]], text: str) -> tuple[Hit | None, float | None]:
    """The topic whose closest example is close enough and clearly ahead of every other topic; also the
    best score, for the trace. (None, None) while the model is loading or there are no phrases."""
    if not rows or not embed.ready():
        return None, None
    missing = [ex for _, ex in rows if ex not in _vectors]
    if missing:
        for ex, v in zip(missing, await embed.vectors(missing), strict=True):
            _vectors[ex] = v
    q = np.array(await embed.vector(norm(text)), dtype=np.float32)
    top: dict[str, tuple[float, str]] = {}  # intent -> (best score, its example)
    for intent, ex in rows:
        s = float(_vectors[ex] @ q)
        if intent not in top or s > top[intent][0]:
            top[intent] = (s, ex)
    ranked = sorted(top.items(), key=lambda x: -x[1][0])
    intent, (score, ex) = ranked[0]
    second = ranked[1][1][0] if len(ranked) > 1 else 0.0
    shown = round(score * 100, 1)
    if score >= MEANING_MIN and score - second >= MEANING_GAP:
        return Hit(intent, ex, shown, "meaning"), shown
    return None, shown


async def find(conn: asyncpg.Connection, clinic_id: str, text: str) -> tuple[Hit | None, float | None]:
    rows = await examples(conn, clinic_id)
    hit = by_words(rows, text)
    if hit:
        return hit, hit.score
    return await by_meaning(rows, text)
