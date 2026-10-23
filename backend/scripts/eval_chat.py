"""Typed-message test set: how the bot answers realistic patient messages, scored against what it should do.
Uses the real clinic content and APPROVED knowledge base (read only; nothing is saved).

    uv run python -m scripts.eval_chat            # failures only
    uv run python -m scripts.eval_chat --all      # every message and conversation
"""

import asyncio
import sys
from typing import Any

import asyncpg

from app.chat import context, embed, engine, service, store
from app.chat.content import content
from app.chat.schemas import ChatRequest
from app.core.config import get_settings

# (message, expected layer, a word the reply must contain; "" = any)
# layers: emergency, medical, rule, kb, lead, menu, start (a flow begins)
CASES: list[tuple[str, str, str]] = [
    # greetings and small talk
    ("hi", "menu", ""), ("Hello", "menu", ""), ("good morning", "menu", ""), ("hii there", "menu", ""),
    ("thanks", "menu", ""), ("thank you so much", "menu", ""), ("ok", "menu", ""), ("bye", "menu", ""),
    ("who are you?", "rule", "Arya"), ("are you a real person", "rule", "Arya"), ("human or ai", "rule", "Arya"),
    ("is this a bot", "rule", "Arya"), ("am i chatting with a real person", "rule", "Arya"),
    # timings
    ("what are your timings", "any", "7"), ("working hours?", "any", "7"), ("are you open on sunday", "any", "Sunday"),
    ("is the clinic open on tuesday", "any", "Tuesday"), ("clinic kab khulta hai", "any", "7"),
    ("what time do you close", "any", "7"),
    # location
    ("where is the clinic", "any", "Marathahalli"), ("address pls", "any", "Marathahalli"),
    ("how do i reach you", "any", "Marathahalli"), ("clinic kahan hai", "any", "Marathahalli"),
    ("google maps link", "any", "maps"), ("adress", "any", "Marathahalli"),
    # cost
    ("how much does hair transplant cost", "any", "graft"), ("price?", "any", "graft"),
    ("hair transplant ka kitna kharcha hai", "any", "graft"), ("cost per graft", "any", "60"),
    ("is there emi", "any", "EMI"), ("can i pay in installments", "any", "EMI"), ("prp cost", "any", "consultation"),
    # doctor
    ("who is the doctor", "any", "Sandeep"), ("tell me about dr sandeep", "any", "Sandeep"),
    ("is the doctor experienced", "any", "20+"), ("doctor qualification", "any", "MD"),
    # treatments
    ("what is prp", "any", "PRP"), ("tell me about gfc", "any", "GFC"), ("what is qr678", "any", "QR678"),
    ("do you do beard transplant", "any", "beard"), ("eyebrow transplant", "any", "yebrow"),
    ("can women get hair transplant", "any", "emale"), ("transplant without shaving", "any", "nshaven"),
    ("my previous transplant failed can you fix it", "any", "epair"), ("what treatments do you offer", "any", ""),
    ("how long does surgery take", "any", "hours"), ("when can i go back to office", "any", "days"),
    # international and photos
    ("i live in dubai", "any", ""), ("do you help with visa", "any", "visa"), ("how many days stay in bangalore", "any", "3 to 5"),
    ("can i send photos", "any", "WhatsApp"),
    # booking flows
    ("i want to book an appointment", "any", ""), ("book consultation", "any", ""), ("online consultation", "start", ""),
    ("i want to cancel my appointment", "start", ""), ("reschedule my appointment", "start", ""),
    ("call me back", "any", ""), ("talk to someone", "any", ""),
    # medical: never answered
    ("is it painful", "medical", ""), ("can i take minoxidil", "medical", ""), ("side effects of prp", "medical", ""),
    ("am i suitable for transplant", "medical", ""), ("i have thyroid will it affect", "medical", ""),
    # emergency
    ("bleeding after surgery", "emergency", ""), ("severe swelling after transplant", "emergency", ""),
    # facts (layer 1)
    ("clinic name", "kb", "Neo Follicle"), ("what is the name of your clinic", "kb", "Neo Follicle"),
    ("what is your email", "kb", "info@"), ("mail id", "kb", "info@"), ("which languages do you speak", "kb", "Kannada"),
    ("what facilities do you have", "kb", "lounge"), ("website link", "kb", "neofollicle"),
    ("do you have a brochure", "kb", ""), ("what techniques do you use", "kb", ""),
    ("what is included in the consultation", "kb", ""), ("which areas do you serve", "kb", ""),
    # unknown: a lead, never a guess
    ("do you have parking", "lead", ""), ("do you treat acne", "lead", ""), ("what's the weather", "lead", ""),
    ("can i bring my dog", "lead", ""),
]  # fmt: skip


# Conversations (C1): each message is read with the chat before it. "tap action value" is a button.
# ("recovery?" is not in the approved KB yet, so the call back is right.)
CONVERSATIONS: list[list[tuple[str, str, str]]] = [
    [("which treatments are there", "rule", ""), ("I want more", "rule", "Which one")],
    [("hi", "menu", ""), ("tell me more", "rule", "Which one")],
    [("tell me about beard transplant", "any", "eard"), ("tell me more", "rule", "Beard Transplant")],
    [("tap treat PRP Treatment", "any", "PRP"), ("how much does it cost", "any", ""), ("and for gfc?", "any", "")],
    [("how much does hair transplant cost", "any", "graft"), ("is there emi", "any", "EMI")],
    [("what is prp", "any", "PRP"), ("how long does it take", "any", "")],
    [("tap treat Hair Transplant for Men", "any", ""), ("how long does the procedure take", "any", "hours"),
     ("recovery?", "lead", "call you back")],
    [("what is qr678", "any", "QR678"), ("where is the clinic", "any", "Marathahalli"),
     ("what time do you close", "any", "7")],
    [("do you have parking", "lead", "call you back"), ("yes", "lead", "full name")],
    [("do you treat acne", "lead", ""), ("no", "menu", "")],
]  # fmt: skip


def req(text: str) -> ChatRequest:
    event, payload = "text", {"text": text}
    if text.startswith("tap "):
        _, action, value = text.split(" ", 2)
        event, payload = "button", {"action": action, "value": value}
    return ChatRequest.model_validate(
        {"client_id": "CL01", "session_id": "s_" + "0" * 32, "visitor_id": "v_" + "0" * 32, "event": event,
         "payload": payload, "context": {"page_url": "https://example.com", "device": "desktop", "lang": "en"}}
    )  # fmt: skip


async def turn_of(
    conn: asyncpg.Connection, text: str, state: dict[str, Any]
) -> tuple[str, str, dict[str, Any]]:
    """One message as the service runs it (nothing saved): (layer, reply, new state)."""
    c = content("CL01")
    assert c is not None
    r = req(text)
    said = store.patient_text(r, state)
    r = context.as_text(r)
    question = engine.asked(r, state)
    steps: list[service.Step] = []
    hit = await service._kb(conn, r, steps, question)
    turn = engine.respond(r, state, None, hit.answer if hit else None)
    first = steps[0]["step"] if steps else ""
    layer = first if first in ("emergency", "medical") else turn.answered_by
    if turn.state.get("flow") and layer == "flow":
        layer = "lead" if turn.state["flow"].get("kind") == "question" else "start"
    turn.state["last_shown"] = turn.state["shown"] = engine.shown_choices(turn.reply.ui)
    bot = [m.text for m in turn.reply.messages]
    context.remember(state, turn.state, r, said, bot, turn.reply.ui, turn.answered_by, question, c)
    return layer, " | ".join(bot), turn.state


def ok_for(want: str, word: str, layer: str, reply: str) -> bool:
    return (want == "any" and layer not in ("lead", "medical", "emergency") or layer == want) and (
        word.lower() in reply.lower()
    )


def line(ok: bool, text: str, want: str, layer: str, reply: str) -> str:
    return f"{'PASS' if ok else 'FAIL'}  {text!r:46} want {want:9} got {layer:9} {reply[:70]!r}"


async def main(show_all: bool) -> None:
    await embed.warm()
    conn = await asyncpg.connect(get_settings().database_url, statement_cache_size=0)
    passed = talks = 0
    try:
        for text, want, word in CASES:
            layer, reply, _ = await turn_of(conn, text, {})
            ok = ok_for(want, word, layer, reply)
            passed += ok
            if show_all or not ok:
                print(line(ok, text, want, layer, reply))
        for talk in CONVERSATIONS:
            state: dict[str, Any] = {}
            lines, all_ok = [], True
            for text, want, word in talk:
                layer, reply, state = await turn_of(conn, text, state)
                ok = ok_for(want, word, layer, reply)
                all_ok = all_ok and ok
                lines.append("    " + line(ok, text, want, layer, reply))
            talks += all_ok
            if show_all or not all_ok:
                print(f"{'PASS' if all_ok else 'FAIL'}  conversation")
                print("\n".join(lines))
    finally:
        await conn.close()
    print(f"\n{passed}/{len(CASES)} messages, {talks}/{len(CONVERSATIONS)} conversations passed")


if __name__ == "__main__":
    asyncio.run(main("--all" in sys.argv))
