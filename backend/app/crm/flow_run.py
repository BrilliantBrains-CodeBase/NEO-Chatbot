"""Runs a workflow canvas flow (app.crm.flow), one patient message at a time: tapped buttons and typed text
alike. No database and no LLM here: the live data comes in a Context (services, hours, Knowledge base search,
appointments), so the test chat (W6) and later the widget can share it. Typed text is matched with the chat's
own rules (button labels with typos, dates, times, yes, main menu, emergency words).

State (JSON, kept by the caller between messages): {"at": block id, "fields": {...}, "ask": {...} | None}.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from rapidfuzz.distance import Levenshtein

from app.chat.engine import BYE, MAIN_MENU_TEXT, NO_ANSWER, NOTED, THANKS
from app.chat.flows import EMAIL, normal_phone, valid_name
from app.chat.intents import treatment_topic
from app.chat.kb import GENERAL as KB_GENERAL
from app.chat.understand import (
    COST_OPTIONS,
    EMERGENCY,
    IDENTITY,
    INTENTS,
    MEDICAL,
    is_menu,
    is_yes,
    match_option,
    norm,
    parse_date,
    parse_time,
    small_talk,
    spelled,
)
from app.crm.flow import DAYS, DEFAULT_QUESTIONS, LEAD_TYPES, Flow, Node, settings_of

AUTO = {
    "typed",
    "set_field",
    "goto",
    "condition",
    "clinic_open",
    "media",
    "known_patient",
    "lead_tag",
}  # go on by themselves
MAX_STEPS = 50  # a loop of automatic blocks stops here
NO = re.compile(r"no|n|nope|not now|cancel|don'?t|do not")
# Too general to name one treatment by themselves ("hair" is in many names).
GENERAL_WORDS = KB_GENERAL | {"female", "body", "direct", "failed", "scalp", "laser", "stem"}
# The answer box the widget shows for each question (phone: with the country picker).
INPUT_MODE = {"name": "text", "phone": "phone", "email": "email", "reason": "text"}
BACK = re.compile(r"back|go back|previous|undo")
# "Which details would you like to change?": the button for each question, and the words that also pick it.
CHANGE_OPTIONS = {
    "name": ("Name", r"name"),
    "phone": ("Contact number", r"phone|mobile|number|contact|whatsapp"),
    "email": ("Email", r"e ?mail|mail"),
    "treatment": ("Treatment", r"treatment|service"),
    "doctor": ("Doctor", r"doctor|dr"),
    "date": ("Date", r"date|day"),
    "time": ("Time", r"time|slot"),
    "booked_date": ("Booked date", r"booked"),
    "reason": ("Reason", r"reason|about"),
}
# Changing their mind mid-question ("actually I want to cancel"): the block type it switches to.
SWITCH = [
    ("cancel", re.compile(r"\bcancel\w*\b.*\b(appointment|booking|visit|it)\b|\bcancel (my|the)\b")),
    (
        "reschedule",
        re.compile(r"\b(reschedul\w*|postpone|(change|move|shift) (my |the )?(appointment|booking|date))\b"),
    ),
]
QUESTION = re.compile(
    r"\?\s*$|^(what|how|when|where|why|which|who|is|are|do|does|can|will|kya|kitna|kab|kahan)\b"
)
# Typed at "May I know your full name?" but no name: a question ("will" left out: Will is a name), a long
# sentence, or a word a name never has. It is then answered (Knowledge base / the clinic's page) and the name
# asked again, instead of "Thanks, what is the price".
NAME_QUESTION = re.compile(
    r"\?|^(what|how|when|where|why|which|who|is|are|do|does|can|kya|kitna|kab|kahan)\s"
)
NOT_NAME = {
    "price", "prices", "cost", "costs", "fee", "fees", "charges", "timing", "timings", "hours", "open",
    "address", "location", "located", "directions", "review", "reviews", "appointment", "appointments",
    "booking", "book", "cancel", "reschedule", "doctor", "doctors", "treatment", "treatments", "clinic",
    "help", "menu", "whatsapp", "call", "number", "phone", "email", "today", "tomorrow", "want", "need",
    "please", "hello", "hi", "thanks", "thank", "ok", "okay", "yes", "no",
}  # fmt: skip


@dataclass
class Context:
    """What the flow reads from outside: India time, the device, and the clinic's live data."""

    today: date
    minutes: int  # minutes since midnight, India time
    device: str = "desktop"
    returning: bool = False  # a lead with this phone already exists
    services: list[dict[str, Any]] = field(default_factory=list)  # Clinic info → Services
    open_now: dict[str, bool] = field(default_factory=lambda: {"in_clinic": True, "online": True})
    location: str = ""  # Contact & hours: the address and landmark, as text
    maps_link: str = ""  # Contact & hours: the Google Maps link (a Location block's "Map link")
    hours_today: str = (
        ""  # today's in-clinic hours and open / closed now (a Location block's "Today's hours")
    )
    booking_options: list[str] = field(default_factory=list)  # Services → booking list ("Which treatment?")
    # A booking choice -> the services set to "book as" it (Clinic info → Services), when 2 or more: asked
    # next ("Which treatment exactly?"), e.g. "Non-Surgical Treatment" -> PRP, GFC, QR678.
    techniques: dict[str, list[str]] = field(default_factory=dict)
    phone: str = ""  # the clinic's number: a call button with no number calls it
    reviews: list[str] = field(default_factory=list)  # Clinic info → Reviews, newest first
    kb: Callable[[str], str | None] = lambda q: None  # approved Knowledge base answers only
    kb_source: str = ""  # what answered: "qa" or "fact" by words, "qa_meaning" / "fact_meaning" by meaning
    # Knowledge base only (a clinic's testing switch): typed questions are answered from the Knowledge base
    # alone, no screens, keyword rules or phrases. Safety, buttons and booking answers work as always.
    kb_only: bool = False
    appointments: Callable[[str], list[str]] = lambda phone: []  # upcoming, as text
    # Free HH:MM slots per day (YYYY-MM-DD) for the booking open now: doctors' hours, leave, holidays and
    # appointments (in-clinic and online share one diary). None: not checked (e.g. no database).
    slots: dict[str, dict[str, list[str]]] | None = None  # by mode: in_clinic, online
    # Each active doctor's day today, by name (app.chat.slots.doctors_today): hours, leave, today's free
    # in-clinic times and the next free day. Shown on the doctor's card.
    doctor_today: dict[str, dict[str, Any]] = field(default_factory=dict)
    # The approved phrase closest in meaning ({"target", "text", "score"}), when no words matched.
    meaning: Callable[[str], dict[str, Any] | None] = lambda text: None


KB_ONLY_MISS = "Sorry, I don't have an answer to that yet."


NOT_SURE = "Not sure"


class Run:
    def __init__(self, flow: dict[str, Any], ctx: Context, state: dict[str, Any] | None = None) -> None:
        self.flow = Flow.model_validate(flow)
        self.ctx = ctx
        self.nodes = {n.id: n for n in self.flow.nodes}
        self.lines = {(e.source, e.exit): e.target for e in self.flow.edges}
        st = state or {}
        self.at: str | None = st.get("at")
        self.fields: dict[str, str] = dict(st.get("fields") or {})
        self.ask: dict[str, Any] | None = st.get("ask")
        self.back: list[str] = list(st.get("back") or [])  # the screens before this one, for "back"
        self.out: list[dict[str, Any]] = []
        self.lead: dict[str, Any] | None = None  # a finished booking / call back ... (saved by the caller)
        self.matched: dict[str, Any] | None = None  # what typed text matched (shown in the test chat)
        self.alert: dict[str, Any] | None = None  # a staff alert raised now (the caller sends it)
        self.last_text = ""

    # ---------- the result ----------
    def reply(self) -> dict[str, Any]:
        return {
            "messages": self.out,
            "at": self.at,
            "lead": self.lead,
            "matched": self.matched,
            "alert": self.alert,
            "state": {"at": self.at, "fields": self.fields, "ask": self.ask, "back": self.back[-10:]},
        }

    def say(self, text: str, **more: Any) -> None:
        node = self.nodes.get(self.at or "")
        msg = {"text": self.sub(text), "typing": node.typing if node else 0} | more
        if msg["text"] or len(msg) > 2:
            self.out.append(msg)

    def sub(self, text: str) -> str:
        return re.sub(r"\{([a-z][a-z0-9_]*)\}", lambda m: self.fields.get(m[1], ""), text or "")

    # ---------- which blocks and buttons are shown ----------
    def shown(self, node: Node | None) -> bool:
        if node is None or not node.enabled:
            return False
        if node.show_from and self.ctx.today < node.show_from:
            return False
        if node.show_until and self.ctx.today > node.show_until:
            return False
        return not (node.clinic_hours_only and not self.ctx.open_now.get("in_clinic", True))

    def buttons(self, node: Node) -> list[dict[str, Any]]:
        """The buttons on screen: each with its action, or "go" when it leads on along its line."""
        s = settings_of(node)
        out: list[dict[str, Any]] = []
        if node.type == "treatment_list":
            cat = node.settings.get("category")
            out += [self._treat(t) for t in self.ctx.services if t.get("show") and t.get("category") == cat]
        if node.type == "carousel" and node.settings.get("source") != "custom":
            cat = node.settings.get("category")
            out += [
                self._treat(t)
                for t in self.ctx.services
                if t.get("show") and (not cat or t.get("category") == cat)
            ]
        if node.type == "faq":
            out += [
                {"id": f"faq{i}", "label": f["question"], "action": "faq", "value": str(i)}
                for i, f in enumerate(node.settings.get("items") or [])
            ]
        if node.type == "doctor_card":
            # Today's free in-clinic times: a tap books this doctor then (when a booking block is reachable).
            if self._booking_for(node):
                times = (self.ctx.doctor_today.get(node.settings["doctor"]) or {}).get("times") or []
                out += [
                    {"id": f"slot:{t}", "label": _time(t), "action": "slot", "value": t} for t in times[:6]
                ]
            if node.settings.get("book_label") and self._leads(node.id, "book"):
                out.append({"id": "book", "label": self.sub(node.settings["book_label"]), "action": "go"})
            if node.settings.get("treatments_label"):
                out.append({"id": "treatments", "label": node.settings["treatments_label"], "action": "list"})
        if node.type == "treatment_card":
            out += [
                {"id": x, "label": label, "action": "go"}
                for x, label in (("book", "Book"), ("more", "More treatments"))
                if self._leads(node.id, x)
            ] + self.read_more(node.settings.get("treatment", ""))
        if node.type == "location" and node.settings.get("map", True) and self.ctx.maps_link:
            out.append(
                {"id": "map", "label": "Open in Google Maps", "action": "link", "value": self.ctx.maps_link}
            )
        for b in getattr(s, "buttons", []):
            if not b.visible or (not b.action and not self._leads(node.id, b.id)):
                continue  # hidden, or its line leads nowhere / to a block that is off
            out.append({"id": b.id, "label": b.label, "action": b.action or "go", "value": b.value,
                        "icon": b.icon, "variant": b.variant})  # fmt: skip
        return out

    def _treat(self, t: dict[str, Any]) -> dict[str, Any]:
        return {"id": "t:" + t["name"], "label": t["name"], "action": "treatment", "value": t["name"]}

    def _booking_for(self, card: Node) -> str | None:
        """The booking block a doctor's card leads to: its Book line, else the canvas's booking block."""
        target = self.lines.get((card.id, "book")) or self.first("book")
        return target if target and self.shown(self.nodes.get(target)) else None

    def today_line(self, doctor: str) -> str:
        """The doctor's day today, as the card says it."""
        d = self.ctx.doctor_today.get(doctor)
        if d is None:
            return ""

        def span(xs: list[tuple[str, str]]) -> str:
            return ", ".join(f"{_time(a)} – {_time(b)}" for a, b in xs)

        parts = []
        if d["on_leave"]:
            parts.append("On leave today.")
        else:
            if d["in_clinic"]:
                parts.append(f"In the clinic today: {span(d['in_clinic'])}.")
            if d["online"]:
                parts.append(f"Online today: {span(d['online'])}.")
            if not parts:
                parts.append("The clinic is closed today." if d["closed"] else "Not in the clinic today.")
        if d["times"]:
            parts.append("Choose a time to book your appointment today:")
        else:
            if d["in_clinic"]:
                parts.append("No free times left today.")
            if d["next"]:
                parts.append(f"Next free day: {_day(d['next'])}.")
        return " ".join(parts)

    def _leads(self, source: str, exit_: str) -> bool:
        return self.shown(self.nodes.get(self.lines.get((source, exit_), "")))

    # ---------- moving through the flow ----------
    def start(self) -> dict[str, Any]:
        opening = next((n.id for n in self.flow.nodes if n.type == "opening"), None)
        if opening:
            self.enter(opening)
        return self.reply()

    def follow(self, exit_: str) -> bool:
        target = self.lines.get((self.at or "", exit_))
        if target and self.shown(self.nodes.get(target)):
            self.enter(target)
            return True
        return False

    def enter(self, node_id: str, steps: int = 0) -> None:
        node = self.nodes.get(node_id)
        if node is None or steps > MAX_STEPS:
            return
        if not self.shown(node):  # an off block is skipped: the patient goes on
            nxt = next((self.lines[k] for k in self.lines if k[0] == node_id), None)
            if nxt:
                self.enter(nxt, steps + 1)
            return
        if self.at and self.at != node_id and node.type not in AUTO:
            self.back.append(self.at)
        self.at, self.ask = node_id, None
        s = node.settings
        t = node.type
        if t in AUTO:
            exit_ = self.auto(node)
            target = self.lines.get((node_id, exit_)) if exit_ else None
            if target:
                self.enter(target, steps + 1)
            return
        if t in LEAD_TYPES:
            known = [
                f for f in ("name", "phone", "email") if self.fields.get(f)
            ]  # given earlier in this chat
            known += (self.fields.pop("_picked", "") or "").split()  # a time tapped on a doctor's card
            if t == "book" and self.fields.get("treatment"):  # chosen earlier (a treatment card's Book)
                known.append("treatment")
            if t == "callback" and self.fields.get("reason"):  # e.g. the medical question
                known.append("reason")
            self.ask = {"kind": "lead", "i": 0, "tries": 0, "known": known}
            self.next_question(node)
            return
        if t == "question":
            self.ask = {"kind": "question", "tries": 0}
            opts = [
                {"id": o["label"], "label": o["label"], "image": o.get("image", "")} for o in s["options"]
            ]
            if s["kind"] == "yes_no":
                opts = [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}]
            if s["kind"] == "rating":
                lo, hi = int(s.get("minimum") or 1), int(s.get("maximum") or 5)
                opts = [{"id": str(i), "label": str(i)} for i in range(lo, hi + 1)]
            self.say(s["question"], buttons=[o | {"action": "answer"} for o in opts])
            if s["kind"] == "file" and s.get("consent_text"):
                self.say(s["consent_text"])
            return
        if t == "knowledge":
            self.ask = {"kind": "knowledge", "tries": 0}
            self.say(s["message"])
            return
        if t == "check_appointment":
            self.ask = {"kind": "check", "tries": 0}
            self.say(s["message"])
            return
        if t == "emergency" and self.flow.globals.emergency_alert:
            self.alert = {
                "kind": "emergency",
                "said": self.last_text[:300],
                "phone": self.fields.get("phone", ""),
            }
        self.render(node)

    def auto(self, node: Node) -> str | None:
        s = node.settings
        if node.type == "set_field":
            self.fields[s["field"]] = self.sub(s.get("value", ""))
        if node.type == "goto":
            self.enter(s["target"])
            return None
        if node.type == "condition":
            for b in s["branches"]:
                hits = [self.test(t) for t in b["tests"]]
                if all(hits) if b.get("match", "all") == "all" else any(hits):
                    return str(b["id"])
            return "else"
        if node.type == "known_patient":  # a lead with this phone already exists (the caller looked it up)
            return "known" if self.ctx.returning else "new"
        if node.type == "lead_tag":
            self.fields["campaign"] = s["campaign"]
            return "next"
        if node.type == "clinic_open":
            return "open" if self.ctx.open_now.get(s.get("hours", "in_clinic"), True) else "closed"
        if node.type == "media":
            self.say(s.get("caption", ""), media={"kind": s["kind"], "url": s["url"]})
        return "next"

    def test(self, t: dict[str, Any]) -> bool:
        v, op = str(t.get("value", "")).strip().lower(), t["op"]
        if t["subject"] == "field":
            have = self.fields.get(t.get("field", ""), "").strip().lower()
            return {
                "is": have == v,
                "is_not": have != v,
                "contains": v in have,
                "empty": not have,
                "not_empty": bool(have),
            }[op]
        if t["subject"] == "weekday":
            today = DAYS[self.ctx.today.weekday()]
            listed = today in v.replace(" ", "").split(",")
            return listed if op == "is" else not listed
        if t["subject"] == "time":
            h, m = v.split(":")
            mins = int(h) * 60 + int(m)
            return self.ctx.minutes < mins if op == "before" else self.ctx.minutes >= mins
        if t["subject"] == "device":
            return self.ctx.device == v
        return self.ctx.returning == (v == "yes")  # returning

    def render(self, node: Node) -> None:
        s = node.settings
        text = s.get("welcome") or s.get("message") or s.get("text") or ""
        more: dict[str, Any] = {}
        if node.type == "doctor_card":
            text = "\n".join(
                x
                for x in (
                    s["doctor"],
                    s.get("title", ""),
                    s.get("qualifications", ""),
                    self.today_line(s["doctor"]),
                )
                if x
            )
            more["card"] = {k: s.get(k) for k in ("photo", "about", "stats", "profile_url")} | {
                "name": s["doctor"],
                "title": s.get("title", ""),
                "quals": s.get("qualifications", ""),
                "today": self.today_line(s["doctor"]),
            }
        if node.type == "treatment_card":
            text = self.treatment_text(s["treatment"])
            more.update(self.photo(s["treatment"]))
        if node.type == "location":
            hours = self.ctx.hours_today if s.get("hours", True) else ""
            text = "\n".join(x for x in (text, self.ctx.location, hours) if x)
        if node.type == "reviews":
            text = "\n\n".join([text, *self.ctx.reviews[: int(s.get("count", 3))]]).strip()
        if node.type in ("link", "whatsapp", "call"):
            value = s.get("url") or s.get("number", "")
            more["open"] = {"action": node.type, "value": value}
        if node.type == "carousel":
            more["cards"] = self.cards(node)
        self.say(text, buttons=self.buttons(node), **more)

    def cards(self, node: Node) -> list[dict[str, Any]]:
        """A carousel's cards, each with its own buttons: the clinic's own cards (a button id "card<i>:<id>",
        doing its own job), or the category's treatments from Services (each "View" opens its card)."""
        s = node.settings
        if s.get("source") == "custom":
            return [
                {
                    "title": c["title"], "text": c.get("text", ""), "image": c.get("image", ""),
                    "buttons": [
                        b | {"id": f"card{i}:{b['id']}"}
                        for b in c.get("buttons") or []
                        if b.get("visible", True)
                    ],
                }
                for i, c in enumerate(s.get("cards") or [])
            ]  # fmt: skip
        cat = s.get("category")
        out = []
        for t in self.ctx.services:
            if not t.get("show") or (cat and t.get("category") != cat):
                continue
            price = f"From ₹{t['price']:,}" if t.get("show_price") and t.get("price") is not None else ""
            text = price or str(t.get("description") or "")[:120]
            out.append({"title": t["name"], "text": text, "image": t.get("photo") or "", "buttons": [
                self._treat(t) | {"label": "View"}
            ]})  # fmt: skip
        return out

    def service(self, name: str) -> dict[str, Any]:
        return next((x for x in self.ctx.services if x.get("name") == name), None) or {}

    def treatment_text(self, name: str) -> str:
        t = self.service(name)
        if not t:
            return name
        price = f"\nFrom ₹{t['price']:,}" if t.get("show_price") and t.get("price") is not None else ""
        duration = f"\nDuration: {t['duration']}" if t.get("duration") else ""
        return f"{name}{price}{duration}\n{t.get('description') or ''}".strip()

    def read_more(self, name: str) -> list[dict[str, Any]]:
        """The treatment's Read more button: its page on the website (Clinic info → Services)."""
        page = str(self.service(name).get("page") or "")
        return [{"id": "read:" + name, "label": "Read more", "action": "link", "value": page}] if page else []

    def photo(self, name: str) -> dict[str, Any]:
        """The treatment's photo (Clinic info → Services), shown with its card."""
        url = str(self.service(name).get("photo") or "")
        return {"media": {"kind": "image", "url": url}} if url.startswith("https://") else {}

    # ---------- the patient's message ----------
    def tap(self, button_id: str) -> dict[str, Any]:
        node = self.nodes.get(self.at or "")
        if node is None:
            return self.start()
        if self.ask and self.ask["kind"] in ("question", "consent", "change", "lead", "switch"):
            return self.text(button_id)
        b = next((x for x in self.buttons(node) if x["id"] == button_id), None)
        kind, _, name = button_id.partition(":")
        if b is None and name and kind in ("t", "book"):  # shown after a tap: a treatment, or Book it
            b = {"id": button_id, "action": "treatment" if kind == "t" else "book", "value": name}
        if b is None and kind == "slot" and node.type == "doctor_card" and name:  # a time no longer listed
            b = {"id": button_id, "action": "slot", "value": name}  # a taken one: the booking refuses it
        if b is None and kind == "medical":  # the medical offer: a call back about the question, or the menu
            b = {"id": button_id, "action": "callback" if name == "yes" else "menu", "value": ""}
        if b is None and kind == "read" and name:  # a treatment's Read more (test chat: says the page)
            b = next(iter(self.read_more(name)), None)
        if b is None and node.type == "carousel" and kind.startswith("card"):  # a button on one of its cards
            b = next((x for c in self.cards(node) for x in c["buttons"] if x["id"] == button_id), None)
        if b is None:
            self.say("Please choose one of the options.")
            self.render(node)
            return self.reply()
        self.act(node, b)
        return self.reply()

    def act(self, node: Node, b: dict[str, Any]) -> None:
        a, value = b["action"], b.get("value", "")
        if a == "go":
            if node.type == "doctor_card" and b["id"] == "book":
                # "Book with this doctor": the booking is with them (their free times; not asked again)
                self.fields["doctor"] = node.settings["doctor"]
                self.fields["_picked"] = "doctor"
            self.follow(b["id"])
        elif a == "treatment":
            self.fields["treatment"] = value
            book = [{"id": "book:" + value, "label": "Book", "action": "book", "value": value}]
            buttons = (book if self.first("book") else []) + self.read_more(value)
            self.say(self.treatment_text(value), buttons=buttons, **self.photo(value))
        elif a == "faq":
            self.say(node.settings["items"][int(value)]["answer"])
        elif a == "list":  # a doctor's treatments, each to its card
            names = node.settings.get("treatments") or []
            self.say("", buttons=[self._treat({"name": n}) for n in names])
        elif a == "menu":
            self.enter(self.first("opening") or "")
        elif a == "slot":  # a free time today on a doctor's card: book this doctor then
            target = self._booking_for(node)
            if target:
                self.fields.update(
                    doctor=node.settings["doctor"], date=self.ctx.today.isoformat(), time=value
                )
                self.fields["_picked"] = "date time doctor"  # not asked again in the booking block
                self.enter(target)
        elif a in ("book", "callback"):
            target = self.first("book" if a == "book" else "callback")
            if value:
                self.fields["treatment" if a == "book" else "reason"] = value
            if target:
                self.enter(target)
        else:  # link, whatsapp, call: the widget opens it
            if a == "call" and not value:
                value = self.ctx.phone
            self.say("", open={"action": a, "value": value})

    def first(self, type_: str) -> str | None:
        return next((n.id for n in self.flow.nodes if n.type == type_ and self.shown(n)), None)

    def text(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        self.last_text = text
        g = {t.kind: t for t in self.flow.globals.triggers if t.enabled}
        # Emergency words always come first, from anywhere: the trigger's block, else the flow's Emergency.
        sos = (g["emergency"].target if "emergency" in g else "") or self.first("emergency")
        if EMERGENCY.search(text.lower()) and sos:
            self.enter(sos)
            return self.reply()
        if "start_again" in g and norm(text) in ("start again", "restart", "start over"):
            self.fields = {}
            self.enter(g["start_again"].target or self.first("opening") or "")
            return self.reply()
        if "main_menu" in g and is_menu(text):
            self.enter(g["main_menu"].target or self.first("opening") or "")
            return self.reply()
        if "talk_to_person" in g and re.search(
            r"call ?back|talk to (a |some)?(person|human|someone)", text.lower()
        ):
            self.enter(g["talk_to_person"].target)
            return self.reply()
        node = self.nodes.get(self.at or "")
        if node is None:
            return self.start()
        # Medical questions are never answered (client rule), not even from the Knowledge base: the same
        # offer as the live chat, a call back about the question. A booking answer is still taken as typed.
        if MEDICAL.search(text.lower()) and (not self.ask or self.ask["kind"] == "knowledge"):
            self.ask = None
            self.fields["reason"] = text[:200]  # what the call back is about
            offer = [{"id": "medical:yes", "label": "Yes, call me back", "action": "callback", "value": ""}]
            offer.append({"id": "medical:no", "label": "No, thanks", "action": "menu"})
            self.say(NO_ANSWER, buttons=offer)
            return self.reply()
        low = " ".join(text.lower().split())
        if BACK.fullmatch(norm(text)):
            self.go_back()
            return self.reply()
        if self.ask:
            self.answer(node, text)
            return self.reply()
        said = self.small(low)
        if said is not None:
            self.say(said)  # only the reply: the buttons already on screen are not sent again
            return self.reply()
        if self.ctx.kb_only:
            found = self.ctx.kb(text)
            self.matched = {"how": "knowledge base" if found else "knowledge base: no answer", "text": text}
            self.say(found or KB_ONLY_MISS)
            return self.reply()
        options = self.buttons(node)
        hit = match_option(text, options)
        # The live chat's order: buttons and the approved phrases by their words, the keyword rules, a
        # treatment named, the approved Knowledge base; a phrase by meaning only when nothing else fits.
        named = None if hit else self.named_treatment(low, full_only=True)  # a full name beats a phrase
        if named:
            self.matched = {"how": "treatment name", "text": named}
            self.act(node, {"id": "t:" + named, "action": "treatment", "value": named})
            return self.reply()
        phrase = None if hit else self.phrase(text, meaning=False)
        start = None if hit or phrase else self.start_rule(low)
        start = self.first(start) if start else None
        found = None if hit or phrase or start else self.ctx.kb(text)  # approved answers; never medical
        if found and self.ctx.kb_source in ("fact_meaning", "followup") and self.page_rule(low):
            found = (
                None  # the clinic's own screen (location: address and map) beats a fact matched only loosely
            )
        if hit:
            self.matched = {"how": "button", "text": hit["label"]}
            self.act(node, hit)
        elif phrase:
            self.go_to_phrase(phrase)
        elif start:
            self.matched = {"how": "rule", "text": start}  # the live chat's keyword rules ("cancel my visit")
            self.enter(start)
        elif found:
            self.matched = {"how": "knowledge base", "text": text}
            self.say(found)  # only the answer: the buttons already on screen are not sent again
        elif treatment := self.named_treatment(low):
            self.matched = {"how": "treatment name", "text": treatment}
            self.act(node, {"id": "t:" + treatment, "action": "treatment", "value": treatment})
        elif page := self.page_rule(low):
            self.matched = {"how": "rule", "text": page}  # "price?" -> the cost page
            self.enter(page)
        elif near := self.phrase(text, meaning=True):
            self.go_to_phrase(near)
        elif not self.follow("no_match"):
            topic = next(
                (
                    n.id
                    for n in self.flow.nodes
                    if n.type == "typed" and norm(n.settings.get("topic", "")) in norm(text)
                ),
                None,
            )
            if topic:
                self.enter(topic)
            else:
                fallback = next(
                    (n.settings.get("fallback") for n in self.flow.nodes if n.type == "opening"), ""
                )
                self.say(fallback or "Sorry, I didn't get that. Please choose one of the options.")
        return self.reply()

    # ---------- typed text beside the flow ----------
    def small(self, low: str) -> str | None:
        """Small talk and "who are you": the live chat's replies (a greeting gets the welcome)."""
        welcome = next((n.settings.get("welcome", "") for n in self.flow.nodes if n.type == "opening"), "")
        if IDENTITY.search(low):
            return str(welcome or MAIN_MENU_TEXT)
        chat = small_talk(low)
        if chat is None:
            return None
        return {"greeting": welcome or MAIN_MENU_TEXT, "thanks": THANKS, "bye": BYE, "ok": MAIN_MENU_TEXT}[
            chat
        ]

    def aside(self, node: Node, text: str, before: bool) -> bool:
        """Typed text mid-question that is not the answer: changing their mind or small talk (checked before
        the answer), a medical or side question (after: it was no valid answer). Then the same question again.
        A one-word reply to a free-text question ("ok", "sure") is still its answer."""
        low = " ".join(text.lower().split())
        if before:
            for type_, pattern in SWITCH:
                target = self.first(type_)
                if pattern.search(low) and target and node.type != type_:
                    self.ask = {"kind": "switch", "to": target, "was": self.ask}
                    self.say(f"Shall I stop this and help you {type_} instead?", buttons=self.yes_no())
                    return True
            free_text = node.type == "question" and node.settings.get("kind") == "text"
            said = None if free_text else self.small(low)
            if said is not None:
                self.say(said)
                self.reask(node)
                return True
            return False
        if MEDICAL.search(low):
            self.say(NOTED)
            self.reask(node)
            return True
        if QUESTION.search(low):
            found = self.ctx.kb(text)
            if found:
                self.say(found)
                self.reask(node)
                return True
        # "timings" / "price" typed instead of the answer: the clinic's own page for it says it, then the
        # same question again (the patient stays in the booking).
        page = self.nodes.get(self.page_rule(low) or "")
        said = str(page.settings.get("message") or page.settings.get("text") or "") if page else ""
        if said and page and page.id != node.id:
            self.say(said)
            self.reask(node)
            return True
        return False

    def not_a_name(self, text: str) -> bool:
        """Typed at the name question but plainly not a name (see NOT_NAME)."""
        low = " ".join(text.lower().split())
        words = set(re.findall(r"[a-z]+", low))
        return bool(
            len(low.split()) > 5
            or NAME_QUESTION.search(low)
            or MEDICAL.search(low)
            or words & NOT_NAME
            or self.page_rule(low)
            or self.start_rule(low)
        )

    def reask(self, node: Node) -> None:
        if (self.ask or {}).get("kind") == "lead":
            self.next_question(node)
        else:
            self.at = None  # the same block again, not a new screen in the history
            self.enter(node.id)

    def go_back(self) -> None:
        """The screen before this one (as tapped through), or the opening."""
        while self.back:
            prev = self.back.pop()
            if prev != self.at and self.shown(self.nodes.get(prev)):
                self.at = None  # going back adds nothing to the history
                self.enter(prev)
                return
        self.at = None
        self.enter(self.first("opening") or "")

    def page_rule(self, low: str) -> str | None:
        """The page the live chat's keyword rules open ("price?" -> the cost page, "treatments" -> the
        treatment list; a named cost pattern -> that cost option), when the flow has it."""
        text = spelled(low)
        for pattern, (what, key) in INTENTS:
            if what == "node" and pattern.search(text) and self.shown(self.nodes.get("page-" + key)):
                if key == "cost":
                    exact = next(
                        (k for k, p in COST_OPTIONS if p.search(text) and "page-" + k in self.nodes), None
                    )
                    return "page-" + (exact or key)
                return "page-" + key
        if re.search(r"\b(treatments?|explore|options|services)\b", text) and "page-treat" in self.nodes:
            return "page-treat"
        return None

    def start_rule(self, low: str) -> str | None:
        """The live chat's keyword rules that start a booking, online consult, cancel, reschedule or call
        back (rules written by staff, never learnt)."""
        text = spelled(low)
        return next((t[1] for pattern, t in INTENTS if t[0] == "start" and pattern.search(text)), None)

    def treatment_shown(self, name: str) -> str | None:
        """The shown treatment of that name (or that topic, e.g. t_prp_treatment), as named in Services."""
        for t in self.ctx.services:
            if t.get("show") and (t["name"] == name or treatment_topic(t["name"]) == name):
                return str(t["name"])
        return None

    def named_treatment(self, low: str, full_only: bool = False) -> str | None:
        """A treatment typed by name ("female hair transplant"), or by a first word only one treatment has
        ("prp"; never a general word like "hair"): its card, live from Services."""
        names = [t["name"] for t in self.ctx.services if t.get("show")]
        t = f" {norm(low)} "
        for name in sorted(names, key=len, reverse=True):
            if f" {norm(name)} " in t:
                return str(name)
        if full_only:
            return None
        firsts = [norm(n).split()[0] for n in names]
        for name, first in zip(names, firsts, strict=True):
            unique = len(first) >= 3 and firsts.count(first) == 1 and first not in GENERAL_WORDS
            if unique and f" {first} " in t:
                return str(name)
        return None

    # ---------- approved typed phrases ----------
    def phrase(self, text: str, meaning: bool) -> dict[str, Any] | None:
        """The approved phrase the patient meant: the same words, a small typo (about 1 in 6 letters), or the
        phrase inside a longer message (2+ words); else the closest by meaning (from the caller). Phrases on
        the screen the patient is on come first. Pending phrases are never used."""
        t = norm(text)
        here = (self.at or "") + ":"
        ranked = []
        for p in self.flow.phrases:
            if p.status != "approved" or not self.reachable(p.target):
                continue
            w = norm(p.text)
            if w == t:
                rank = 0
            elif Levenshtein.distance(w, t) <= max(1, len(t) // 6):
                rank = 1
            elif " " in w and f" {w} " in f" {t} ":  # the whole phrase, as whole words
                rank = 2
            else:
                continue
            ranked.append((rank, not p.target.startswith(here), -len(w), p))
        if ranked and not meaning:
            rank, _, _, p = min(ranked, key=lambda r: r[:3])
            return {"target": p.target, "text": p.text, "how": ("phrase", "typo", "phrase in message")[rank]}
        near = self.ctx.meaning(text) if meaning else None
        if near and self.reachable(near["target"]):
            return near | {"how": "meaning"}
        return None

    def reachable(self, target: str) -> bool:
        if target.startswith("@treatment:"):
            return self.treatment_shown(target.removeprefix("@treatment:")) is not None
        if target.startswith("@"):
            return True  # small talk
        node_id, _, button = target.partition(":")
        node = self.nodes.get(node_id)
        if not self.shown(node) or node is None:
            return False
        return not button or any(b["id"] == button for b in self.buttons(node))

    def go_to_phrase(self, p: dict[str, Any]) -> None:
        """As if the patient tapped that button (on its own screen), or reached that Typed trigger."""
        self.matched = {"how": p["how"], "text": p["text"]} | ({"score": p["score"]} if "score" in p else {})
        target = p["target"]
        if target.startswith("@treatment:"):
            name = self.treatment_shown(target.removeprefix("@treatment:")) or ""
            here = self.nodes.get(self.at or "")
            if here:
                self.act(here, {"id": "t:" + name, "action": "treatment", "value": name})
            return
        if target.startswith("@"):  # small talk: the live chat's reply, then the same screen
            small = {"@identity": "who are you", "@greeting": "hello", "@thanks": "thanks", "@bye": "bye"}
            self.say(self.small(small[target]) or "")
            here = self.nodes.get(self.at or "")
            if here:
                self.render(here)
            return
        node_id, _, button = target.partition(":")
        if not button:
            self.enter(node_id)
            return
        node = self.nodes[node_id]
        b = next(x for x in self.buttons(node) if x["id"] == button)
        self.at = node_id
        self.act(node, b)

    # ---------- answers to questions ----------
    def answer(self, node: Node, text: str) -> None:
        ask = self.ask or {}
        kind = ask["kind"]
        if kind == "knowledge":
            found = self.ctx.kb(text)
            if found:
                self.say(found)
            self.follow("answered" if found else "not_found")
            return
        if kind == "check":
            phone = normal_phone(text, None)
            if not phone:
                return self.wrong(node, "Please share a valid 10-digit mobile number.", "not_found")
            self.fields["phone"] = phone
            if node.settings.get("otp"):
                self.say(
                    "(Test chat: the OTP step is skipped here; it is sent on WhatsApp through Interakt.)"
                )
            booked = self.ctx.appointments(phone)
            for a in booked:
                self.say(a)
            if not booked:
                self.say("I couldn't find an upcoming appointment with this number.")
            self.follow("found" if booked else "not_found")
            return
        if kind == "switch":  # "Shall I stop this?"
            if is_yes(text):
                self.enter(ask["to"])
            else:
                self.ask = ask["was"]
                self.reask(node)
            return
        if kind in ("lead", "question") and self.aside(node, text, before=True):
            return
        if kind == "consent":  # "Is this correct?"
            low = norm(text)
            if is_yes(text) or low in ("yes that's correct", "yes thats correct", "correct", "confirm"):
                self.finish(node)
            elif low in ("change", "change details", "edit", "update") or NO.fullmatch(low):
                self.change_details(node)
            else:
                self.say("Please choose one: is this correct, or change your details?",
                         buttons=self.confirm_buttons())  # fmt: skip
            return
        if kind == "change":  # "Which details would you like to change?"
            if is_yes(text) or NO.fullmatch(norm(text)):  # nothing to change: their details again
                self.edit_field(node, None)
                return
            key = self.change_choice(node, text)
            if key:
                self.edit_field(node, key)
            else:
                self.say("Please choose which details to change.", buttons=self.change_buttons(node))
            return
        if kind == "question":
            s = node.settings
            value = self.check(s["kind"], text, s)
            if value is None and self.aside(node, text, before=False):
                return
            if value is None:
                if not s.get("required", True) and norm(text) in ("skip", "no"):
                    self.follow("next")
                    return
                return self.wrong(node, "Sorry, that doesn't look right. Please try again.", None)
            self.fields[s["field"]] = value
            self.ask = None
            if s["kind"] == "yes_no":
                self.follow(value)
            else:
                self.follow("next")
            return
        # a booking / call back ... question
        if ask.get("sub"):  # "Which treatment exactly?" after a booking choice that has several
            options = [
                {"id": t, "label": t, "action": "answer"}
                for t in [*self.ctx.techniques[ask["sub"]], NOT_SURE]
            ]
            hit = match_option(text, options)
            if hit is None and self.aside(node, text, before=False):
                return
            if hit is None:
                return self.wrong(node, "Please choose one of the treatments.", None)
            if hit["label"] != NOT_SURE:
                self.fields["treatment"] = hit["label"]  # the exact one; "Not sure" keeps the booking choice
            ask.pop("sub")
            ask.update(i=ask["i"] + 1, tries=0)
            self.next_question(node)
            return
        fields = self.lead_fields(node)
        key = fields[ask["i"]]
        value = self.check(key, text, {})
        if value is None and self.aside(node, text, before=False):
            return
        if value is None:
            return self.wrong(node, f"Sorry, that doesn't look like a valid {key.replace('_', ' ')}.", None)
        free = self.free(node)
        if free is not None and key == "date" and value not in free:
            days = ", ".join(_day(d) for d in list(free)[:5]) or "none in the next two weeks"
            self.wrong(node, f"Sorry, there are no free times on {_day(value)}. Free days: {days}.", None)
            if self.ask:
                self.say("", **self.offer(node, "date"))
            return
        if free is not None and key == "time" and value != "any":
            times = free.get(self.fields.get("date", ""), [])
            if value not in times:
                self.wrong(
                    node, f"Sorry, {_time(value)} is not free that day. Please pick a free time.", None
                )
                if self.ask:
                    self.say("", **self.offer(node, "time"))
                return
        self.fields[key] = value
        if key == "date" and ask.get("editing") and "time" in ask["known"]:
            old = self.fields.get("time", "")  # the time kept from before may not be free on the new date
            if free is not None and old not in ("", "any") and old not in free.get(value, []):
                self.say(f"{_time(old)} is not free on {_day(value)}.")
                self.edit_field(node, "time")
                return
        if key == "treatment" and len(self.ctx.techniques.get(value, [])) > 1:
            ask["sub"] = value  # its techniques next, then the next question
            self.next_question(node)
            return
        ask.update(i=ask["i"] + 1, tries=0)
        self.next_question(node)

    def wrong(self, node: Node, message: str, exit_: str | None) -> None:
        ask = self.ask or {}
        ask["tries"] = ask.get("tries", 0) + 1
        limit = int(node.settings.get("retries", node.settings.get("otp_retries", 2)))
        if ask["tries"] <= limit:
            self.say(message)
            return
        self.ask = None
        if exit_ and self.follow(exit_):
            return
        callback = self.first("callback")
        self.say("Let me arrange a call back from our team instead.")
        if callback and callback != node.id:
            self.enter(callback)

    def check(self, kind: str, text: str, s: dict[str, Any]) -> str | None:
        """The answer in a clean form, or None when it does not fit its kind."""
        t = text.strip()
        if kind == "name":
            return t if valid_name(t) and not self.not_a_name(t) else None
        if kind == "phone":  # "+971 501234567" from the country picker, or a number alone (India)
            m = re.fullmatch(r"(\+\d{1,4})\s+(.+)", t)
            return normal_phone(m[2], m[1]) if m else normal_phone(t, None)
        if kind == "email":
            return t.lower() if EMAIL.match(t) else None
        if kind in ("date", "booked_date"):
            return parse_date(t, self.ctx.today)
        if kind == "time":
            return parse_time(t)
        if kind == "yes_no":
            return "yes" if is_yes(t) else "no" if NO.fullmatch(norm(t)) else None
        if kind in ("number", "rating"):
            try:
                n = float(t)
            except ValueError:
                return None
            lo, hi = s.get("minimum"), s.get("maximum")
            if kind == "rating":
                lo, hi = lo if lo is not None else 1, hi if hi is not None else 5
            if (lo is not None and n < lo) or (hi is not None and n > hi):
                return None
            return str(int(n)) if n.is_integer() else str(n)
        if kind in ("choice", "picture_choice"):
            hit = match_option(t, [{"label": o["label"], "action": "answer"} for o in s.get("options", [])])
            return hit["label"] if hit else None
        return t if len(t) >= 1 else None  # text, file, treatment, doctor, reason

    def lead_fields(self, node: Node) -> list[str]:
        s = node.settings
        skip = {"doctor"} if s.get("doctor") else set()
        if s.get("treatment"):
            skip.add("treatment")
        # Given before this block (name, phone, a treatment chosen earlier, the medical question...): decided
        # once when the block starts, so an answer given IN the block never shifts the questions after it.
        skip |= set((self.ask or {}).get("known") or [])
        return [f for f in s.get("fields", []) if f not in skip]

    def free(self, node: Node) -> dict[str, list[str]] | None:
        """Free slots, when this block books a time (a cancel or call back has no slot to check)."""
        if self.ctx.slots is None or node.type not in ("book", "online", "reschedule", "follow_up"):
            return None
        return self.ctx.slots.get("online" if node.type == "online" else "in_clinic", {})

    def offer(self, node: Node, key: str) -> dict[str, Any]:
        """The tap answers for a question. A free date or time also carries every free day / that day's free
        times ("pick"), so the live chat shows its calendar and time grid; the test chat shows buttons."""
        out: dict[str, Any] = {"buttons": self.picks(node, key)}
        free = self.free(node)
        if free and key == "date":
            out["pick"] = {"kind": "date", "dates": list(free)}
        elif free is not None and key == "time" and free.get(self.fields.get("date", "")):
            out["pick"] = {"kind": "time", "times": free[self.fields["date"]]}
        return out

    def picks(self, node: Node, key: str) -> list[dict[str, Any]]:
        """Tap answers: the booking list for the treatment, the next free days, or that day's free times."""
        if key == "treatment":
            return [{"id": t, "label": t, "action": "answer"} for t in self.ctx.booking_options]
        free = self.free(node)
        if free is None:
            return []
        if key == "date":
            return [{"id": d, "label": _day(d), "action": "answer"} for d in list(free)[:6]]
        if key == "time":
            times = free.get(self.fields.get("date", ""), [])
            return [{"id": t, "label": _time(t), "action": "answer"} for t in times[:12]] + [
                {"id": "any", "label": "Any time", "action": "answer"}
            ]
        return []

    def next_question(self, node: Node) -> None:
        s, ask = node.settings, self.ask or {}
        if ask.get("sub"):
            options = [*self.ctx.techniques.get(ask["sub"], []), NOT_SURE]
            self.say(
                "Which treatment exactly?",
                buttons=[{"id": t, "label": t, "action": "answer"} for t in options],
            )
            return
        fields = self.lead_fields(node)
        if ask.get("i", 0) < len(fields):
            key = fields[ask["i"]]
            callback = self.first("callback")
            if key == "date" and self.free(node) == {} and callback and callback != node.id:
                # No free day to book (e.g. no doctor's hours yet): the team calls back to fix a time.
                treatment = self.fields.get("treatment")
                self.fields.setdefault("reason", "Booking request" + (f": {treatment}" if treatment else ""))
                self.ask = None
                self.say(
                    "There are no free times to book online right now. Our team will call you to fix a time."
                )
                self.enter(callback)
                return
            wording = (s.get("questions") or {}).get(key) or DEFAULT_QUESTIONS[key]
            # No "Thanks, ." when no name was asked, and no thanks when only changing this one answer.
            if "{name}" in wording and (ask.get("editing") or not self.fields.get("name")):
                wording = re.sub(r"^[^.?!]*\{name\}[^.?!]*[.?!]\s*", "", wording) or wording
            self.say(wording, **self.offer(node, key), input={"mode": INPUT_MODE.get(key, "text")})
            return
        if s.get("read_back", True):  # the patient checks their details, as in the live chat
            labels = {"name": "Name", "phone": "Phone", "email": "Email", "treatment": "Treatment",
                      "doctor": "Doctor", "date": "Date", "time": "Time", "booked_date": "Booked date",
                      "reason": "About"}  # fmt: skip
            lines = []
            for k in s.get("fields", []):
                v = self.fields.get(k, "")
                if k in ("date", "booked_date") and v:
                    v = _day(v)
                elif k == "time" and v:
                    v = "Any time" if v == "any" else _time(v)
                if v:
                    lines.append(f"{labels.get(k, k)}: {v}")
            if lines:
                self.say("Please check your details:\n" + "\n".join(lines))
        if s.get("consent", True):  # the clinic's consent line, then "Is this correct?" (change, never lost)
            self.ask = {"kind": "consent", "tries": 0}
            self.say(s.get("consent_text") or "By continuing, you agree to be contacted about your request.")
            self.say("Is this correct?", buttons=self.confirm_buttons())
            return
        self.finish(node)

    def confirm_buttons(self) -> list[dict[str, Any]]:
        return [
            {"id": "yes", "label": "Yes, that's correct", "action": "answer"},
            {"id": "change", "label": "Change details", "action": "answer"},
        ]

    def changeable(self, node: Node) -> list[str]:
        """The details on the read-back that the patient gave (a block's fixed treatment or doctor is not)."""
        s = node.settings
        fixed = {k for k in ("treatment", "doctor") if s.get(k)}
        return [
            k for k in s.get("fields", []) if k in CHANGE_OPTIONS and k not in fixed and self.fields.get(k)
        ]

    def change_buttons(self, node: Node) -> list[dict[str, Any]]:
        labels = [CHANGE_OPTIONS[k][0] for k in self.changeable(node)]
        return [{"id": label, "label": label, "action": "answer"} for label in labels]

    def change_choice(self, node: Node, text: str) -> str | None:
        """The detail picked: its button (typos too), or one detail named ("my phone number")."""
        keys = self.changeable(node)
        hit = match_option(text, self.change_buttons(node))
        if hit:
            return next(k for k in keys if CHANGE_OPTIONS[k][0] == hit["label"])
        named = [k for k in keys if re.search(rf"\b({CHANGE_OPTIONS[k][1]})\b", norm(text))]
        return named[0] if len(named) == 1 else None

    def change_details(self, node: Node) -> None:
        """Asks which detail to change (nothing is sent until the patient confirms, and nothing is lost)."""
        buttons = self.change_buttons(node)
        if not buttons:  # nothing the patient gave: the same check again
            self.edit_field(node, None)
            return
        self.ask = {"kind": "change", "tries": 0}
        self.say("No problem. Which details would you like to change?", buttons=buttons)

    def edit_field(self, node: Node, key: str | None) -> None:
        """Asks that one question again, with its usual checks, then the read-back (None: only that)."""
        known = [k for k in node.settings.get("fields", []) if k != key]
        self.ask = {"kind": "lead", "i": 0, "tries": 0, "known": known, "editing": True}
        self.next_question(node)

    def yes_no(self) -> list[dict[str, Any]]:
        return [
            {"id": "yes", "label": "Yes", "action": "answer"},
            {"id": "no", "label": "No", "action": "answer"},
        ]

    def finish(self, node: Node) -> None:
        s = node.settings
        if s.get("treatment"):
            self.fields["treatment"] = s["treatment"]
        if s.get("doctor"):
            self.fields["doctor"] = s["doctor"]
        if s.get("topic"):
            self.fields.setdefault("reason", s["topic"])
        keys = set(s.get("fields", [])) | {"treatment", "doctor", "reason", "campaign"}
        kind = "book" if node.type == "follow_up" else node.type  # a follow-up is a booking on the same lead
        self.lead = (
            {"type": kind, "block": node.id}
            | ({"follow_up": "yes"} if node.type == "follow_up" else {})
            | {k: v for k, v in self.fields.items() if k in keys and v}
        )
        self.ask = None
        self.say(s.get("final_message") or "Thank you, {name}. Our team will contact you shortly.")
        # Only who the patient is carries on; what this request was about (reason, date...) does not.
        self.fields = {k: v for k, v in self.fields.items() if k in ("name", "phone", "email")}
        self.follow("done")


def _day(d: str) -> str:
    return date.fromisoformat(d).strftime("%a %d %b")


def _time(hm: str) -> str:
    h, m = int(hm[:2]), int(hm[3:])
    return f"{(h - 1) % 12 + 1}:{m:02d} {'AM' if h < 12 else 'PM'}"


def kb_topics(flow: dict[str, Any], state: dict[str, Any] | None) -> tuple[str, ...]:
    """The topics (Knowledge base categories) of the Knowledge block waiting for a question; none: all."""
    if ((state or {}).get("ask") or {}).get("kind") != "knowledge":
        return ()
    node = next((n for n in flow["nodes"] if n["id"] == (state or {}).get("at")), None)
    return tuple(((node or {}).get("settings") or {}).get("topics") or ())


def start(flow: dict[str, Any], ctx: Context) -> dict[str, Any]:
    return Run(flow, ctx).start()


def send(
    flow: dict[str, Any],
    ctx: Context,
    state: dict[str, Any],
    *,
    tap: str | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    """One patient message: a tapped button id, or typed text (matched like a tap when it fits a button)."""
    run = Run(flow, ctx, state)
    return run.tap(tap) if tap is not None else run.text(text or "")


def run_checks(flow: dict[str, Any], ctx: Context) -> list[dict[str, Any]]:
    """Replays each saved check on the flow: it passes when the chat ends on the same block (and finishes a
    lead when it did before)."""
    results = []
    for c in flow.get("checks") or []:
        r, lead = start(flow, ctx), False
        try:
            for step in c["steps"]:
                r = send(flow, ctx, r["state"], tap=step.get("tap"), text=step.get("text"))
                lead = lead or bool(r["lead"])
            ok = r["at"] == c["expect_at"] and (lead or not c.get("expect_lead"))
            why = "" if ok else f"ended at '{r['at']}', expected '{c['expect_at']}'"
            if r["at"] == c["expect_at"] and not ok:
                why = "the booking / call back was not finished"
        except Exception as err:  # a broken flow must not stop the other checks
            ok, why = False, f"stopped: {err}"
        results.append({"name": c["name"], "ok": ok, "message": why})
    return results


__all__ = ["Context", "run_checks", "send", "start"]
