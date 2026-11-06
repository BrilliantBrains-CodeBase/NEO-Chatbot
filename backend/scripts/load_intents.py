"""T4: saves a clinic's REVIEWED example phrases and fact wordings (app/clinics/<CLxx>.intents.json) as
APPROVED, so the bot uses them. Run it only after the person responsible has approved the file. Safe to run
again: phrases already there are kept, Q/A and fact wordings are added to what staff have (never removed).

    uv run python -m scripts.load_intents NFHT            # shows what would change
    uv run python -m scripts.load_intents NFHT --apply    # saves it
"""

import asyncio
import json
import sys
from pathlib import Path

import asyncpg

from app.chat.intents import norm
from app.core.config import get_settings

ROOT = Path(__file__).resolve().parent.parent / "app" / "clinics"


class _DryRun(Exception):
    pass


async def save(conn: asyncpg.Connection, clinic: str) -> None:
    """Writes the phrases and wordings on this connection; the caller owns the transaction."""
    data = json.loads((ROOT / f"{clinic}.intents.json").read_text(encoding="utf-8"))
    # New reviewed facts (e.g. Google reviews): added as approved; a fact already there is never changed.
    for key, fact in data.get("new_facts", {}).items():
        if await conn.fetchval("select 1 from app.kb_facts where clinic_id = $1 and key = $2", clinic, key):
            continue
        await conn.execute(
            """insert into app.kb_facts (clinic_id, key, category, value, status, approved_at)
               values ($1, $2, $3, $4, 'approved', now())""",
            clinic, key, fact["category"], fact["value"],
        )  # fmt: skip
        print(f"  new fact {key}: {fact['value'][:80]}...")
    have = {
        norm(r["example"]): r["intent"]
        for r in await conn.fetch(
            "select intent, example from app.intent_examples where clinic_id = $1 and status <> 'retired'",
            clinic,
        )
    }
    added = kept = 0
    for intent, phrases in data["intents"].items():
        for phrase in phrases:
            key = norm(phrase)
            if key in have:
                if have[key] != intent:
                    raise SystemExit(f"{phrase!r} is already for {have[key]!r}, not {intent!r}")
                kept += 1
                continue
            await conn.execute(
                """insert into app.intent_examples (clinic_id, intent, example, status, approved_at)
                   values ($1, $2, $3, 'approved', now())""",
                clinic, intent, key,
            )  # fmt: skip
            have[key] = intent
            added += 1
    print(f"{clinic}: {added} phrases approved, {kept} already there")
    for question, more in data.get("qa_variants", {}).items():
        row = await conn.fetchrow(
            "select variants from app.kb_qa where clinic_id = $1 and question = $2 and status = 'approved'",
            clinic, question,
        )  # fmt: skip
        if row is None:
            raise SystemExit(f"no approved question {question!r} in {clinic}")
        old = [v for v in row["variants"].splitlines() if v.strip()]
        new = [v for v in more if norm(v) not in {norm(o) for o in old}]
        if new:  # its meaning is worked out again by the backend (0016 clears it on change)
            await conn.execute(
                "update app.kb_qa set variants = $3 where clinic_id = $1 and question = $2",
                clinic, question, "\n".join([*old, *new]),
            )  # fmt: skip
            print(f"  Q/A {question!r}: + {', '.join(new)}")
    for key, more in data["fact_variants"].items():
        row = await conn.fetchrow(
            "select variants from app.kb_facts where clinic_id = $1 and key = $2 and status = 'approved'",
            clinic, key,
        )  # fmt: skip
        if row is None:
            raise SystemExit(f"no approved fact {key!r} in {clinic}")
        old = [v for v in row["variants"].splitlines() if v.strip()]
        new = [v for v in more if norm(v) not in {norm(o) for o in old}]
        if new:
            await conn.execute(
                "update app.kb_facts set variants = $3 where clinic_id = $1 and key = $2",
                clinic, key, "\n".join([*old, *new]),
            )  # fmt: skip
            print(f"  fact {key}: + {', '.join(new)}")


async def main(clinic: str, apply: bool) -> None:
    conn = await asyncpg.connect(get_settings().database_url, statement_cache_size=0)
    try:
        async with conn.transaction():
            await save(conn, clinic)
            if not apply:
                raise _DryRun
    except _DryRun:
        print("Nothing changed. Run with --apply to save.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], "--apply" in sys.argv))
