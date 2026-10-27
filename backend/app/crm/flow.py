"""Workflow canvas (Dashboard → Menu buttons): the chat as blocks connected by lines, like n8n.

A flow is a list of blocks (nodes) and lines (edges). Each block has a type, a title, its place on the canvas
and settings checked by the model of its type. A block's exits are where lines start: one per button of an
Opening, Choice or Answer block, "done" for a lead block, "book" and "more" for a treatment card, and
"no_match" for typed text nothing matched. A line joins one exit to the next block.

check() finds problems: structural ones (unknown block or exit, two lines from one exit, no Opening block)
refuse the save; loose ends block a publish; unreachable blocks are warnings. import_content() turns
today's chat (the clinic's content file: menu, 19 pages, booking questions) into the first flow, laid out
left to right.
See frontend/crm/WORKFLOW-CANVAS-PLAN.md."""

import re
from collections import deque
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

ID = r"^[a-z0-9][a-z0-9_-]{0,47}$"
MAX_NODES, MAX_EDGES, MAX_BUTTONS = 200, 600, 12


# What a button does by itself, with no line and no extra block (keeps the canvas simple). Empty: the button
# leads on to the next block along its line.
BUTTON_ACTIONS = Literal["", "link", "call", "whatsapp", "treatment", "callback", "book"]


class Button(BaseModel):
    id: str = Field(pattern=ID)  # the exit name a line starts from (when it has no action of its own)
    label: str = Field(min_length=1, max_length=40)
    icon: str = Field(default="", max_length=20)
    variant: Literal["", "wa", "sos", "primary"] = ""
    visible: bool = True
    action: BUTTON_ACTIONS = ""
    # link / whatsapp: https address; call: number; treatment: its name (shows its card);
    # callback: what it is about; book: the treatment filled in
    value: str = Field(default="", max_length=600)


class Figure(BaseModel):
    value: str = Field(max_length=12)
    label: str = Field(max_length=24)


# ---------- block settings, one model per type ----------
class OpeningSettings(BaseModel):
    """The chat opens: welcome, trust figures, the main buttons (each a trigger)."""

    welcome: str = Field(default="", max_length=500)
    figures: list[Figure] = Field(default=[], max_length=3)
    fallback: str = Field(default="", max_length=300)
    buttons: list[Button] = Field(default=[], max_length=MAX_BUTTONS)


class ChoiceSettings(BaseModel):
    """A message with buttons; each button is its own exit (a sub-menu)."""

    message: str = Field(default="", max_length=1500)
    buttons: list[Button] = Field(default=[], max_length=MAX_BUTTONS)


class TreatmentListSettings(BaseModel):
    """The treatments of one category, live from Clinic info → Services (shown ones, in order); each opens its
    card. Extra buttons (e.g. "Not sure, help me choose") are its own and lead on along their lines."""

    message: str = Field(default="", max_length=1500)
    category: str = Field(default="", max_length=40)  # a Services category, e.g. Hair transplant
    buttons: list[Button] = Field(default=[], max_length=MAX_BUTTONS)


class AnswerSettings(BaseModel):
    """Fixed text, optionally with buttons."""

    text: str = Field(min_length=1, max_length=2000)
    buttons: list[Button] = Field(default=[], max_length=MAX_BUTTONS)


FIELDS = Literal["name", "phone", "email", "treatment", "doctor", "date", "time", "booked_date", "reason"]


class LeadSettings(BaseModel):
    """Booking, online consult, cancel, reschedule, call back: as a form or one question at a time."""

    mode: Literal["steps", "form"] = "steps"
    fields: list[FIELDS] = Field(default=["name", "phone"], max_length=9)
    treatment: str = Field(default="", max_length=80)  # filled in (e.g. "Book for Beard Transplant")
    topic: str = Field(default="", max_length=120)  # call back: what it is about
    read_back: bool = True
    final_message: str = Field(default="", max_length=500)


class TreatmentSettings(BaseModel):
    treatment: str = Field(min_length=1, max_length=80)  # a treatment from Clinic info → Services


class DoctorSettings(BaseModel):
    """A doctor's profile card: name, title, qualifications, photo, a few figures, Book with, full profile."""

    doctor: str = Field(min_length=1, max_length=80)  # the name, as in the CRM's Doctors
    title: str = Field(default="", max_length=120)  # e.g. Founder and Director
    qualifications: str = Field(default="", max_length=300)
    photo: str = Field(default="", max_length=300, pattern=r"^(https://\S+)?$")
    about: str = Field(default="", max_length=1000)
    stats: list[Figure] = Field(default=[], max_length=6)  # e.g. 20+ Years experience
    book_label: str = Field(
        default="", max_length=40
    )  # "Book with Dr ..." (empty: no button); a line to a booking
    profile_url: str = Field(default="", max_length=600, pattern=r"^(https://\S+)?$")  # "Read full profile"


class LinkSettings(BaseModel):
    url: str = Field(max_length=600, pattern=r"^https://\S+$")


class CallSettings(BaseModel):
    number: str = Field(max_length=16, pattern=r"^\+?\d{3,15}$")


class TriggerSettings(BaseModel):
    """Typed message: the patient types instead of tapping (e.g. "how much does it cost?"). The topic's
    approved phrases (staff approved, no self-training) lead into the flow here."""

    topic: str = Field(min_length=1, max_length=40)  # e.g. cost, clinic, results
    phrases: list[str] = Field(default=[], max_length=200)  # examples shown on the block


TYPES: dict[str, type[BaseModel]] = {
    "opening": OpeningSettings,
    "typed": TriggerSettings,
    "choice": ChoiceSettings,
    "appointment_menu": ChoiceSettings,  # Book / online / cancel / reschedule
    "treatment_categories": ChoiceSettings,  # main treatment list
    "treatment_list": TreatmentListSettings,  # sub list: one category's treatments, live from Services
    "doctor_list": ChoiceSettings,
    "answer": AnswerSettings,
    "book": LeadSettings,
    "online": LeadSettings,
    "cancel": LeadSettings,
    "reschedule": LeadSettings,
    "callback": LeadSettings,
    "treatment_card": TreatmentSettings,
    "doctor_card": DoctorSettings,
    "link": LinkSettings,
    "whatsapp": LinkSettings,
    "call": CallSettings,
    "emergency": AnswerSettings,
}
LEAD_TYPES = {"book", "online", "cancel", "reschedule", "callback"}
MENUS = {"opening", "choice", "appointment_menu", "treatment_categories", "treatment_list", "doctor_list"}


class Node(BaseModel):
    id: str = Field(pattern=ID)
    type: Literal[
        "opening", "typed", "appointment_menu", "treatment_categories", "treatment_list", "doctor_list",
        "choice", "answer", "book", "online", "cancel", "reschedule", "callback", "treatment_card",
        "doctor_card", "link", "whatsapp", "call", "emergency", "set_field",
    ]  # fmt: skip
    title: str = Field(default="", max_length=60)
    x: float = 0
    y: float = 0
    settings: dict[str, Any] = {}
    # ON/OFF: an off block is hidden from patients, with the buttons that lead to it. A schedule shows it only
    # between two days (both included) and/or only while the clinic is open.
    enabled: bool = True
    show_from: date | None = None
    show_until: date | None = None
    clinic_hours_only: bool = False


class Edge(BaseModel):
    source: str = Field(pattern=ID)  # block id
    exit: str = Field(pattern=ID)  # the exit of that block
    target: str = Field(pattern=ID)  # the next block


class Flow(BaseModel):
    nodes: list[Node] = Field(default=[], max_length=MAX_NODES)
    edges: list[Edge] = Field(default=[], max_length=MAX_EDGES)
    fields: list["FieldDef"] = Field(default=[], max_length=50)  # the clinic's own fields


# Fields: values saved during a chat, used in messages as {name}. The built-in ones are filled by the chat
# itself (questions, the source of the visit); a clinic adds its own and fills them with Set field blocks.
BUILT_IN_FIELDS = {
    "name",
    "phone",
    "email",
    "treatment",
    "doctor",
    "date",
    "time",
    "booked_date",
    "reason",
    "source",
}
FIELD = r"^[a-z][a-z0-9_]{1,29}$"


class FieldDef(BaseModel):
    key: str = Field(pattern=FIELD)  # used as {key} in messages
    label: str = Field(min_length=1, max_length=40)
    kind: Literal["text", "number", "date", "choice"] = "text"
    options: list[str] = Field(default=[], max_length=20)  # for choice


class SetFieldSettings(BaseModel):
    """Saves a value into a field, e.g. interest = Hair transplant, then goes on."""

    field: str = Field(pattern=FIELD)
    value: str = Field(default="", max_length=200)  # may use other fields, e.g. {treatment}


class Problem(BaseModel):
    level: Literal["error", "warning"]  # error: publish is blocked
    node: str
    message: str


TYPES["set_field"] = SetFieldSettings
Flow.model_rebuild()
_settings = {t: TypeAdapter(m) for t, m in TYPES.items()}


def settings_of(node: Node) -> BaseModel:
    """The block's settings checked against its type (ValueError with the field when wrong)."""
    model: BaseModel = _settings[node.type].validate_python(node.settings)
    return model


def exits(node: Node) -> list[str]:
    s = settings_of(node)
    out = [b.id for b in getattr(s, "buttons", []) if not b.action]
    if node.type in ("typed", "set_field"):
        out.append("next")
    if node.type in LEAD_TYPES:
        out.append("done")
    if isinstance(s, DoctorSettings) and s.book_label:
        out.append("book")
    if node.type == "treatment_card":
        out += ["book", "more"]
    if node.type in MENUS:
        out.append("no_match")  # typed text nothing matched (optional line; the fallback answers otherwise)
    return out


class FlowError(ValueError):
    """The flow cannot be saved as it is (the message says where)."""


def normalise(raw: dict[str, Any]) -> dict[str, Any]:
    """Checks the flow's structure and each block's settings. Raises FlowError; returns the clean flow."""
    flow = Flow.model_validate(raw)
    ids = [n.id for n in flow.nodes]
    if len(ids) != len(set(ids)):
        raise FlowError("Two blocks have the same id.")
    if [n.type for n in flow.nodes].count("opening") != 1 and flow.nodes:
        raise FlowError("A flow needs exactly one Opening block.")
    keys = [f.key for f in flow.fields]
    if len(keys) != len(set(keys)) or set(keys) & BUILT_IN_FIELDS:
        raise FlowError("Each field needs its own name, not one of the built-in fields.")
    known = BUILT_IN_FIELDS | set(keys)
    for n in flow.nodes:
        if n.type == "set_field" and n.settings.get("field") not in known:
            raise FlowError(f"Block '{n.title or n.id}' sets a field that does not exist.")
    by_id = {n.id: n for n in flow.nodes}
    clean_nodes = []
    for n in flow.nodes:
        try:
            s = settings_of(n)
        except ValueError as err:
            msg = err.errors()[0]["msg"] if hasattr(err, "errors") else str(err)
            raise FlowError(f"Block '{n.title or n.id}': {msg}") from None
        buttons = [b.id for b in getattr(s, "buttons", [])]
        if len(buttons) != len(set(buttons)):
            raise FlowError(f"Block '{n.title or n.id}' has two buttons with the same id.")
        if n.show_from and n.show_until and n.show_from > n.show_until:
            raise FlowError(f"Block '{n.title or n.id}': the schedule ends before it starts.")
        if n.type == "opening" and not n.enabled:
            raise FlowError("The Opening block cannot be off (turn the chatbot off in Appearance instead).")
        clean_nodes.append(n.model_copy(update={"settings": s.model_dump()}))
    seen: set[tuple[str, str]] = set()
    for e in flow.edges:
        if e.source not in by_id or e.target not in by_id:
            raise FlowError("A line joins a block that does not exist.")
        if e.exit not in exits(by_id[e.source]):
            raise FlowError(f"Block '{by_id[e.source].title or e.source}' has no exit '{e.exit}'.")
        if (e.source, e.exit) in seen:
            raise FlowError(f"Two lines start from the same exit of '{by_id[e.source].title or e.source}'.")
        seen.add((e.source, e.exit))
    return Flow(nodes=clean_nodes, edges=flow.edges, fields=flow.fields).model_dump(mode="json")


def check(raw: dict[str, Any]) -> list[Problem]:
    """Loose ends (errors: a visible button with no line) and unreachable blocks (warnings)."""
    flow = Flow.model_validate(raw)
    if not flow.nodes:
        return [Problem(level="error", node="", message="The flow is empty: add an Opening block.")]
    out: list[Problem] = []
    linked = {(e.source, e.exit) for e in flow.edges}
    for n in flow.nodes:
        if not n.enabled:
            out.append(
                Problem(level="warning", node=n.id, message="Off: hidden from patients, with its buttons.")
            )
            continue
        for b in getattr(settings_of(n), "buttons", []):
            if b.visible and not b.action and (n.id, b.id) not in linked:
                out.append(Problem(level="error", node=n.id, message=f"Button '{b.label}' leads nowhere."))
    known = BUILT_IN_FIELDS | {f.key for f in flow.fields}
    for n in flow.nodes:
        texts = [str(v) for k, v in n.settings.items() if isinstance(v, str)]
        for name in sorted({m for t in texts for m in re.findall(r"\{([a-z][a-z0-9_]*)\}", t)} - known):
            out.append(Problem(level="error", node=n.id, message=f"Uses {{{name}}}, which is not a field."))
    nxt: dict[str, list[str]] = {}
    for e in flow.edges:
        nxt.setdefault(e.source, []).append(e.target)
    starts = [n.id for n in flow.nodes if n.type in ("opening", "typed")]  # the triggers
    reached, todo = set(starts), deque(starts)
    while todo:
        for t in nxt.get(todo.popleft(), []):
            if t not in reached:
                reached.add(t)
                todo.append(t)
    for n in flow.nodes:
        if n.id not in reached:
            out.append(Problem(level="warning", node=n.id, message="Nothing leads to this block."))
    return out


# ---------- import of today's chat ----------
# Today's pages that are one of the plan's ready-made menus (the others stay a general Choice).
ROLE = {
    "book": "appointment_menu",
    "treat": "treatment_categories",
    "ht": "treatment_list",
    "hf": "treatment_list",
    "about": "doctor_list",
}
LIST_CATEGORY = {"ht": "Hair transplant", "hf": "Hair fall & scalp"}  # as Services' categories (GROUP)
STEP_FIELDS: dict[str, list[str]] = {  # the chat's booking questions today (app/chat/flows.py)
    "book": ["name", "phone", "treatment", "date", "time"],
    "online": ["name", "phone", "email", "treatment", "date", "time"],
    "cancel": ["name", "phone", "booked_date"],
    "reschedule": ["name", "phone", "booked_date", "date", "time"],
    "callback": ["name", "phone", "reason"],
}
TITLES = {
    "book": "Book appointment",
    "online": "Online consultation",
    "cancel": "Cancel appointment",
    "reschedule": "Reschedule",
    "callback": "Call back",
}


def import_content(c: dict[str, Any]) -> dict[str, Any]:
    """The clinic's chat today (content file) as a flow: an Opening block, a block per page, and a block per
    action the buttons lead to (shared when two buttons do the same thing), laid out left to right."""
    pages: dict[str, Any] = c.get("nodes") or {}
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []

    def slug(text: str) -> str:
        s = "".join(ch if ch.isalnum() else "-" for ch in text.lower()).strip("-")
        return ("-".join(p for p in s.split("-") if p) or "x")[:40]

    def add(nid: str, kind: str, title: str, settings: dict[str, Any]) -> str:
        nodes.setdefault(nid, {"id": nid, "type": kind, "title": title[:60], "settings": settings})
        return nid

    def target(o: dict[str, Any]) -> str:
        """The block a button of today's chat leads to."""
        href, action, value = o.get("href", ""), o.get("action", ""), str(o.get("value", ""))
        if href.startswith("tel:"):
            num = href[4:]
            return add("call-" + slug(num), "call", f"Call {num}", {"number": num})
        if "wa.me" in href:
            return add("whatsapp", "whatsapp", "WhatsApp", {"url": href})
        if href:
            return add("link-" + slug(o.get("label", href)), "link", o.get("label", "Link"), {"url": href})
        if action == "go" and value in pages:
            return "page-" + value
        if action == "start" and value in STEP_FIELDS:
            return add(value, value, TITLES[value], {"fields": STEP_FIELDS[value]})
        if action == "callback":
            fields = STEP_FIELDS["callback"]
            return add(
                "callback-" + slug(value),
                "callback",
                f"Call back: {value}"[:60],
                {"fields": fields, "topic": value},
            )
        if action == "book_for":
            return add(
                "book-" + slug(value),
                "book",
                f"Book: {value}"[:60],
                {"fields": STEP_FIELDS["book"], "treatment": value},
            )
        if action == "treat":
            return add("treat-" + slug(value), "treatment_card", value, {"treatment": value})
        return add("emergency", "emergency", "Emergency", {"text": "Call 108 for a medical emergency."})

    def inline(o: dict[str, Any]) -> dict[str, str] | None:
        """A button that does its job by itself (no line, no extra block): links, calls, WhatsApp, a
        treatment's card, a call back about a topic, booking a given treatment."""
        href, action, value = o.get("href", ""), o.get("action", ""), str(o.get("value", ""))
        if href.startswith("tel:"):
            return {"action": "call", "value": href[4:]}
        if "wa.me" in href:
            return {"action": "whatsapp", "value": href}
        if href:
            return {"action": "link", "value": href}
        if action == "treat":
            return {"action": "treatment", "value": value}
        if action == "callback":
            return {"action": "callback", "value": value}
        if action == "book_for":
            return {"action": "book", "value": value}
        return None

    def buttons_and_lines(
        source: str, options: list[dict[str, Any]], prefix: str = "b"
    ) -> list[dict[str, Any]]:
        out = []
        for i, o in enumerate(options[:MAX_BUTTONS]):
            bid = f"{prefix}{i + 1}"
            variant = o.get("variant") or ("primary" if o.get("primary") else "")
            button = {"id": bid, "label": o["label"][:40], "icon": o.get("icon", ""), "variant": variant}
            own = inline(o)
            if own and not (source == "opening" and o.get("variant") == "sos"):
                button |= own
            else:
                edges.append({"source": source, "exit": bid, "target": target(o)})
            out.append(button)
        return out

    for key, page in pages.items():
        nid = "page-" + key
        msgs = page.get("messages") or []
        text = "\n".join(m.get("text", "") for m in msgs if m.get("text")).strip()
        ui = page.get("ui") or {}
        if ui.get("type") == "doctor_card":
            opts = ui.get("options", [])
            book = next((o for o in opts if o.get("action") == "start"), None)
            profile = next((o.get("href", "") for o in opts if o.get("href", "").startswith("https://")), "")
            stats = [{"value": f["value"][:12], "label": f["label"][:24]} for f in ui.get("stats", [])][:6]
            add(nid, "doctor_card", ui.get("name") or key, {
                "doctor": ui.get("name") or key, "title": ui.get("title", ""),
                "qualifications": ui.get("quals", ""), "stats": stats,
                "book_label": book["label"][:40] if book else "", "profile_url": profile,
            })  # fmt: skip
            if book:
                edges.append({"source": nid, "exit": "book", "target": target(book)})
            continue
        title = key.replace("_", " ").title()
        if key == "emergency":
            nodes[nid] = {
                "id": nid,
                "type": "emergency",
                "title": "Emergency",
                "settings": {"text": text or "Call 108."},
            }
            nodes[nid]["settings"]["buttons"] = buttons_and_lines(nid, ui.get("options", []))
            continue
        kind = ROLE.get(key, "choice") if ui.get("options") else "answer"
        if kind == "treatment_list":  # treatments come live from Services; keep only the other buttons
            others = [o for o in ui.get("options", []) if o.get("action") != "treat"]
            nodes[nid] = {"id": nid, "type": kind, "title": title, "settings": {}}
            nodes[nid]["settings"] = {
                "message": text, "category": LIST_CATEGORY.get(key, ""),
                "buttons": buttons_and_lines(nid, others),
            }  # fmt: skip
            continue
        nodes[nid] = {"id": nid, "type": kind, "title": title, "settings": {}}
        btns = buttons_and_lines(nid, ui.get("options", []))
        nodes[nid]["settings"] = (
            {"message": text, "buttons": btns}
            if kind == "choice"
            else {"text": text or title, "buttons": btns}
        )

    menu = [
        dict(item, action="go", value="emergency")
        if item.get("variant") == "sos" and "emergency" in pages
        else item
        for item in (c.get("menu") or {}).get("items", [])
    ]
    opening_buttons = buttons_and_lines("opening", menu, prefix="m")
    reviews = c.get("reviews") or {}
    nodes["opening"] = {
        "id": "opening",
        "type": "opening",
        "title": "Opening",
        "settings": {
            "welcome": c.get("greeting") or (c.get("config") or {}).get("greeting", ""),
            "figures": [{"value": f"{reviews['rating']}★", "label": "Google rating"}]
            if reviews.get("rating")
            else [],
            "buttons": opening_buttons,
        },
    }
    edges = [e for e in edges if e["target"] in nodes]  # a page that does not exist is left as a loose end
    # Pages no button leads to are reached by typing ("how much does it cost?"): a Typed trigger for each.
    reached, todo = {"opening"}, deque(["opening"])
    while todo:
        cur = todo.popleft()
        for e in edges:
            if e["source"] == cur and e["target"] not in reached:
                reached.add(e["target"])
                todo.append(e["target"])
    for key in pages:
        if "page-" + key not in reached and not any(e["target"] == "page-" + key for e in edges):
            tid = "typed-" + slug(key)
            add(tid, "typed", f"Typed: {key.replace('_', ' ')}", {"topic": key[:40]})
            edges.append({"source": tid, "exit": "next", "target": "page-" + key})
    _layout(nodes, edges)
    return normalise({"nodes": list(nodes.values()), "edges": edges})


GAP_X, GAP_Y = 340.0, 40.0


def _height(n: dict[str, Any]) -> float:
    """About how tall a block is drawn on the canvas: its header, then one row per button or exit."""
    rows = len(n["settings"].get("buttons", [])) + (1 if n["type"] in MENUS else 0)
    rows += 12 if n["type"] == "treatment_list" else 0  # its treatments come live from Services
    rows += 1 if n["type"] in LEAD_TYPES or n["type"] == "typed" else 0
    return 90.0 + rows * 26.0


def _layout(nodes: dict[str, dict[str, Any]], edges: list[dict[str, str]]) -> None:
    """One lane per trigger (each main button's flow, then each Typed trigger's): depth left to right, blocks
    in a column stacked by their real height. The lanes are then packed side by side into columns so the
    whole flow is about as wide as a screen (16:9), not one tall strip. A block reached from two lanes stays
    in the first; unreached blocks go last."""
    nxt: dict[str, list[str]] = {}
    for e in edges:
        nxt.setdefault(e["source"], []).append(e["target"])
    firsts: list[str] = []
    placed: set[str] = set()
    if "opening" in nodes:
        placed.add("opening")
        firsts = [e["target"] for e in edges if e["source"] == "opening"]
    firsts += [nid for nid, n in nodes.items() if n["type"] == "typed"]
    lanes: list[tuple[list[tuple[str, int, float]], int, float]] = []  # blocks (id, column, y), width, height
    for first in firsts:
        if first in placed:
            continue
        bottom: dict[int, float] = {}
        blocks: list[tuple[str, int, float]] = []
        todo = deque([(first, 0)])
        while todo:
            nid, col = todo.popleft()
            if nid in placed:
                continue
            placed.add(nid)
            y = bottom.get(col, 0.0)
            blocks.append((nid, col, y))
            bottom[col] = y + _height(nodes[nid]) + GAP_Y
            todo.extend((t, col + 1) for t in nxt.get(nid, []) if t not in placed)
        lanes.append((blocks, max(bottom) + 1, max(bottom.values())))
    # Pack the lanes into k side-by-side columns; choose k whose overall shape is closest to 16:9.
    best: list[list[int]] = [list(range(len(lanes)))] if lanes else []
    if lanes:
        total = sum(h for _, _, h in lanes)
        best_score = float("inf")
        for k in range(1, len(lanes) + 1):
            limit = max(total / k, max(h for _, _, h in lanes))
            cols: list[list[int]] = []
            cur: list[int] = []
            used = 0.0
            for i, (_, _, h) in enumerate(lanes):
                if cur and used + h > limit:
                    cols.append(cur)
                    cur, used = [], 0.0
                cur.append(i)
                used += h + 60.0
            cols.append(cur)
            width = sum(max(lanes[i][1] for i in c) for c in cols) * GAP_X
            height = max(sum(lanes[i][2] + 60.0 for i in c) for c in cols)
            score = abs(width / max(height, 1.0) - 16 / 9)
            if score < best_score:
                best, best_score = cols, score
    x0 = GAP_X if "opening" in nodes else 0.0
    if "opening" in nodes:
        nodes["opening"]["x"], nodes["opening"]["y"] = 0.0, 0.0
    for packed in best:
        y0 = 0.0
        for i in packed:
            blocks, _, h = lanes[i]
            for nid, c, y in blocks:
                nodes[nid]["x"], nodes[nid]["y"] = x0 + c * GAP_X, y0 + y
            y0 += h + 60.0
        x0 += max(lanes[i][1] for i in packed) * GAP_X + 60.0
    rest = [nid for nid in nodes if nid not in placed]
    for i, nid in enumerate(rest):
        nodes[nid]["x"], nodes[nid]["y"] = x0 + (i % 3) * GAP_X, (i // 3) * 260.0
