"""The conversation: what the bot answers to each event. Same behaviour as the approved mock
(frontend/widgets/mock/engine.ts). B3: greeting, menu, fixed answers, treatment cards.
Booking steps, typed text and leads follow in the next steps.
"""

from dataclasses import dataclass, field
from typing import Any

from app.chat.content import content
from app.chat.schemas import BotMessage, ChatRequest, ChatResponse, Input
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


def respond(req: ChatRequest, state: State) -> Turn:
    c = content(req.client_id)
    if c is None:  # a clinic without content yet: greet, never fail
        return Turn(ChatResponse(messages=[BotMessage(text=MAIN_MENU_TEXT)]), "menu", {})
    menu = ChatResponse(messages=[BotMessage(text=c["greeting"])], ui=c["menu"])

    if req.event in ("start", "restart"):
        return Turn(menu, "menu", {})

    if req.event == "button":
        action, value = req.payload.action, req.payload.value
        # Earlier buttons stay usable (approved mockups), so a tap is checked against the clinic's
        # content, not only the latest buttons: anything that is not a real answer gets the menu again.
        if action == "go" and value in c["nodes"]:
            return Turn(_response(c["nodes"][value]), "flow", {})
        if action == "treat" and value:
            card = treatment_card(c, value)
            if card:
                return Turn(card, "flow", {})
        return Turn(ChatResponse(messages=[BotMessage(text=MAIN_MENU_TEXT)], ui=c["menu"]), "menu", {})

    # Typed text: rules, flows and leads come in the next steps.
    return Turn(ChatResponse(messages=[BotMessage(text=NO_ANSWER)]), "lead", {})
