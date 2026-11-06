"""Neo Follicle's chatbot wording after the rename to Neo Follicle Hair Transplant (migration 0040).

    uv run python -m scripts.nfht_wording            # show every change, save nothing
    uv run python -m scripts.nfht_wording --apply    # save them

"Neo Follicle" in the clinic's own words becomes "Neo Follicle Hair Transplant": the chatbot settings (draft,
published and the version shared with other clinics; the published one is saved as a new version), the
knowledge facts' and Q/A answers, the doctors' titles and profiles, and the repo's app/clinics/NFHT*.json.
Left as they are: patients' review quotes (their own words), web addresses, the facts' other wordings (what
patients may type), "Neofollicle and Neofertility Clinic LLP" and anything already saying the full name.
"""

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

import asyncpg

from app.core.config import get_settings

CLINIC = "NFHT"
NEW = "Neo Follicle Hair Transplant"
# "Neo Follicle" / "NEO Follicle" as words, not already the full name (nor the Google listing's "Neo Follicle
# Transplant Clinic").
OLD = re.compile(r"\bneo follicle\b(?!\s+(hair\s+)?transplant)", re.IGNORECASE)
SKIP = re.compile(r"\.reviews\.quotes\b")  # patients' own words
HERE = Path(__file__).resolve().parent.parent / "app" / "clinics"
FILES = [HERE / f"{CLINIC}{s}" for s in (".json", ".kb.json")]


def fix(text: str) -> str:
    return text if text.startswith(("http://", "https://")) else OLD.sub(NEW, text)


def walk(v: Any, path: str, changes: list[tuple[str, str, str]]) -> Any:
    if isinstance(v, dict):
        return {k: walk(x, f"{path}.{k}", changes) for k, x in v.items()}
    if isinstance(v, list):
        return [walk(x, f"{path}[{i}]", changes) for i, x in enumerate(v)]
    if isinstance(v, str) and not SKIP.search(path):
        new = fix(v)
        if new != v:
            changes.append((path, v, new))
        return new
    return v


def obj(raw: Any) -> Any:
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def show(changes: list[tuple[str, str, str]]) -> None:
    for path, old, new in changes:
        print(f"  {path}\n    - {old[:150]!r}\n    + {new[:150]!r}")


async def main(apply: bool) -> None:
    total = 0
    conn = await asyncpg.connect(get_settings().database_url, statement_cache_size=0, timeout=15)
    try:
        async with conn.transaction():
            if not await conn.fetchval("select 1 from app.clinics where id = $1", CLINIC):
                raise SystemExit(f"{CLINIC} not found: apply migration 0040 first.")
            s = await conn.fetchrow(
                """select draft, published, shared, version from app.clinic_settings
                   where clinic_id = $1 for update""",
                CLINIC,
            )
            fixed: dict[str, Any] = {}
            for col in ("draft", "published", "shared"):
                changes: list[tuple[str, str, str]] = []
                fixed[col] = walk(obj(s[col]), "", changes) if s[col] is not None else None
                print(f"== chatbot settings, {col}: {len(changes)}")
                show(changes)
                total += len(changes)
            facts = []
            for r in await conn.fetch(
                "select id, key, value from app.kb_facts where clinic_id = $1 order by key", CLINIC
            ):
                if r["value"] and fix(r["value"]) != r["value"]:
                    facts.append((r["id"], fix(r["value"])))
                    print(f"== fact {r['key']}\n    - {r['value'][:150]!r}\n    + {fix(r['value'])[:150]!r}")
            total += len(facts)
            answers = []
            for r in await conn.fetch(
                "select id, question, answer from app.kb_qa where clinic_id = $1 order by question", CLINIC
            ):
                if r["answer"] and fix(r["answer"]) != r["answer"]:
                    answers.append((r["id"], fix(r["answer"])))
                    print(f"== Q/A {r['question'][:80]!r}")
                    print(f"    - {r['answer'][:150]!r}\n    + {fix(r['answer'])[:150]!r}")
            total += len(answers)
            doctors = []
            for r in await conn.fetch(
                "select id, name, role_title, profile from app.doctors where clinic_id = $1", CLINIC
            ):
                changes = []
                title = walk(r["role_title"], ".role_title", changes) if r["role_title"] else r["role_title"]
                profile = walk(obj(r["profile"]), ".profile", changes)
                if changes:
                    print(f"== doctor {r['name']}")
                    show(changes)
                    doctors.append((r["id"], title, profile))
                    total += len(changes)
            if apply and total:
                version = s["version"] + 1
                await conn.execute(
                    """update app.clinic_settings set draft = $2::jsonb, published = $3::jsonb,
                         shared = $4::jsonb, version = $5, published_at = now(), updated_at = now()
                       where clinic_id = $1""",
                    CLINIC, json.dumps(fixed["draft"]), json.dumps(fixed["published"]),
                    json.dumps(fixed["shared"]) if fixed["shared"] is not None else None, version,
                )  # fmt: skip
                await conn.execute(
                    """insert into app.clinic_setting_versions (clinic_id, version, settings, published_at)
                       values ($1, $2, $3::jsonb, now())""",
                    CLINIC, version, json.dumps(fixed["published"]),
                )  # fmt: skip
                for fid, value in facts:
                    await conn.execute(
                        "update app.kb_facts set value = $2, updated_at = now() where id = $1", fid, value
                    )
                for qid, answer in answers:  # its meaning vector is of the question: unchanged
                    await conn.execute(
                        "update app.kb_qa set answer = $2, updated_at = now() where id = $1", qid, answer
                    )
                for did, title, profile in doctors:
                    await conn.execute(
                        "update app.doctors set role_title = $2, profile = $3::jsonb, updated_at = now() "
                        "where id = $1",
                        did, title, json.dumps(profile),
                    )  # fmt: skip
            others = await conn.fetch(
                """select clinic_id from app.clinic_settings where clinic_id <> $1
                     and (draft::text ~* 'neo follicle' or published::text ~* 'neo follicle')""",
                CLINIC,
            )
            if others:
                print("Note: other clinics' own chatbot text also says Neo Follicle (left as is):",
                      ", ".join(r[0] for r in others))  # fmt: skip
    finally:
        await conn.close()

    for f in FILES:  # the repo's copy of the content, line by line so its layout stays as it is
        lines = f.read_text(encoding="utf-8").split("\n")
        out = [line if '"topic":' in line else OLD.sub(NEW, line) for line in lines]  # review quotes: as is
        pairs = enumerate(zip(lines, out, strict=True))
        changes = [(f"line {i + 1}", a.strip(), b.strip()) for i, (a, b) in pairs if a != b]
        print(f"== {f.name}: {len(changes)}")
        show(changes)
        total += len(changes)
        if apply and changes:
            json.loads("\n".join(out))  # still valid JSON
            f.write_text("\n".join(out), encoding="utf-8")
    print(f"{total} changes {'saved' if apply else 'found. Nothing changed. Run with --apply to save them.'}")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
