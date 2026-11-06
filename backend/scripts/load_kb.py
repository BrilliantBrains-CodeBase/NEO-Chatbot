"""Loads a clinic's knowledge base file (app/clinics/<CLxx>.kb.json) into app.kb_facts and app.kb_qa
as DRAFTS. Approved or retired rows are never changed. Safe to run again.

    uv run python -m scripts.load_kb NFHT            # shows what would change
    uv run python -m scripts.load_kb NFHT --apply    # saves it
"""

import asyncio
import json
import sys
from pathlib import Path

import asyncpg

from app.core.config import get_settings

ROOT = Path(__file__).resolve().parent.parent / "app" / "clinics"


async def main(clinic: str, apply: bool) -> None:
    data = json.loads((ROOT / f"{clinic}.kb.json").read_text(encoding="utf-8"))
    conn = await asyncpg.connect(get_settings().database_url, statement_cache_size=0)
    try:
        async with conn.transaction():
            facts = qa = kept = 0
            for f in data["facts"]:
                status = await conn.fetchval(
                    "select status from app.kb_facts where clinic_id = $1 and key = $2", clinic, f["key"]
                )
                if status in ("approved", "retired"):
                    kept += 1
                    continue
                await conn.execute(
                    """insert into app.kb_facts (clinic_id, key, category, value) values ($1, $2, $3, $4)
                       on conflict (clinic_id, key) do update set category = excluded.category,
                         value = excluded.value""",
                    clinic, f["key"], f["category"], f["value"],
                )  # fmt: skip
                facts += 1
            for q in data["qa"]:
                status = await conn.fetchval(
                    "select status from app.kb_qa where clinic_id = $1 and question = $2", clinic, q["q"]
                )
                if status in ("approved", "retired"):
                    kept += 1
                    continue
                await conn.execute(
                    "delete from app.kb_qa where clinic_id = $1 and question = $2 and status = 'draft'",
                    clinic, q["q"],
                )  # fmt: skip
                await conn.execute(
                    """insert into app.kb_qa (clinic_id, question, variants, answer, category, treatment)
                       values ($1, $2, $3, $4, $5, $6)""",
                    clinic, q["q"], q["v"], q["a"], q["cat"], q["t"],
                )  # fmt: skip
                qa += 1
            print(f"{clinic}: {facts} facts and {qa} Q/A as draft; {kept} approved/retired rows kept")
            if not apply:
                raise _DryRun
    except _DryRun:
        print("Nothing changed. Run with --apply to save.")
    finally:
        await conn.close()


class _DryRun(Exception):
    pass


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--apply"]
    if len(args) != 1 or not (ROOT / f"{args[0]}.kb.json").exists():
        sys.exit("usage: python -m scripts.load_kb NFHT [--apply]")
    asyncio.run(main(args[0], "--apply" in sys.argv))
