"""Scoring the canvas flow on a clinic's typed-message test sets (scripts/eval_set_*.py), the way
scripts/eval_chat.py scores the live chat: each message, the kind of reply it got, a word it must contain.

Expected kinds: any (answered, never the call back), rule, menu (small talk), start (a booking / cancel ...
begins), noanswer (the call back offer or the medical guard), medical, emergency, lead (nothing known), kb.
"""

from typing import Any

from app.chat.engine import BYE, MAIN_MENU_TEXT, THANKS
from app.crm.flow import LEAD_TYPES

FALLBACK = "Sorry, I didn't get that."


def outcome(flow: dict[str, Any], reply: dict[str, Any]) -> str:
    """What kind of reply the flow gave: emergency, medical, start, menu, lead or answer."""
    nodes = {n["id"]: n for n in flow["nodes"]}
    at = nodes.get(reply["at"] or "", {})
    texts = [m["text"] for m in reply["messages"]]
    buttons = [b["id"] for m in reply["messages"] for b in m.get("buttons", [])]
    welcome = next((n["settings"].get("welcome", "") for n in flow["nodes"] if n["type"] == "opening"), "")
    fallback = next((n["settings"].get("fallback", "") for n in flow["nodes"] if n["type"] == "opening"), "")
    if at.get("type") == "emergency":
        return "emergency"
    if any(b.startswith("medical:") for b in buttons):
        return "medical"
    if at.get("type") in LEAD_TYPES | {"check_appointment"}:
        return "start"
    if texts and texts[0] in {welcome, THANKS, BYE, MAIN_MENU_TEXT} - {""}:
        return "menu"
    if any(t.startswith(FALLBACK) or (fallback and t == fallback) for t in texts):
        return "lead"
    return "answer"


OK = {
    "any": {"answer", "start", "menu", "emergency"},
    "rule": {"answer", "menu"},
    "kb": {"answer"},
    "menu": {"menu"},
    "start": {"start"},
    "noanswer": {"medical", "lead"},
    "lead": {"medical", "lead"},
    "medical": {"medical"},
    "emergency": {"emergency"},
}


# A "start" case's word is the live chat's wording of that flow; on the canvas the block type proves it.
START_WORDS = {
    "book your appointment": "book",
    "online video": "online",
    "cancel": "cancel",
    "reschedule": "reschedule",
}


def passed(flow: dict[str, Any], reply: dict[str, Any], expected: str, word: str) -> tuple[bool, str]:
    """Whether the reply is the kind expected and contains the word (in its text or buttons)."""
    got = outcome(flow, reply)
    if expected == "start" and got == "start" and word.lower() in START_WORDS:
        at: dict[str, Any] = next((n for n in flow["nodes"] if n["id"] == reply["at"]), {})
        return at.get("type") == START_WORDS[word.lower()], got
    seen = " ".join(
        [m["text"] for m in reply["messages"]]
        + [b["label"] for m in reply["messages"] for b in m.get("buttons", [])]
    ).lower()
    ok = got in OK.get(expected, {expected}) and word.lower() in seen
    return ok, got
