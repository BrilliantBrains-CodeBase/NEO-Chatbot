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

from app.chat.flows import EMAIL, normal_phone, valid_name
from app.chat.understand import EMERGENCY, is_menu, is_yes, match_option, norm, parse_date, parse_time
from app.crm.flow import DAYS, DEFAULT_QUESTIONS, LEAD_TYPES, Flow, Node, settings_of

AUTO = {"typed", "set_field", "goto", "condition", "clinic_open", "media"}  # go on by themselves
MAX_STEPS = 50  # a loop of automatic blocks stops here
NO = re.compile(r"no|n|nope|not now|cancel|don'?t|do not")


@dataclass
class Context:
    """What the flow reads from outside: India time, the device, and the clinic's live data."""

    today: date
    minutes: int  # minutes since midnight, India time
    device: str = "desktop"
    returning: bool = False  # a lead with this phone already exists
    services: list[dict[str, Any]] = field(default_factory=list)  # Clinic info → Services
    open_now: dict[str, bool] = field(default_factory=lambda: {"in_clinic": True, "online": True})
    location: str = ""  # Contact & hours, as text
    phone: str = ""  # the clinic's number: a call button with no number calls it
    reviews: list[str] = field(default_factory=list)  # Clinic info → Reviews, newest first
    kb: Callable[[str], str | None] = lambda q: None  # approved Knowledge base answers only
    appointments: Callable[[str], list[str]] = lambda phone: []  # upcoming, as text


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
        self.out: list[dict[str, Any]] = []
        self.lead: dict[str, Any] | None = None  # a finished booking / call back ... (saved by the caller)

    # ---------- the result ----------
    def reply(self) -> dict[str, Any]:
        return {
            "messages": self.out,
            "at": self.at,
            "lead": self.lead,
            "state": {"at": self.at, "fields": self.fields, "ask": self.ask},
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
            if node.settings.get("book_label") and self._leads(node.id, "book"):
                out.append({"id": "book", "label": self.sub(node.settings["book_label"]), "action": "go"})
            if node.settings.get("treatments_label"):
                out.append({"id": "treatments", "label": node.settings["treatments_label"], "action": "list"})
        if node.type == "treatment_card":
            out += [
                {"id": x, "label": label, "action": "go"}
                for x, label in (("book", "Book"), ("more", "More treatments"))
                if self._leads(node.id, x)
            ]
        for b in getattr(s, "buttons", []):
            if not b.visible or (not b.action and not self._leads(node.id, b.id)):
                continue  # hidden, or its line leads nowhere / to a block that is off
            out.append({"id": b.id, "label": b.label, "action": b.action or "go", "value": b.value})
        return out

    def _treat(self, t: dict[str, Any]) -> dict[str, Any]:
        return {"id": "t:" + t["name"], "label": t["name"], "action": "treatment", "value": t["name"]}

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
            self.ask = {"kind": "lead", "i": 0, "tries": 0}
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
            text = "\n".join(x for x in (s["doctor"], s.get("title", ""), s.get("qualifications", "")) if x)
            more["card"] = {k: s.get(k) for k in ("photo", "about", "stats", "profile_url")}
        if node.type == "treatment_card":
            text = self.treatment_text(s["treatment"])
        if node.type == "location":
            text = "\n".join(x for x in (text, self.ctx.location) if x)
        if node.type == "reviews":
            text = "\n\n".join([text, *self.ctx.reviews[: int(s.get("count", 3))]]).strip()
        if node.type in ("link", "whatsapp", "call"):
            value = s.get("url") or s.get("number", "")
            more["open"] = {"action": node.type, "value": value}
        if node.type == "carousel" and s.get("source") == "custom":
            more["cards"] = s["cards"]
        self.say(text, buttons=self.buttons(node), **more)

    def treatment_text(self, name: str) -> str:
        t = next((x for x in self.ctx.services if x.get("name") == name), None)
        if t is None:
            return name
        price = f"\nFrom ₹{t['price']:,}" if t.get("show_price") and t.get("price") is not None else ""
        return f"{name}{price}\n{t.get('description') or ''}".strip()

    # ---------- the patient's message ----------
    def tap(self, button_id: str) -> dict[str, Any]:
        node = self.nodes.get(self.at or "")
        if node is None:
            return self.start()
        if self.ask and self.ask["kind"] in ("question", "consent"):
            return self.text(button_id)
        b = next((x for x in self.buttons(node) if x["id"] == button_id), None)
        kind, _, name = button_id.partition(":")
        if b is None and name and kind in ("t", "book"):  # shown after a tap: a treatment, or Book it
            b = {"id": button_id, "action": "treatment" if kind == "t" else "book", "value": name}
        if b is None:
            self.say("Please choose one of the options.")
            self.render(node)
            return self.reply()
        self.act(node, b)
        return self.reply()

    def act(self, node: Node, b: dict[str, Any]) -> None:
        a, value = b["action"], b.get("value", "")
        if a == "go":
            self.follow(b["id"])
        elif a == "treatment":
            self.fields["treatment"] = value
            book = [{"id": "book:" + value, "label": "Book", "action": "book", "value": value}]
            self.say(self.treatment_text(value), buttons=book if self.first("book") else [])
        elif a == "faq":
            self.say(node.settings["items"][int(value)]["answer"])
        elif a == "list":  # a doctor's treatments, each to its card
            names = node.settings.get("treatments") or []
            self.say("", buttons=[self._treat({"name": n}) for n in names])
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
        g = {t.kind: t for t in self.flow.globals.triggers if t.enabled}
        if EMERGENCY.search(text.lower()) and "emergency" in g:
            self.enter(g["emergency"].target or self.first("emergency") or "")
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
        if self.ask:
            self.answer(node, text)
            return self.reply()
        options = self.buttons(node)
        hit = match_option(text, options)
        if hit:
            self.act(node, hit)
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
                self.render(node)
        return self.reply()

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
        if kind == "consent":
            if is_yes(text):
                self.finish(node)
            elif NO.fullmatch(norm(text)):
                self.ask = None
                self.say("No problem. Your details were not saved.")
                self.enter(self.first("opening") or "")
            else:
                self.say("Please choose Yes or No.", buttons=self.yes_no())
            return
        if kind == "question":
            s = node.settings
            value = self.check(s["kind"], text, s)
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
        fields = self.lead_fields(node)
        key = fields[ask["i"]]
        value = self.check(key, text, {})
        if value is None:
            return self.wrong(node, f"Sorry, that doesn't look like a valid {key.replace('_', ' ')}.", None)
        self.fields[key] = value
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
            return t if valid_name(t) else None
        if kind == "phone":
            return normal_phone(t, None)
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
        if s.get("treatment") or (node.type == "book" and self.fields.get("treatment")):
            skip.add("treatment")
        return [f for f in s.get("fields", []) if f not in skip]

    def next_question(self, node: Node) -> None:
        s, ask = node.settings, self.ask or {}
        fields = self.lead_fields(node)
        if ask.get("i", 0) < len(fields):
            key = fields[ask["i"]]
            self.say((s.get("questions") or {}).get(key) or DEFAULT_QUESTIONS[key])
            return
        if s.get("consent", True):
            self.ask = {"kind": "consent", "tries": 0}
            self.say(s.get("consent_text") or "May we save your details?", buttons=self.yes_no())
            return
        self.finish(node)

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
        keys = set(s.get("fields", [])) | {"treatment", "doctor", "reason"}
        self.lead = {"type": node.type, "block": node.id} | {
            k: v for k, v in self.fields.items() if k in keys and v
        }
        self.ask = None
        self.say(s.get("final_message") or "Thank you, {name}. Our team will contact you shortly.")
        self.follow("done")


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
