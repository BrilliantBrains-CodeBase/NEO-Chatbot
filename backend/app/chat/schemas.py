"""The widget and backend JSON contract (README "Widget and backend contract",
frontend/widgets/core/types.ts).

Every field is checked here, so nothing unexpected reaches the flows or the database.
"""

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
)

from app.core.codes import CLINIC_CODE, current

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
    client_id: str = Field(pattern=CLINIC_CODE)
    session_id: str = Field(pattern=rf"^s_{ID_HEX}$")
    visitor_id: str = Field(pattern=rf"^v_{ID_HEX}$")
    event: Literal["start", "text", "button", "restart"]
    payload: Payload = Field(default_factory=Payload)
    context: Context

    @field_validator("client_id")
    @classmethod
    def _renamed(cls, v: str) -> str:
        return current(v)  # a cached widget file may still send a clinic's old code (CL01)


class Media(BaseModel):
    kind: Literal["image", "video", "file", "map"]
    url: str = Field(pattern=r"^https://\S+$")


class BotMessage(BaseModel):
    type: Literal["text"] = "text"
    text: str
    media: Media | None = None  # a canvas Media block: the widget shows it here, the text as its caption
    typing: float = Field(default=0, ge=0, le=5)  # seconds of typing dots before it (the block's setting)

    @model_serializer(mode="wrap")
    def _extras_only_when_set(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        out: dict[str, Any] = handler(self)
        if out.get("media") is None:
            out.pop("media", None)  # a plain text message stays {"type": "text", "text": ...}
        if not out.get("typing"):
            out.pop("typing", None)
        return out


class Input(BaseModel):
    mode: Literal["text", "phone", "email"] = "text"
    placeholder: str = "Type your question"


class ChatResponse(BaseModel):
    messages: list[BotMessage]
    # The block shapes (menu, chips, calendar, ...) are checked by the flows that build them.
    ui: dict[str, Any] | None = None
    input: Input = Field(default_factory=Input)
