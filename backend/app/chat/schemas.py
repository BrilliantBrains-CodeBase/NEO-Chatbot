"""The widget and backend JSON contract (README "Widget and backend contract",
frontend/widgets/core/types.ts).

Every field is checked here, so nothing unexpected reaches the flows or the database.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ID_HEX = r"[0-9a-f]{32}"


class Strict(BaseModel):
    # Unknown fields are refused instead of silently ignored.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Payload(Strict):
    action: str | None = Field(default=None, max_length=50, pattern=r"^[a-z_]{1,50}$")
    value: str | None = Field(default=None, max_length=200)
    text: str | None = Field(default=None, max_length=500)
    cc: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{0,3}$")


class Context(Strict):
    page_url: str = Field(max_length=2000)
    device: Literal["mobile", "desktop"]
    lang: Literal["en"]


class ChatRequest(Strict):
    client_id: str = Field(pattern=r"^CL[0-9]{2,3}$")
    session_id: str = Field(pattern=rf"^s_{ID_HEX}$")
    visitor_id: str = Field(pattern=rf"^v_{ID_HEX}$")
    event: Literal["start", "text", "button", "restart"]
    payload: Payload = Field(default_factory=Payload)
    context: Context


class BotMessage(BaseModel):
    type: Literal["text"] = "text"
    text: str


class Input(BaseModel):
    mode: Literal["text", "phone", "email"] = "text"
    placeholder: str = "Type your question"


class ChatResponse(BaseModel):
    messages: list[BotMessage]
    # The block shapes (menu, chips, calendar, ...) are checked by the flows that build them.
    ui: dict[str, Any] | None = None
    input: Input = Field(default_factory=Input)
