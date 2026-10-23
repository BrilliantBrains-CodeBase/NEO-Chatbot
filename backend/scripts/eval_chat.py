"""Typed-message test set: how the bot answers realistic patient messages, scored against what it should do.
Uses the real clinic content and APPROVED knowledge base (read only; nothing is saved).

    uv run python -m scripts.eval_chat            # failures only
    uv run python -m scripts.eval_chat --all      # every message
"""

import asyncio
import sys

import asyncpg

from app.chat import embed, engine, service
from app.chat.schemas import ChatRequest
from app.core.config import get_settings

# (message, expected layer, a word the reply must contain; "" = any)
# layers: emergency, medical, rule, kb, lead, menu, start (a flow begins)
CASES: list[tuple[str, str, str]] = [
    # greetings and small talk
    ("hi", "menu", ""), ("Hello", "menu", ""), ("good morning", "menu", ""), ("hii there", "menu", ""),
    ("thanks", "menu", ""), ("thank you so much", "menu", ""), ("ok", "menu", ""), ("bye", "menu", ""),
    ("who are you?", "rule", "Arya"), ("are you a real person", "rule", "Arya"),
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
    # unknown: a lead, never a guess
    ("do you have parking", "lead", ""), ("do you treat acne", "lead", ""), ("what's the weather", "lead", ""),
    ("can i bring my dog", "lead", ""),
]  # fmt: skip


def req(text: str) -> ChatRequest:
    return ChatRequest.model_validate(
        {"client_id": "CL01", "session_id": "s_" + "0" * 32, "visitor_id": "v_" + "0" * 32, "event": "text",
         "payload": {"text": text}, "context": {"page_url": "https://example.com", "device": "desktop", "lang": "en"}}
    )  # fmt: skip


async def main(show_all: bool) -> None:
    await embed.warm()
    conn = await asyncpg.connect(get_settings().database_url, statement_cache_size=0)
    passed = 0
    try:
        for text, want, word in CASES:
            r = req(text)
            steps: list[service.Step] = []
            hit = await service._kb(conn, r, steps)
            turn = engine.respond(r, {}, None, hit.answer if hit else None)
            first = steps[0]["step"] if steps else ""
            layer = first if first in ("emergency", "medical") else turn.answered_by
            if turn.state.get("flow") and layer == "flow":
                layer = "lead" if turn.state["flow"].get("kind") == "question" else "start"
            reply = " | ".join(m.text for m in turn.reply.messages)
            ok = (want == "any" and layer not in ("lead", "medical", "emergency") or layer == want) and (
                word.lower() in reply.lower()
            )
            passed += ok
            if show_all or not ok:
                print(f"{'PASS' if ok else 'FAIL'}  {text!r:46} want {want:9} got {layer:9} {reply[:70]!r}")
    finally:
        await conn.close()
    print(f"\n{passed}/{len(CASES)} passed")


if __name__ == "__main__":
    asyncio.run(main("--all" in sys.argv))
