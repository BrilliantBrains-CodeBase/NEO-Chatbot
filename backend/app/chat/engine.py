"""The conversation: what the bot answers to each event. Same behaviour as the approved mock
(frontend/widgets/mock/engine.ts). B3: greeting, menu, fixed answers, treatment cards.
Booking steps, typed text and leads follow in the next steps.
"""

from dataclasses import dataclass, field
from typing import Any

from app.chat import flows, understand
from app.chat.content import content
from app.chat.schemas import BotMessage, ChatRequest, ChatResponse, Input, Payload
from app.chat.store import State

NO_ANSWER = (
    "I don't have a confirmed answer for that yet. Share your number and our team will call you back "
    "with the right information."
)
MAIN_MENU_TEXT = "How can I help you today?"


@dataclass
class Turn:
    reply: ChatResponse
    answered_by: str
    state: State = field(default_factory=dict)
    completed: dict[str, Any] | None = None  # a flow the patient just finished: the service saves it


def _response(raw: dict[str, Any]) -> ChatResponse:
    return ChatResponse(
        messages=[BotMessage(text=m["text"]) for m in raw.get("messages", [])],
        ui=raw.get("ui"),
        input=Input(**raw.get("input", {})),
    )


def shown_choices(ui: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The tappable buttons of a reply (for transcript labels and, later, typed text that means a tap)."""
    if not ui or ui.get("type") not in ("menu", "chips", "doctor_card"):
        return []
    items = ui["items"] if ui["type"] == "menu" else list(ui.get("options", []))
    if ui["type"] != "menu":
        if ui.get("back"):
            items.append({**ui["back"], "label": "Back"})
        if ui.get("main"):
            items.append({"label": "Main menu", "action": "menu"})
    return [c for c in items if c.get("action")]


def treatment_card(c: dict[str, Any], name: str) -> ChatResponse | None:
    info = c["treatments"].get(name)
    if not info:
        return None
    return ChatResponse(
        messages=[BotMessage(text=f"**{name}**\n{info['text']}")],
        ui={
            "type": "chips",
            "options": [
                {"label": f"Book for {name}", "action": "book_for", "value": name, "primary": True},
                {"label": "Read more on our website", "href": c["site"] + info["path"]},
            ],
            "back": {"label": "Back", "action": "go", "value": info["list"]},
            "main": True,
        },
    )


def respond(
    req: ChatRequest, state: State, slots: dict[str, list[str]] | None = None, kb_answer: str | None = None
) -> Turn:
    """slots: free slots per day from the database; the service loads them while a booking is open.
    kb_answer: the approved knowledge base answer for typed text, if one matched (service)."""
    c = content(req.client_id)
    if c is None:  # a clinic without content yet: greet, never fail
        return Turn(ChatResponse(messages=[BotMessage(text=MAIN_MENU_TEXT)]), "menu", {})
    if slots is not None:
        c = {**c, "config": {**c["config"], "slots_by_day": slots}}
    menu = ChatResponse(messages=[BotMessage(text=c["greeting"])], ui=c["menu"])

    if req.event in ("start", "restart"):
        return Turn(menu, "menu", {})

    flow = state.get("flow")
    if req.event == "button":
        action, value = req.payload.action or "", req.payload.value
        cfg = c["config"]
        if action == "start" and value in ("book", "online", "cancel", "reschedule", "callback"):
            return _flow(*flows.start(value))
        if action == "book_for" and value:
            option = value if value in cfg["treatments"] else c["booking_option"].get(value)
            return _flow(*flows.start("book", treatment=option))
        if action == "callback":
            return _flow(*flows.start("callback", reason=value or None))
        if flow and action not in ("menu", "go", "treat"):
            return _step(flow, flows.button(flow, cfg, action, value))
        # Earlier buttons stay usable (approved mockups), so a tap is checked against the clinic's
        # content, not only the latest buttons: anything that is not a real answer gets the menu again.
        if action == "go" and value in c["nodes"]:
            return Turn(_response(c["nodes"][value]), "flow", {})
        if action == "treat" and value:
            card = treatment_card(c, value)
            if card:
                return Turn(card, "flow", {})
        return Turn(ChatResponse(messages=[BotMessage(text=MAIN_MENU_TEXT)], ui=c["menu"]), "menu", {})

    return _text(req, state, c, kb_answer)


NOTED = "I don't have a confirmed answer for that yet. I have noted your question for our team."
STOPPED = "No problem. How else can I help you?"
NOT_AVAILABLE_DATE = flows.NOT_AVAILABLE_DATE
NOT_AVAILABLE_TIME = flows.NOT_AVAILABLE_TIME
INPUT_STEPS = {"name", "phone", "email", "reason", "cb_reason"}


def _text(req: ChatRequest, state: State, c: dict[str, Any], kb_answer: str | None = None) -> Turn:
    """Typed text: emergency first, then anything that stands for a tap, then the open step or the rules."""
    text = (req.payload.text or "").strip()
    flow = state.get("flow")
    kind, target = understand.route(text, c)
    if kind == "emergency":  # always first, and never mistaken for a tap
        return Turn(_response(c["nodes"]["emergency"]), "rule", {})
    low = " ".join(text.lower().split())
    if flow and flow["step"] in INPUT_STEPS and understand.REFUSAL.match(low):
        # "no" to a form question ends the form; nothing is saved.
        return Turn(ChatResponse(messages=[BotMessage(text=STOPPED)], ui=c["menu"]), "menu", {})
    if understand.IDENTITY.search(low):
        if flow:
            return _flow(flow, flows.ask(flow, c["config"], [c["greeting"]]), answered_by="rule")
        return Turn(ChatResponse(messages=[BotMessage(text=c["greeting"])], ui=c["menu"]), "rule", {})
    tap = _typed_tap(state, c, flow, text)
    if isinstance(tap, Turn):
        return tap
    if tap:
        tap_req = req.model_copy(update={"event": "button", "payload": Payload(**tap)})
        return respond(tap_req, state, c["config"].get("slots_by_day"))
    if flow:
        cfg = c["config"]
        exact = flow["step"] == "treatment" and any(t.lower() == text.lower() for t in cfg["treatments"])
        if (flow["step"] in INPUT_STEPS and "?" not in text) or exact:
            return _step(flow, flows.typed(flow, cfg, text, req.payload.cc))
        return _mid_flow(flow, c, text, kind, target, kb_answer)
    return _answer(c, text, kind, target, kb_answer)


def _typed_tap(
    state: State, c: dict[str, Any], flow: flows.Flow | None, text: str
) -> dict[str, Any] | Turn | None:
    """The tap that typed text stands for; a reply when it names a date or time that cannot be booked."""
    if understand.is_menu(text):
        return {"action": "menu"}
    cfg = c["config"]
    if flow and flow["step"] in ("date", "booked_date"):
        day = understand.parse_date(text, flows.ist_now()[0])
        if day:
            ok = flows.bookable(cfg, day) if flow["step"] == "date" else flows.valid_booked_date(cfg, day)
            if ok:
                return {"action": flow["step"], "value": day}
            return Turn(flows.ask(flow, cfg, [NOT_AVAILABLE_DATE]), "flow", {"flow": flow})
    if flow and flow["step"] == "time" and flow.get("date"):
        time = understand.parse_time(text)
        if time:
            if time == "any" or time in flows.slots_for(cfg, flow["date"]):
                return {"action": "time", "value": time}
            return Turn(flows.ask(flow, cfg, [NOT_AVAILABLE_TIME]), "flow", {"flow": flow})
    if flow and flow["step"] == "summary" and understand.is_yes(text):
        return {"action": "confirm"}
    # Only the buttons of the latest reply (never older ones: a typed name must not tap an old button).
    option = understand.match_option(text, state.get("last_shown", []))
    return {"action": option["action"], "value": option.get("value")} if option else None


def _mid_flow(
    flow: flows.Flow, c: dict[str, Any], text: str, kind: str, target: str, kb_answer: str | None = None
) -> Turn:
    """A question in the middle of a flow: a short answer (or noted for the team), then the same step."""
    cfg = c["config"]
    if kind == "start" and target != flow["kind"]:
        return _flow(*flows.start(target))
    if kind == "node" and target in c["brief"]:
        return _flow(flow, flows.ask(flow, cfg, [c["brief"][target]]), answered_by="rule")
    if kind == "card":
        card_text = f"**{target}**\n{c['treatments'][target]['text']}"
        return _flow(flow, flows.ask(flow, cfg, [card_text]), answered_by="rule")
    if kind == "node" and target == "book":
        return _flow(flow, flows.ask(flow, cfg))
    if kb_answer:  # answered from the approved knowledge base, then the same step again
        return _flow(flow, flows.ask(flow, cfg, [kb_answer]), answered_by="kb")
    flow.setdefault("questions", []).append(text[:500])  # saved for the team with the lead (B6)
    return _flow(flow, flows.ask(flow, cfg, [NOTED]), answered_by="lead")


def _answer(c: dict[str, Any], text: str, kind: str, target: str, kb_answer: str | None = None) -> Turn:
    """Typed text with no flow open: the keyword rules, then the approved knowledge base. Medical, or
    nothing known, becomes a lead."""
    if kind == "start":
        return _flow(*flows.start(target))
    if kind == "node" and target in c["nodes"]:
        return Turn(_response(c["nodes"][target]), "rule", {})
    if kind == "card":
        card = treatment_card(c, target)
        if card:
            return Turn(card, "rule", {})
    if kb_answer:
        return Turn(ChatResponse(messages=[BotMessage(text=kb_answer)], ui=c["menu"]), "kb", {})
    return _flow(*flows.start("question", reason=text[:500], lead=[NO_ANSWER]), answered_by="lead")


def _flow(flow: flows.Flow | None, reply: ChatResponse, answered_by: str = "flow") -> Turn:
    return Turn(reply, answered_by, {"flow": flow} if flow else {})


def _step(flow: flows.Flow, result: tuple[flows.Flow | None, ChatResponse]) -> Turn:
    """A step of the open flow. A flow only ends by being finished, so no flow left means: save it."""
    turn = _flow(*result)
    if result[0] is None:
        turn.completed = flow
    return turn


SLOT_TAKEN = "Sorry, that time was just booked by someone else. Please choose another time."


def slot_taken(req: ChatRequest, flow: flows.Flow, slots: dict[str, list[str]] | None) -> Turn:
    """The chosen time went to another patient while this one was confirming: pick again, fresh slots."""
    c = content(req.client_id)
    assert c is not None  # a flow only runs for a clinic with content
    cfg = {**c["config"], "slots_by_day": slots or {}}
    day_left = flow["date"] in cfg["slots_by_day"]
    again = {**flow, "time": None, "step": "time" if day_left else "date"}
    return _flow(again, flows.ask(again, cfg, [SLOT_TAKEN]))
