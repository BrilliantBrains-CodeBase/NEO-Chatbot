"""Understanding typed text: dates, times, yes, main menu, button labels (with typos), and the keyword
rules (emergency first, medical never answered). Same rules as the approved mock
(frontend/widgets/mock/typing.ts and router.ts). Knowledge base search and the LLM come later.
"""

import re
from datetime import date, timedelta
from typing import Any

from rapidfuzz.distance import OSA, Levenshtein


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def is_menu(text: str) -> bool:
    return bool(re.fullmatch(r"main menu|menu|home|start over|go to menu", norm(text)))


def is_yes(text: str) -> bool:
    return bool(
        re.fullmatch(
            r"yes|y|yeah|yep|ok|okay|confirm|confirmed|confirm it|book it|go ahead|sure|done|correct",
            norm(text),
        )
    )


MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]


def _ymd(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def _with_year(m: int, d: int, today: date) -> str | None:
    """A date without a year: this year's, or next year's when that is closer (e.g. "2 Jan" in December)."""
    this, nxt = _ymd(today.year, m, d), _ymd(today.year + 1, m, d)
    if not this or not nxt:
        return None
    return this if this >= (today - timedelta(days=180)).isoformat() else nxt


def _month(word: str) -> int:
    return MONTHS.index(word[:3]) + 1 if word[:3] in MONTHS else 0


def parse_date(text: str, today: date) -> str | None:
    """today, tomorrow, friday, 28 oct, oct 28, 28/10, 28-10-2026, 2026-10-28. Day first (India)."""
    t = norm(text)
    if t == "today":
        return today.isoformat()
    if t in ("tomorrow", "tmrw", "tmr"):
        return (today + timedelta(days=1)).isoformat()
    if t == "day after tomorrow":
        return (today + timedelta(days=2)).isoformat()
    if m := re.fullmatch(r"(?:next |this |on )?(sun|mon|tue|wed|thu|fri|sat)[a-z]*", t):
        target, now = DAYS.index(m[1]), (today.weekday() + 1) % 7
        return (today + timedelta(days=(target - now) % 7)).isoformat()
    if m := re.fullmatch(r"(\d{4}) (\d{1,2}) (\d{1,2})", t):
        return _ymd(int(m[1]), int(m[2]), int(m[3]))
    if m := re.fullmatch(r"(\d{1,2}) (\d{1,2})(?: (\d{2}|\d{4}))?", t):
        if not m[3]:
            return _with_year(int(m[2]), int(m[1]), today)
        year = 2000 + int(m[3]) if len(m[3]) == 2 else int(m[3])
        return _ymd(year, int(m[2]), int(m[1]))
    if (m := re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?(?: of)? ([a-z]{3,9})(?: (\d{4}))?", t)) and _month(
        m[2]
    ):
        return (
            _ymd(int(m[3]), _month(m[2]), int(m[1])) if m[3] else _with_year(_month(m[2]), int(m[1]), today)
        )
    if (m := re.fullmatch(r"([a-z]{3,9}) (\d{1,2})(?:st|nd|rd|th)?(?: (\d{4}))?", t)) and _month(m[1]):
        return (
            _ymd(int(m[3]), _month(m[1]), int(m[2])) if m[3] else _with_year(_month(m[1]), int(m[2]), today)
        )
    return None


def parse_time(text: str) -> str | None:
    """10:30, 10.30 am, 2 pm, 14:15, noon, any time. Without am/pm, 1 to 8 means afternoon or evening."""
    raw = text.lower().strip()
    if re.fullmatch(r"any ?time|anytime|any", raw):
        return "any"
    if raw == "noon":
        return "12:00"
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", raw)
    if not m:
        return None
    h, mins, ampm = int(m[1]), int(m[2] or 0), (m[3] or "").replace(".", "")
    if h > 23 or mins > 59 or (ampm and not 1 <= h <= 12):
        return None
    if ampm == "pm" and h < 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    if not ampm and 1 <= h <= 8:
        h += 12
    return f"{h:02d}:{mins:02d}"


def match_option(text: str, options: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The button meant: same label, a small typo (about 1 in 6 letters), or a part of the label (4+ letters)
    that fits only one button. Links are never matched."""
    t = norm(text)
    usable = [o for o in options if o.get("action")]
    if len(t) < 2 or not usable:
        return None
    for o in usable:
        if norm(o["label"]) == t:
            return o
    close = [o for o in usable if Levenshtein.distance(norm(o["label"]), t) <= max(1, len(t) // 6)]
    if len(close) == 1:
        return close[0]
    if len(t) >= 4:
        part = [o for o in usable if t in norm(o["label"])]
        if len(part) == 1:
            return part[0]
    return None


# ---------- keyword rules (priority order) ----------

EMERGENCY = re.compile(
    r"\b(emergency|bleed(ing)?|faint(ed|ing)?|unconscious|can'?t breathe|breathing (problem|difficulty)|chest pain|"
    r"allergic|anaphyla\w*|severe (swelling|pain)|high fever)\b"
)
# Healthcare and medicine questions are never answered (client decision): they always become a lead.
MEDICAL = re.compile(
    r"\b(medicines?|medication|tablets?|pills?|doses?|dosage|side ?effects?|safe for me|suitab\w*|candidate|eligib\w*|how many grafts|right for me|"
    r"is it normal|minoxidil|finasteride|biotin|steroids?|diabet\w*|blood pressure|thyroid|pregnan\w*|pain(ful)?|"
    r"itch(y|ing)?|rash|infection|swelling|diagnos\w*|symptoms?|cure[ds]?|hurts?|hurting|risks?|"
    # the cause of this patient's problem, or whether it is normal: a diagnosis
    r"why (is|are|am|do|does|did) (my|i)|is (my|this|it) [a-z ]{0,25}normal|"
    # suitability: what this patient should have
    r"should i (get|go for|take|do|use|try)|should i choose (?!you|your|neo|this clinic)|"
    r"do i need (a |an )?(transplant|surgery|prp|gfc|qr678|exosomes?|treatment|grafts?)|"
    r"(best|better|right) for me|which (one|treatment) (is|should)|"
    r"which (shampoo|oil|serum|vitamins?|supplements?) should|"
    # aftercare: what to do before or after the procedure
    r"(alcohol|drink\w*|smok\w*|wash\w*|shampoo\w*|gym|exercise|workout|swim\w*|helmet|sleep\w*|diet|sex)\b.*\b"
    r"(after|before) (the |my |a )?(surgery|transplant|procedure|prp|gfc|treatment|session)|"
    r"(after|before) (the |my |a )?(surgery|transplant|procedure|prp|gfc|treatment|session)\b.*\b"
    r"(alcohol|drink\w*|smok\w*|wash\w*|shampoo\w*|gym|exercise|workout|swim\w*|helmet|sleep\w*|diet|sex))\b"
)
# Saying no to a form question ("no", "skip", "not now"): the whole message, so "no 98..." is not caught.
REFUSAL = re.compile(
    r"^(no|nope|nah|na|no thanks|no thank you|not now|later|skip|cancel|stop|leave it|not interested|"
    r"(i )?(don'?t|do not) want( to)?( share| give)?( it)?|nahi|nahin|nai|rehne do|mat)[.! ]*$"
)
# Words no name has: at the name step, "clinic location" is a question, not a patient called "Clinic".
NOT_A_NAME = re.compile(
    r"\b(clinic|location|address|where|what|when|why|how|which|timings?|hours|open|cost|price|fees?|charges?|"
    r"emi|book\w*|appointment|consult\w*|treatments?|transplant|hair|prp|gfc|beard|eyebrows?|doctor|parking|"
    r"results?|offer|available|tell|more|info|details?|help|menu|call|number|phone|whatsapp|need|want)\b"
)

# Asking for every treatment ("more treatments", "all your services", "list of treatments"), not their cost.
ALL_TREATMENTS = re.compile(
    r"^(?!.*\b(cost|price|fees?|charges?)\b).*("
    r"\b(all|more|other|full|complete|entire|rest of( the)?)\b[a-z ]{0,20}\b(treatments?|services|procedures)\b|"
    r"\blist of (treatments?|services|procedures)\b|\bhow many (treatments?|services)\b)"
)
# Asking whether a list is complete ("only 4 or more?", "is that all?", "any others?"): about the last list.
MORE_OF_LIST = re.compile(
    r"^(only (\d+|these|this|that|four|five)|(is|are) (that|these|this) (all|it|the only)|that'?s all|"
    r"any (more|others?)|(\d+|four|five) (only|or more))\b|\bor more\W*$"
)

# Small talk: the whole message only, so "hi, what does PRP cost?" is still a question.
SMALL_TALK: list[tuple[str, re.Pattern[str]]] = [
    (
        "greeting",
        re.compile(
            r"^(hi+|hey+|hello+|helo|hlo|namaste|namaskar|good (morning|afternoon|evening))( there| arya)?[!. ]*$"
        ),
    ),
    (
        "thanks",
        re.compile(
            r"^(thanks?|thank (you|u)|thx|ty|dhanyavad|shukriya|great thanks)( a lot| so much| very much)?[!. ]*$"
        ),
    ),
    ("bye", re.compile(r"^(bye+|bye bye|good ?bye|see (you|ya)|take care|tata)[!. ]*$")),
    ("ok", re.compile(r"^(ok+|okay|fine|cool|alright|got it|hmm+|sure|great|nice)[!. ]*$")),
]


def small_talk(text: str) -> str | None:
    return next((name for name, pattern in SMALL_TALK if pattern.match(text)), None)


# Questions about the bot itself.
IDENTITY = re.compile(
    r"\b(who are you|what are you|who is this|who am i (talking|chatting) (to|with)|"
    r"are you an? (bot|robot|human|real person|person|ai)|are you (a )?(bot|robot|human|real|ai)|"
    r"what'?s your name|what is your name|your name|"
    r"(human|person|bot|robot|ai|machine|real)( or | ya |/)(human|person|bot|robot|ai|machine|real)|"
    r"(is this|am i (talking|chatting|speaking) (to|with)) (an? )?(bot|robot|human|real person|person|ai|machine)|"
    r"(real|actual) (person|human)|chatbot)\b"
)

INTENTS: list[tuple[re.Pattern[str], tuple[str, str]]] = [
    # "online" alone is not a video consultation: "estimate online", "online hair test" are other things.
    (
        re.compile(
            r"^(?!.*\b(estimates?|calculator|cost|price|assessment|analysis|test|brochure)\b)"
            r".*\b(online|video( ?call| consult\w*)?|from home|google meet|virtual)\b"
        ),
        ("start", "online"),
    ),
    (re.compile(r"\bcancel"), ("start", "cancel")),
    (
        re.compile(
            r"\b(reschedul\w*|postpone|(change|move|shift|push) (my |the )?(appointment|booking|date|slot|visit))\b"
        ),
        ("start", "reschedule"),
    ),
    (re.compile(r"\b(call ?back|callback|call me back)\b"), ("start", "callback")),
    (
        re.compile(
            r"\b(cost|price|fees?|charges?|package|emi|how much|rates?|kharcha|lagega|"
            r"kitna (hoga|paisa|lagta)|kitne (ka|ki|ke|paise|rupaye))\b"
        ),
        ("node", "cost"),
    ),
    # A clear wish to book starts the in-clinic booking at once ("I want to book an appointment"); the word
    # "consultation" alone may be a question about it ("what is included in the consultation").
    (re.compile(r"\b(book\w*|appointment|slots?)\b"), ("start", "book")),
    (re.compile(r"\bconsult\w*\b"), ("node", "book")),
    # Photos to be checked or sent are not the results gallery.
    (
        re.compile(
            r"^(?!.*\b(check|assess\w*|analy\w*|send|share|upload|privacy|private)\b)"
            r".*\b(results?|before and after|before after|gallery|photos?)\b"
        ),
        ("node", "results"),
    ),
    (
        re.compile(
            r"\b(timings?|hours|open|opening|closed?|address|adres+|location|where|directions?|map|landmark|"
            r"kahan|floor|pin ?code|holiday|weekly off|working days|kitne baje|khul\w*|band (hota|hoti|rehta))\b"
        ),
        ("node", "clinic"),
    ),
    # "talk in kannada", "gst number" are not a wish to call: only contact words and asking to talk to us.
    (
        re.compile(
            r"\b(call( me)?|whatsapp|contact|(phone|mobile|contact|clinic|your|whatsapp) (number|no)|phone|"
            r"(talk|speak) (to|with) (someone|a human|a person|the team|your team|you|the doctor|doctor))\b"
        ),
        ("node", "talk"),
    ),
    (re.compile(r"\b(doctors?|dr|sandeep|surgeons?)\b"), ("node", "about")),
    (re.compile(r"\b(international|abroad|overseas|travel|fly|nri)\b"), ("node", "intl")),
]


# Long action words patients often misspell ("reschudle", "apointment"). Only words of 7+ letters, so short
# words are never changed ("cancer" must not become "cancel"); misspellings of "cancel" are listed instead.
SPELLED = ["reschedule", "appointment", "consultation", "emergency", "treatment", "transplant", "location",
           "callback", "postpone", "timings"]  # fmt: skip
CANCEL_TYPOS = re.compile(r"\b(cancle|cansel|cancell|cancl|cencel|cancal)\b")


def spelled(text: str) -> str:
    """The text with misspelled action words written correctly (1 wrong letter in 7-8 letters, 2 in longer)."""
    text = CANCEL_TYPOS.sub("cancel", text)
    words = text.split(" ")
    for i, w in enumerate(words):
        if len(w) < 7 or w in SPELLED:
            continue
        near = [s for s in SPELLED if OSA.distance(w, s) <= (1 if len(w) < 9 else 2)]
        if len(near) == 1:
            words[i] = near[0]
    return " ".join(words)


def route(raw: str, c: dict[str, Any]) -> tuple[str, str]:
    """("emergency", ""), ("lead", ""), ("start", kind), ("node", key) or ("card", treatment)."""
    text = spelled(" ".join(raw.lower().split()))
    if EMERGENCY.search(text):
        return "emergency", ""
    if MEDICAL.search(text):
        return "lead", ""
    for pattern, target in INTENTS:
        if pattern.search(text):
            return target
    for name in c["treatments"]:
        if name.lower() in text:
            return "card", name
    for alias, name in c["aliases"].items():
        if re.search(rf"\b{alias}\b", text):
            return "card", name
    if re.search(r"\b(treatments?|explore|options|services)\b", text):  # not "procedure": that is the surgery
        return "node", "treat"
    return "lead", ""
