"""POST /v1/chat/message: every widget action arrives here as JSON and gets the reply as JSON."""

from fastapi import APIRouter, HTTPException, Request, status

from app.chat import guard
from app.chat.schemas import BotMessage, ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat/message", response_model=ChatResponse)
async def message(req: ChatRequest, request: Request) -> ChatResponse:
    # Rate limit first: it costs nothing, so floods never reach the database.
    ip = guard.client_ip(request.headers, request.client.host if request.client else None)
    if not guard.limiter.allow("ip:" + ip, guard.IP_PER_MIN) or not guard.limiter.allow(
        "v:" + req.visitor_id, guard.VISITOR_PER_MIN
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many messages, please wait a minute")
    clinic = await guard.get_clinic(req.client_id)
    if clinic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown clinic")
    if not guard.origin_allowed(clinic, request.headers.get("origin")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This website may not use this chat")

    # B1: a greeting only. Sessions, flows and leads come in the next steps.
    name = clinic.bot_name.removesuffix(" AI")
    return ChatResponse(messages=[BotMessage(text=f"Hi, I'm {name}. How can I help you today?")])
