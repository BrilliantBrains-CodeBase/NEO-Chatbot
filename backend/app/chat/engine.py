"""The conversation: what the bot answers to each event. Same behaviour as the approved mock
(frontend/widgets/mock/engine.ts). B3: greeting, menu, fixed answers, treatment cards.
Booking steps, typed text and leads follow in the next steps.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.chat import context, flows, intents, understand
from app.chat.content import content
from app.chat.schemas import BotMessage, ChatRequest, ChatResponse, Input, Payload
from app.chat.store import State

NO_ANSWER = (
    "I don't have a confirmed answer for that yet. Would you like our team to call you back with the right "
    "information?"
)
OFFER_UI = {
    "type": "chips",
    "options": [
        {"label": "Yes, call me back", "action": "ask_team", "primary": True},
        {"label": "No, thanks", "action": "menu"},
    ],
}
MAIN_MENU_TEXT = "How can I help you today?"
WHICH = "Sure. Which one would you like to know more about?"
# Under an answer: only the "Main menu" link. The full menu cards show above the message and pushed the
# answer out of view.
AFTER_ANSWER: dict[str, Any] = {"type": "chips", "options": [], "main": True}


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
    req: ChatRequest, state: State, slots: dict[str, list[str]] | None = None, kb_answer: str | None = None,
    intent: str | None = None,
) -> Turn:  # fmt: skip
    """slots: free slots per day from the database; the service loads them while a booking is open.
    kb_answer: the approved knowledge base answer for typed text, if one matched (service).
    intent: the topic of typed text from approved example phrases, when no rule or answer fitted (service)."""
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
        if action == "ask_team":  # yes to "would you like our team to call you back?"
            reason = state.get("pending_q") or "Asked our team a question"
            return _flow(*flows.start("question", reason=reason))
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

    return _text(req, state, c, kb_answer, intent)


NOTED = "I don't have a confirmed answer for that yet. I have noted your question for our team."
ACTIONS = {"book", "talk", "treat"}  # rule targets that do something (or list buttons), not just inform
QUESTION_START = re.compile(r"(what|which|how|why|does|do|is|are|can)\b")
BOOK_WORDS = re.compile(r"\b(book\w*|appointment|slots?|schedule)\b")


def _acts(kind: str, target: str, text: str) -> bool:
    """A rule that does something (book, talk to us, the treatment list) goes before an approved answer. But a
    question about the consultation ("what is included in the consultation") is not a wish to book."""
    if kind != "node" or target not in ACTIONS:
        return False
    low = text.lower().strip()
    return not (target == "book" and QUESTION_START.match(low) and not BOOK_WORDS.search(low))


THANKS = "You're welcome! Is there anything else I can help you with?"
BYE = "Thank you for chatting with us. Take care!"
STOPPED = "No problem. How else can I help you?"
NOT_AVAILABLE_DATE = flows.NOT_AVAILABLE_DATE
NOT_AVAILABLE_TIME = flows.NOT_AVAILABLE_TIME
INPUT_STEPS = {"name", "phone", "email", "reason", "cb_reason"}


def _text(
    req: ChatRequest, state: State, c: dict[str, Any], kb_answer: str | None = None, intent: str | None = None
) -> Turn:
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
    if understand.IDENTITY.search(low) or intent == "identity":
        if flow:
            return _flow(flow, flows.ask(flow, c["config"], [c["greeting"]]), answered_by="rule")
        return Turn(ChatResponse(messages=[BotMessage(text=c["greeting"])], ui=c["menu"]), "rule", {})
    tap = _typed_tap(state, c, flow, text)
    if isinstance(tap, Turn):
        return tap
    if tap:
        tap_req = req.model_copy(update={"event": "button", "payload": Payload(**tap)})
        return respond(tap_req, state, c["config"].get("slots_by_day"))
    if state.get("pending_q") and not flow:  # typed answer to "would you like our team to call you back?"
        if understand.is_yes(text):
            yes = req.model_copy(update={"event": "button", "payload": Payload(action="ask_team")})
            return respond(yes, state)
        if understand.REFUSAL.match(low):
            return Turn(ChatResponse(messages=[BotMessage(text=STOPPED)], ui=c["menu"]), "menu", {})
    in_form = bool(flow and flow["step"] in INPUT_STEPS)
    if context.is_vague(text) and not in_form:
        return _vague(state, c, flow)
    chat = understand.small_talk(low) or (intent if intent in intents.SMALL_TALK else None)
    if chat and not (flow and flow["step"] in INPUT_STEPS):
        said = {"greeting": c["greeting"], "thanks": THANKS, "bye": BYE, "ok": MAIN_MENU_TEXT}[chat]
        if flow:  # a booking stays open: the same step again
            return _flow(
                flow, flows.ask(flow, c["config"], [] if chat == "ok" else [said]), answered_by="rule"
            )
        return Turn(ChatResponse(messages=[BotMessage(text=said)], ui=c["menu"]), "menu", {})
    if flow:
        cfg = c["config"]
        exact = flow["step"] == "treatment" and any(t.lower() == text.lower() for t in cfg["treatments"])
        question_at_name = flow["step"] == "name" and understand.NOT_A_NAME.search(low)
        if (flow["step"] in INPUT_STEPS and "?" not in text and not question_at_name) or exact:
            return _step(flow, flows.typed(flow, cfg, text, req.payload.cc))
    # The question as meant in this chat: "how long?" after PRP is "how long ... PRP Treatment".
    question = context.resolve(text, state, c)
    if question != text:
        kind, target = understand.route(question, c)
    if kind == "lead" and intent and not kb_answer and not understand.MEDICAL.search(question.lower()):
        # No keyword rule fitted, but an approved example phrase did ("kab aa sakta hoon" -> book).
        if intent in intents.STARTS:
            kind, target = "start", intent
        elif intent in c["nodes"]:
            kind, target = "node", intent
    # A follow-up about a detail of the topic is not answered by showing the topic's card again.
    follow_up = question != text and kind == "card" and target == state.get("topic")
    if flow:
        return _mid_flow(flow, c, question, kind, target, kb_answer, follow_up)
    return _answer(c, question, kind, target, kb_answer, follow_up)


def wants_intent(req: ChatRequest, state: State, question: str) -> bool:
    """Whether the service should look for the topic in the example phrases: typed text that no keyword rule,
    small talk or follow-up already covers, and that is not a typed answer to a form step."""
    c = content(req.client_id)
    text = (req.payload.text or "").strip()
    low = " ".join(text.lower().split())
    flow = state.get("flow")
    if req.event != "text" or c is None or not low:
        return False
    if flow and flow["step"] in INPUT_STEPS and not understand.NOT_A_NAME.search(low):
        return False
    if understand.IDENTITY.search(low) or understand.small_talk(low) or understand.is_menu(text):
        return False
    return not context.is_vague(text) and understand.route(question, c) == ("lead", "")


def asked(req: ChatRequest, state: State) -> str:
    """The typed question as meant in this chat, for the knowledge base search (the service). A typed
    answer to a form step is taken as it is."""
    text = (req.payload.text or "").strip()
    c = content(req.client_id)
    flow = state.get("flow")
    in_form = flow and flow["step"] in INPUT_STEPS
    if req.event != "text" or c is None or (in_form and not understand.NOT_A_NAME.search(text.lower())):
        return text
    return context.resolve(text, state, c)


def _vague(state: State, c: dict[str, Any], flow: flows.Flow | None) -> Turn:
    """ "Tell me more", "something else": read from the bot's last reply what "more" is about."""
    if flow:  # a booking is open: its step again
        return _flow(flow, flows.ask(flow, c["config"]), answered_by="rule")
    last = state.get("last_ui")
    topic = state.get("topic_now")  # a treatment talked about in the last turn
    is_card = any(o.get("action") == "book_for" for o in (last or {}).get("options", []))
    choices = [o for o in shown_choices(last) if o["action"] != "menu"]
    if topic and topic in c["treatments"] and (is_card or not choices or (last or {}).get("type") == "menu"):
        return Turn(_topic_more(c, topic), "rule", {})
    if choices:  # a list: the same list again
        return Turn(ChatResponse(messages=[BotMessage(text=WHICH)], ui=last), "rule", {})
    return Turn(ChatResponse(messages=[BotMessage(text=MAIN_MENU_TEXT)], ui=c["menu"]), "menu", {})


def _topic_more(c: dict[str, Any], topic: str) -> ChatResponse:
    info = c["treatments"][topic]
    return ChatResponse(
        messages=[BotMessage(text=f"What would you like to know about **{topic}**?")],
        ui={
            "type": "chips",
            "options": [
                {"label": "Cost", "action": "ask", "value": f"cost of {topic}"},
                {"label": f"Book for {topic}", "action": "book_for", "value": topic, "primary": True},
                {"label": "Ask our team", "action": "callback", "value": f"Question about {topic}"},
                {"label": "Read more on our website", "href": c["site"] + info["path"]},
            ],
            "main": True,
        },
    )


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
    flow: flows.Flow, c: dict[str, Any], text: str, kind: str, target: str, kb_answer: str | None = None,
    follow_up: bool = False,
) -> Turn:  # fmt: skip
    """A question in the middle of a flow: a short answer (or noted for the team), then the same step."""
    cfg = c["config"]
    if kind == "start" and target != flow["kind"]:
        return _flow(*flows.start(target))
    if kb_answer and not _acts(kind, target, text):  # the exact approved answer first
        return _flow(flow, flows.ask(flow, cfg, [kb_answer]), answered_by="kb")
    if kind == "node" and target in c["brief"]:
        return _flow(flow, flows.ask(flow, cfg, [c["brief"][target]]), answered_by="rule")
    if kind == "card" and not follow_up:
        card_text = f"**{target}**\n{c['treatments'][target]['text']}"
        return _flow(flow, flows.ask(flow, cfg, [card_text]), answered_by="rule")
    if kind == "node" and target == "book":
        return _flow(flow, flows.ask(flow, cfg))
    if kb_answer:  # answered from the approved knowledge base, then the same step again
        return _flow(flow, flows.ask(flow, cfg, [kb_answer]), answered_by="kb")
    flow.setdefault("questions", []).append(text[:500])  # saved for the team with the lead (B6)
    return _flow(flow, flows.ask(flow, cfg, [NOTED]), answered_by="lead")


def _answer(
    c: dict[str, Any], text: str, kind: str, target: str, kb_answer: str | None = None,
    follow_up: bool = False,
) -> Turn:  # fmt: skip
    """Typed text with no flow open: the keyword rules, then the approved knowledge base. Medical, or
    nothing known: the offer of a call back (the form starts only on yes)."""
    if kind == "start":
        return _flow(*flows.start(target))
    # Actions (book, talk to us) stay first; for information, an approved Q/A that matches the question is
    # more exact than a general rule ("prp cost" is not the transplant price).
    if kb_answer and not _acts(kind, target, text):
        return Turn(ChatResponse(messages=[BotMessage(text=kb_answer)], ui=AFTER_ANSWER), "kb", {})
    if kind == "node" and target in c["nodes"]:
        return Turn(_response(c["nodes"][target]), "rule", {})
    if kind == "card" and not follow_up:
        card = treatment_card(c, target)
        if card:
            return Turn(card, "rule", {})
    if kb_answer:
        return Turn(ChatResponse(messages=[BotMessage(text=kb_answer)], ui=AFTER_ANSWER), "kb", {})
    offer = ChatResponse(messages=[BotMessage(text=NO_ANSWER)], ui=OFFER_UI)
    return Turn(offer, "lead", {"pending_q": text[:500]})


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
