"""The main template: NFHT's canvas, Templates and Appearance. A clinic that follows a part
shows the main's for-all version of it (``shared``, set when NFHT publishes for all) instead of its own, with
the main's clinic name, bot name, website, phone and WhatsApp swapped for its own. The Appearance's bot name,
avatar letter, logo, location and on/off switch always stay the clinic's own. Changing a part makes it the
clinic's own.
"""

import json
import re
from typing import Any

import asyncpg

MAIN = "NFHT"
PARTS = ("flow", "template", "appearance")
OWN_LOOK = ("name", "avatar_letter", "logo", "location", "enabled")  # always the clinic's own


def _obj(v: Any) -> dict[str, Any]:
    v = json.loads(v) if isinstance(v, str) else v
    return dict(v) if isinstance(v, dict) else {}


async def follows(conn: asyncpg.Connection, clinic: str) -> list[str]:
    """The parts this clinic takes from the main template (none for the main itself)."""
    got = await conn.fetchval("select follows from app.clinic_settings where clinic_id = $1", clinic)
    return [] if clinic == MAIN else list(got or [])


async def live_flow(conn: asyncpg.Connection, clinic: str) -> dict[str, Any]:
    """The canvas the chat shows: published (else the draft), or the main's when followed."""
    raw = await conn.fetchval(
        """select coalesce(nullif(published->'flow', 'null'::jsonb), draft->'flow')
           from app.clinic_settings where clinic_id = $1""",
        clinic,
    )
    saved = {"flow": _obj(raw)}
    await apply(conn, clinic, saved)
    return saved["flow"]


async def apply(conn: asyncpg.Connection, clinic: str, *saved: dict[str, Any]) -> list[str]:
    """Puts the main's for-all version of each followed part into these settings (draft and/or published,
    changed in place). Returns the followed parts."""
    if clinic == MAIN:
        return []
    row = await conn.fetchrow(
        """select s.follows, m.shared, c.name, c.bot_name, c.website, c.phone, c.whatsapp,
             mc.name m_name, mc.bot_name m_bot, mc.website m_website, mc.phone m_phone, mc.whatsapp m_whatsapp
           from app.clinics c cross join app.clinics mc
           left join app.clinic_settings s on s.clinic_id = c.id
           left join app.clinic_settings m on m.clinic_id = mc.id
           where c.id = $1 and mc.id = $2""",
        clinic, MAIN,
    )  # fmt: skip
    if row is None or not row["follows"]:
        return []
    shared = _obj(row["shared"])
    parts = [p for p in row["follows"] if shared.get(p)]
    swaps = _swaps(row)
    for s in saved:
        for part in parts:
            main = _swap(json.loads(json.dumps(shared[part])), swaps)
            if part == "appearance":
                own = _obj(s.get("appearance")).get("look") or {"name": row["bot_name"]}
                look = _obj(main.get("look"))
                look.update({k: own[k] for k in OWN_LOOK if k in own})
                main["look"] = look
            s[part] = main
    return list(row["follows"])


def _swaps(row: asyncpg.Record) -> list[tuple[re.Pattern[str], str]]:
    """The main's own words and links, longest first, each to this clinic's own."""
    pairs = [(row["m_name"], row["name"]), (row["m_bot"], row["bot_name"])]
    first = (row["m_bot"] or "").split()[0] if row["m_bot"] else ""
    if len(first) >= 3 and first != row["m_bot"]:  # "Arya" as well as "Arya AI"
        pairs.append((first, row["bot_name"]))
    out = [
        (re.compile(rf"(?<!\w){re.escape(a)}(?!\w)", re.IGNORECASE), b)
        for a, b in pairs
        if a and b and a != b
    ]
    for key in ("website", "phone", "whatsapp"):  # links and numbers: exact
        a, b = row[f"m_{key}"], row[key]
        if a and b and a != b:
            out.append((re.compile(re.escape(a.rstrip("/"))), b.rstrip("/")))
    return out


def _swap(v: Any, swaps: list[tuple[re.Pattern[str], str]]) -> Any:
    if isinstance(v, str):
        for pattern, new in swaps:
            v = pattern.sub(new.replace("\\", "\\\\"), v)
        return v
    if isinstance(v, list):
        return [_swap(x, swaps) for x in v]
    if isinstance(v, dict):
        return {k: _swap(x, swaps) for k, x in v.items()}
    return v


async def make_own(conn: asyncpg.Connection, clinic: str, parts: list[str]) -> None:
    """These parts stop following the main template and become the clinic's own, starting from the main's
    version as patients see it now (also as published, so the live chat changes only at the next publish)."""
    parts = [p for p in parts if p in await follows(conn, clinic)]
    if not parts:
        return
    published = _obj(
        await conn.fetchval("select published from app.clinic_settings where clinic_id = $1", clinic)
    )
    await apply(conn, clinic, published)
    await conn.execute(
        """update app.clinic_settings
              set follows = array(select unnest(follows) except select unnest($2::text[])),
                  published = coalesce(published, '{}'::jsonb) || $3::jsonb
            where clinic_id = $1""",
        clinic, parts, json.dumps({p: published[p] for p in parts if p in published}),
    )  # fmt: skip


async def follow(conn: asyncpg.Connection, clinic: str, parts: list[str]) -> None:
    """These parts follow the main template again (the clinic's own version is kept, unused)."""
    await conn.execute(
        """update app.clinic_settings set follows = array(select distinct unnest(follows || $2::text[]))
            where clinic_id = $1""",
        clinic, parts,
    )  # fmt: skip


async def share(conn: asyncpg.Connection, published: dict[str, Any]) -> None:
    """The main's published canvas, Templates and Appearance become the for-all version."""
    await conn.execute(
        "update app.clinic_settings set shared = $2::jsonb where clinic_id = $1",
        MAIN, json.dumps({p: published[p] for p in PARTS if p in published}),
    )  # fmt: skip
