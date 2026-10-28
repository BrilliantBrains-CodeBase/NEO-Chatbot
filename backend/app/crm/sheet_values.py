"""A sheet's values shown the CRM's way. Meta lead sheets write ids with a prefix ("l:", "ag:", "p:"), answers
with underscores ("yes,_i_have"), dates in many forms ("2026-08-26T01:26:17-05:00", "26/08/2026") and
true / false. The sheet is never changed: only how a value is shown (and saved on a lead) is cleaned.
"""

import re
from datetime import UTC, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
PREFIX = re.compile(r"^(l|ag|as|c|f|p|ad|adset|form|lead):(?=\S)")  # Meta's id prefixes
PLATFORMS = {
    "fb": "Facebook",
    "ig": "Instagram",
    "msg": "Messenger",
    "an": "Audience Network",
    "wa": "WhatsApp",
}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")


def when(text: str, order: str | None = None) -> datetime | None:
    """A date (and time) written any common way, as India time; None when it is not a date.
    order: "dmy" (26/08/2026, the Indian way) or "mdy" (08/26/2026) for numbers that could be either."""
    t = text.strip()
    if ISO.match(t):
        d = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=IST)).astimezone(IST)
    m = re.fullmatch(
        r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})(?:[ ,T]+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([ap]m)?)?", t, re.I
    )
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        y += 2000 if y < 100 else 0
        day, month = (b, a) if order == "mdy" or (order is None and b > 12) else (a, b)
        h, mi, s = int(m[4] or 0), int(m[5] or 0), int(m[6] or 0)
        if m[7]:
            h = h % 12 + (12 if m[7].lower() == "pm" else 0)
        try:
            return datetime(y, month, day, h, mi, s, tzinfo=IST)
        except ValueError:
            return None
    for fmt in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%d %b %Y %H:%M", "%d %b %Y %I:%M %p"):
        try:
            return datetime.strptime(t, fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def phone(text: str) -> str | None:
    """+91 81234 62595 from "p:+918123462595", "918123462595", "08123462595" or "81234 62595"."""
    digits = re.sub(r"\D", "", PREFIX.sub("", text.strip()))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if re.fullmatch(r"[6-9]\d{9}", digits):
        return f"+91 {digits[:5]} {digits[5:]}"
    raw = PREFIX.sub("", text.strip())
    return raw if re.fullmatch(r"\+\d{7,15}", raw.replace(" ", "")) else None


def shown(text: str) -> str:
    """The value as the CRM shows it (the sheet keeps its own)."""
    t = str(text).strip()
    if not t:
        return ""
    d = when(t) if ISO.match(t) else None
    if d:
        return d.strftime("%d %b %Y, %I:%M %p")
    if t.lower() in ("true", "false"):
        return "Yes" if t.lower() == "true" else "No"
    if t.lower() in PLATFORMS:
        return PLATFORMS[t.lower()]
    if t.startswith("p:"):
        return phone(t) or t[2:]
    t = PREFIX.sub("", t)
    if "_" in t and " " not in t and "@" not in t:
        t = t.replace(",_", ", ").replace("_", " ")
        t = re.sub(r"\bi\b", "I", t)
    return t


def now_utc() -> datetime:
    return datetime.now(UTC)
