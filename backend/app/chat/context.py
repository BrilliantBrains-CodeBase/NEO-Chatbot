"""The conversation so far (C1). Before deciding, the bot reads what came before: the last messages, the
treatment being talked about and its own last reply. So a follow-up is understood from the chat:
"how long?" after PRP is "how long PRP", "and for beard?" repeats the last question for beards, and
"tell me more" after a list shows that list again. Rules only; the LLM step (C2) reads the same memory.
"""

import re
from typing import Any

from app.chat.schemas import ChatRequest, Payload
from app.chat.understand import small_talk

HISTORY = 5  # messages kept (patient and bot), newest last
MEMORY = ("history", "topic", "last_q", "last_ui")  # carried from turn to turn by the service

# A message that only asks for more, with no subject of its own: the whole message.
VAGUE = re.compile(
    r"(i )?(want|need|would like)( to (know|see|hear))? more( (info|information|details?|about it))?|"
    r"(tell|show|give) me more( (info|information|details?|about (it|this|that)))?|"
    r"more( please| pls| info| information| details?)?|(any )?(more|other|another) (options?|ones?)|"
    r"(something|anything) else|what else|others?|explain( (it|this|that|more))?|details?( please| pls)?|"
    r"go on|continue|and( then)?|aur( batao| bataiye| bolo)?|aur kuch|detail (me|mein) batao|samjhao"
)
VAGUE_END = re.compile(r"[?.! ]+$")
# Words that mean the message is about the subject already in the chat.
POINTER = re.compile(r"\b(it|its|this|that|these|those|same|the procedure|the treatment)\b")
# A short question about a detail of a treatment ("cost?", "how long", "recovery?") with no subject named.
# Not general words like "time" or "open": "what time do you close" is about the clinic, not the topic.
DETAIL = re.compile(
    r"\b(cost|price|fees?|charges?|how much|emi|rates?|how long|duration|how many (days|sessions)|"
    r"sessions?|results?|recovery|permanent|before and after|process|procedure|steps|kitna|kitne)\b"
)
# "and for beard?", "what about PRP", "same for eyebrows": the last question again for another treatment.
SWITCH = re.compile(r"^(and|what about|how about|same for|for|what for|aur)\b")
SHORT = 6  # words: longer messages are full questions and are read as they are


def norm(text: str) -> str:
    return " ".join(text.lower().split())


def treatment_in(text: str, c: dict[str, Any]) -> tuple[str, str] | None:
    """(treatment, words that named it) for the first treatment named in the text."""
    low = norm(text)
    for name in c["treatments"]:
        if name.lower() in low:
            return name, name.lower()
    for alias, name in c["aliases"].items():
        m = re.search(rf"\b{alias}\b", low)
        if m:
            return name, m.group(0)
    return None


def is_vague(text: str) -> bool:
    return bool(VAGUE.fullmatch(VAGUE_END.sub("", norm(text))))


def resolve(text: str, state: dict[str, Any], c: dict[str, Any]) -> str:
    """The question the patient means, with the subject from the chat filled in. Unchanged when the message
    already names a treatment (and is not a switch), is long, or nothing came before."""
    low = norm(text)
    words = len(low.split())
    named = treatment_in(low, c)
    last_q = state.get("last_q")
    if named and last_q and words <= SHORT and SWITCH.match(low):
        return f"{last_q} {named[0]}"
    topic = state.get("topic")
    if named or not topic or words > SHORT:
        return text
    if DETAIL.search(low) or POINTER.search(low):
        return f"{text} {topic}"
    return text


def without_treatment(text: str, c: dict[str, Any]) -> str:
    """The question with its treatment taken out, so it can be asked again for another one."""
    low = norm(text)
    while named := treatment_in(low, c):
        low = norm(low.replace(named[1], " "))
    return low


def as_text(req: ChatRequest) -> ChatRequest:
    """A button that asks a question (action "ask", the question as its value) is handled as that typed
    question."""
    p = req.payload
    if req.event == "button" and p.action == "ask" and p.value:
        return req.model_copy(update={"event": "text", "payload": Payload(text=p.value)})
    return req


def topic_of(req: ChatRequest, resolved: str, c: dict[str, Any]) -> str | None:
    """The treatment this turn is about, if any."""
    p = req.payload
    if req.event == "button" and p.action in ("treat", "book_for") and p.value in c["treatments"]:
        return p.value
    if req.event == "text":
        named = treatment_in(resolved, c)
        return named[0] if named else None
    return None


def remember(
    old: dict[str, Any], new: dict[str, Any], req: ChatRequest, said: str | None, bot: list[str],
    ui: dict[str, Any] | None, answered_by: str, resolved: str, c: dict[str, Any],
) -> None:  # fmt: skip
    """Carry the memory into the new state. A (re)start forgets everything but the menu it shows."""
    if req.event in ("start", "restart"):
        new["last_ui"] = ui
        return
    for key in MEMORY:
        if key in old and key not in new:
            new[key] = old[key]
    history = list(new.get("history", []))
    if said:
        history.append({"who": "patient", "text": said[:300]})
    if bot:
        history.append({"who": "bot", "text": " ".join(bot)[:300]})
    new["history"] = history[-HISTORY:]
    topic = topic_of(req, resolved, c)
    if topic:
        new["topic"] = topic
    new["topic_now"] = topic  # only this turn's: "tell me more" is about it
    if req.event == "text" and answered_by in ("kb", "rule") and not is_vague(resolved):
        new["last_q"] = without_treatment(resolved, c)
    new["last_ui"] = ui


# --- The workflow canvas (the live chat): the last messages, for follow-ups the Knowledge base answers ------

TURNS = 6  # messages kept: the last 3 from the patient and the bot's 3 replies


def keep(history: list[dict[str, str]], patient: str | None, bot: str) -> list[dict[str, str]]:
    """The chat so far with this turn added (the last TURNS messages)."""
    new = [*history, *([{"who": "patient", "text": patient}] if patient else []), {"who": "bot", "text": bot}]
    return [m for m in new if m["text"].strip()][-TURNS:]


def follow_up(text: str, history: list[dict[str, str]]) -> str | None:
    """A short follow-up read with the patient's question before it ("and Sunday?" after "what are your
    timings" -> "what are your timings sunday"; "tell me more" -> the question again). None when the message
    is not a follow-up, is long enough to stand alone, or nothing came before."""
    low = norm(text).strip(" ?.!")
    before = [m["text"] for m in history if m["who"] == "patient"][-3:]
    if not before or not low or len(low.split()) > SHORT:
        return None
    if small_talk(low) is not None:  # "ok", "thanks", "hi": not a question about what came before
        return None
    last = before[-1]
    if is_vague(text):
        return last
    if SWITCH.match(low) or POINTER.search(low) or DETAIL.search(low) or len(low.split()) <= 3:
        rest = SWITCH.sub("", low).strip()
        return f"{last} {rest}".strip() if rest else last
    return None
