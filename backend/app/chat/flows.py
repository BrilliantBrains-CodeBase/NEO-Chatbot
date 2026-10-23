"""Step-by-step flows: booking (in-clinic, online), cancel, reschedule, call back, and lead capture for
questions the bot cannot answer. Same wording and checks as the approved mock
(frontend/widgets/mock/engine.ts). Every value is validated here, on the server.

B3b: slots come from the clinic hours. B5 adds doctor availability and existing bookings; B6 saves leads.
"""

import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.chat.schemas import BotMessage, ChatResponse, Input

# The clinic clock (India time). Tests replace it to check date and slot rules at a fixed time.
clock: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731

IST = timedelta(hours=5, minutes=30)
CONSENT = "By confirming, you agree to be contacted by phone, WhatsApp or email."
NAME_INPUT = Input(mode="text", placeholder="Your full name")
NOT_AVAILABLE_DATE = "That date is not available. Please choose another date."
NOT_AVAILABLE_TIME = "That time is not available. Please choose one of the times shown."
PHONE_INPUT = Input(mode="phone", placeholder="Mobile number")
EMAIL_INPUT = Input(mode="email", placeholder="name@example.com")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

INTRO = {
    "book": "Sure, let's book your appointment. May I know your full name?",
    "online": "Sure, let's book your online video consultation. May I know your full name?",
    "cancel": "Sure, I can help you cancel your appointment. May I know your full name?",
    "reschedule": "Sure, I can help you reschedule your appointment. May I know your full name?",
    "callback": "Sure, I can arrange a callback. May I know your full name?",
    "question": "May I know your full name?",
}
NO_ANSWER = (
    "I don't have a confirmed answer for that yet. Share your number and our team will call you back "
    "with the right information."
)

Flow = dict[str, Any]

# ---------- validation (the same rules as the widget mock) ----------

NAME = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ .'\-])*[^\W\d_]$")
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def valid_name(s: str) -> bool:
    return bool(NAME.match(s.strip()))


def normal_phone(text: str, cc: str | None) -> str | None:
    cc = cc or "+91"
    digits = re.sub(r"[\s()\-]", "", text)
    ok = re.fullmatch(r"[6-9]\d{9}", digits) if cc == "+91" else re.fullmatch(r"\d{6,12}", digits)
    return f"{cc} {digits}" if ok else None


def first_name(name: str) -> str:
    return name.strip().split()[0]


# ---------- dates and slots ----------


def ist_now() -> tuple[date, int]:
    now = clock().astimezone(UTC) + IST
    return now.date(), now.hour * 60 + now.minute


def fmt_date(d: str) -> str:
    x = date.fromisoformat(d)
    return f"{x.day} {MONTHS[x.month - 1]} {x.year}"


def fmt_time(hm: str) -> str:
    h, m = (int(p) for p in hm.split(":"))
    return f"{(h + 11) % 12 + 1}:{m:02d} {'AM' if h < 12 else 'PM'}"


def weekday(d: str) -> int:
    return (date.fromisoformat(d).weekday() + 1) % 7  # 0 = Sunday, like the widget


def slots_for(cfg: dict[str, Any], d: str) -> list[str]:
    if "slots_by_day" in cfg:  # real free slots from the database (loaded by the service)
        return list(cfg["slots_by_day"].get(d, []))
    # Without the database (pure tests): every slot inside clinic hours.
    if weekday(d) in cfg["closedWeekdays"]:
        return []
    today, minutes = ist_now()
    out = []
    for m in range(cfg["firstSlot"], cfg["lastSlot"] + 1, cfg["slotMinutes"]):
        if d != today.isoformat() or m > minutes:
            out.append(f"{m // 60:02d}:{m % 60:02d}")
    return out


def new_range(cfg: dict[str, Any]) -> tuple[str, str, str]:
    today, _ = ist_now()
    t = today.isoformat()
    first = t if slots_for(cfg, t) else (today + timedelta(days=1)).isoformat()
    return t, first, (today + timedelta(days=cfg["bookingWindowDays"])).isoformat()


def booked_range(cfg: dict[str, Any]) -> tuple[str, str, str]:
    today, _ = ist_now()
    return (
        today.isoformat(),
        (today - timedelta(days=cfg["bookedDateBackDays"])).isoformat(),
        (today + timedelta(days=cfg["bookingWindowDays"])).isoformat(),
    )


def bookable(cfg: dict[str, Any], d: str) -> bool:
    _, lo, hi = new_range(cfg)
    return lo <= d <= hi and bool(slots_for(cfg, d))


def valid_booked_date(cfg: dict[str, Any], d: str) -> bool:
    _, lo, hi = booked_range(cfg)
    return lo <= d <= hi and weekday(d) not in cfg["closedWeekdays"]


def is_date(v: str | None) -> bool:
    try:
        date.fromisoformat(v or "")
        return True
    except ValueError:
        return False


# ---------- replies ----------


def reply(texts: list[str], ui: dict[str, Any] | None = None, inp: Input | None = None) -> ChatResponse:
    return ChatResponse(messages=[BotMessage(text=t) for t in texts], ui=ui, input=inp or Input())


def calendar(cfg: dict[str, Any], action: str, booked: bool = False) -> dict[str, Any]:
    today, lo, hi = booked_range(cfg) if booked else new_range(cfg)
    return {"type": "month_calendar", "action": action, "today": today, "min": lo, "max": hi,
            "closed_weekdays": cfg["closedWeekdays"]}  # fmt: skip


DONE = {
    "type": "chips",
    "options": [
        {"label": "Main menu", "action": "menu"},
        {"label": "Talk to us", "action": "go", "value": "talk"},
    ],
}


def ask(f: Flow, cfg: dict[str, Any], lead: list[str] | None = None) -> ChatResponse:
    lead = lead or []
    step = f["step"]
    if step == "name":
        return reply([*lead, "May I know your full name?"], None, NAME_INPUT)
    if step == "phone":
        return reply(
            [*lead, f"Thanks, {first_name(f['name'])}. What is your contact number?"], None, PHONE_INPUT
        )
    if step == "email":
        return reply([*lead, "What is your email address?"], None, EMAIL_INPUT)
    if step == "treatment":
        opts = [{"label": t, "action": "treatment", "value": t} for t in cfg["treatments"]]
        return reply([*lead, "Which treatment are you looking for?"], {"type": "chips", "options": opts})
    if step == "reason":
        return reply(
            [*lead, "Please tell us briefly what you are looking for."],
            None,
            Input(placeholder="Short reason"),
        )
    if step == "cb_reason":
        return reply(
            [*lead, "What would you like to discuss on the call?"],
            None,
            Input(placeholder="Reason for the call"),
        )
    if step == "booked_date":
        return reply(
            [*lead, "Which date is your appointment booked for?"], calendar(cfg, "booked_date", True)
        )
    if step == "date":
        text = (
            "Which new date would you prefer?" if f["kind"] == "reschedule" else "Which date works for you?"
        )
        return reply([*lead, text], calendar(cfg, "date"))
    if step == "time":
        text = (
            "And what new time would you prefer?"
            if f["kind"] == "reschedule"
            else "What time would you prefer?"
        )
        ui = {
            "type": "time_grid",
            "action": "time",
            "slots": slots_for(cfg, f["date"]),
            "first": 4,
            "any_time": True,
        }
        return reply([*lead, text], ui)
    return summary(f, lead)


def treatment_text(f: Flow) -> str:
    return str(f["reason"] if f.get("treatment") == "Other" and f.get("reason") else f["treatment"])


def when_text(f: Flow) -> str:
    d = fmt_date(f["date"])
    return f"{d}, any time" if f["time"] == "any" else f"{d} at {fmt_time(f['time'])}"


def summary(f: Flow, lead: list[str]) -> ChatResponse:
    visit = "Online video consultation (Google Meet)" if f["kind"] == "online" else "In-clinic visit"
    lines = ["Please check your details:", f"**{f['name']}**", f["phone"], f["email"], treatment_text(f), visit,
             when_text(f), f"**{CONSENT}**"]  # fmt: skip
    options = [
        {"label": "Confirm booking", "action": "confirm"},
        {"label": "Change treatment", "action": "change_treatment"},
        {"label": "Change date and time", "action": "change_datetime"},
        *(
            [{"label": "Switch to in-clinic visit", "action": "switch_inclinic"}]
            if f["kind"] == "online"
            else []
        ),
        {"label": "Start again", "action": "start_again"},
    ]
    return reply([*lead, "\n".join(lines)], {"type": "chips", "options": options})


def confirmed(f: Flow) -> ChatResponse:
    d = fmt_date(f["date"])
    when = f"on {d} (any time)" if f["time"] == "any" else f"on {when_text(f)}"
    if f["kind"] == "online":
        text = (
            f"Your online consultation request for **{treatment_text(f)}** {when} is received. You will get the "
            "Google Meet link on WhatsApp and email once the clinic confirms."
        )
    else:
        text = f"Your appointment request for **{treatment_text(f)}** {when} is received."
    return reply([text], DONE)


def ended(f: Flow) -> ChatResponse:
    """The closing message of cancel, reschedule, call back and lead capture."""
    name = first_name(f["name"])
    if f["kind"] == "cancel":
        text = (
            f"Thanks, {name}. Your request to cancel the appointment on **{fmt_date(f['booked_date'])}** is received. "
            f"Our team will contact you on {f['phone']} to confirm the cancellation."
        )
    elif f["kind"] == "reschedule":
        to = f"{fmt_date(f['date'])} (any time)" if f["time"] == "any" else when_text(f)
        text = (
            f"Thanks, {name}. Your request to move your appointment from **{fmt_date(f['booked_date'])}** to "
            f"**{to}** is received. Our team will contact you on {f['phone']} to confirm the new slot."
        )
    elif f["kind"] == "callback":
        text = (
            f"Thanks, {name}. Our team will call you on {f['phone']} "
            f"about **{f['reason']}** during clinic hours."
        )
    else:
        text = f"Thanks, {name}. Our team will contact you on {f['phone']}."
    return reply([text], DONE)


# ---------- moving through the steps ----------


def start(
    kind: str, reason: str | None = None, treatment: str | None = None, lead: list[str] | None = None
) -> tuple[Flow, ChatResponse]:
    f: Flow = {"kind": kind, "step": "name", "reason": reason, "treatment": treatment}
    return f, reply([*(lead or []), INTRO[kind]], None, NAME_INPUT)


def _advance(f: Flow, cfg: dict[str, Any], nxt: str) -> ChatResponse:
    f["step"] = "summary" if f.get("back_to_summary") and nxt != "time" else nxt
    if f["step"] == "summary":
        f["back_to_summary"] = False
    return ask(f, cfg)


def _pick_treatment(f: Flow, cfg: dict[str, Any], t: str) -> ChatResponse:
    f["treatment"] = t
    if t == "Other":
        f["step"] = "reason"
        return ask(f, cfg)
    f["reason"] = None
    return _advance(f, cfg, "date")


def typed(f: Flow, cfg: dict[str, Any], text: str, cc: str | None) -> tuple[Flow | None, ChatResponse]:
    """Typed text while a step is open. Returns the flow (None when it has ended) and the reply."""
    value, step = text.strip(), f["step"]
    if step == "name":
        if not valid_name(value):
            return f, reply(["Please enter your full name."], None, NAME_INPUT)
        f["name"] = " ".join(value.split())
        return f, _advance(f, cfg, "phone")
    if step == "phone":
        phone = normal_phone(value, cc)
        if not phone:
            return f, reply(
                ["That number does not look right. Please check and enter it again."], None, PHONE_INPUT
            )
        f["phone"] = phone
        if f["kind"] in ("cancel", "reschedule"):
            return f, _advance(f, cfg, "booked_date")
        if f["kind"] == "callback":
            return (None, ended(f)) if f.get("reason") else (f, _advance(f, cfg, "cb_reason"))
        return f, _advance(f, cfg, "email")
    if step == "email":
        if not EMAIL.match(value):
            return f, reply(["Please enter a valid email address."], None, EMAIL_INPUT)
        f["email"] = value.lower()
        if f["kind"] == "question":
            return None, ended(f)
        return f, _advance(f, cfg, "date" if f.get("treatment") else "treatment")
    if step in ("reason", "cb_reason"):
        if len(value) < 3:
            placeholder = "Short reason" if step == "reason" else "Reason for the call"
            return f, reply(["Please add a few more words."], None, Input(placeholder=placeholder))
        f["reason"] = value
        return (f, _advance(f, cfg, "date")) if step == "reason" else (None, ended(f))
    match = next((t for t in cfg["treatments"] if t.lower() == value.lower()), None)
    if step == "treatment" and match:
        return f, _pick_treatment(f, cfg, match)
    return f, ask(f, cfg)  # questions in the middle of a flow: B4


def button(f: Flow, cfg: dict[str, Any], action: str, value: str | None) -> tuple[Flow | None, ChatResponse]:
    """A tap that belongs to the open flow. Earlier pickers stay usable, so they work from any step,
    but only in the flows they belong to (a date tap never moves a call back into booking)."""
    booking = f["kind"] in ("book", "online")
    if (
        action in ("treatment", "confirm", "change_treatment", "change_datetime", "switch_inclinic")
        and not booking
    ) or (action in ("date", "time") and not (booking or f["kind"] == "reschedule")):
        return f, ask(f, cfg)
    if action == "confirm" and f["step"] == "summary":
        return None, confirmed(f)
    if action == "treatment":
        if value is None or value not in cfg["treatments"]:
            return f, ask(f, cfg)
        return f, _pick_treatment(f, cfg, value)
    if action == "booked_date" and f["kind"] in ("cancel", "reschedule"):
        if not is_date(value) or not valid_booked_date(cfg, value or ""):
            return f, ask(f, cfg)
        f["booked_date"] = value
        if f["kind"] == "cancel":
            return None, ended(f)
        if f["step"] == "booked_date":
            f["step"] = "date"
        return f, ask(f, cfg)
    if action == "date":
        if f["step"] == "booked_date" or not is_date(value):
            return f, ask(f, cfg)
        if not bookable(cfg, value or ""):  # e.g. fully booked since the calendar was shown
            return f, ask(f, cfg, [NOT_AVAILABLE_DATE])
        f["date"], f["time"], f["step"] = value, None, "time"
        return f, ask(f, cfg)
    if action == "time":
        if not f.get("date"):
            return f, ask(f, cfg)
        if value != "any" and value not in slots_for(cfg, f["date"]):  # just taken by someone else
            return f, ask(f, cfg, [NOT_AVAILABLE_TIME])
        f["time"] = value
        if f["kind"] == "reschedule":
            return None, ended(f)
        return f, _advance(f, cfg, "summary")
    if action == "change_treatment" and f["step"] == "summary":
        f["step"], f["back_to_summary"] = "treatment", True
        return f, ask(f, cfg)
    if action == "change_datetime" and f["step"] == "summary":
        f["step"], f["back_to_summary"] = "date", True
        return f, ask(f, cfg)
    if action == "switch_inclinic" and f["kind"] == "online":
        f["kind"] = "book"
        return f, _advance(f, cfg, "summary")
    if action == "start_again":
        return start(f["kind"])
    return f, ask(f, cfg)
