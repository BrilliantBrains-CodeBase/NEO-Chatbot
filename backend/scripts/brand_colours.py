"""Each clinic's chatbot in its own website's colours (read from the sites' stylesheets on 6 Nov 2026).

    uv run python -m scripts.brand_colours            # show the changes, save nothing
    uv run python -m scripts.brand_colours --apply    # save them (published as a new version)

Sets Appearance → Colours (and the launcher's background) in the draft and the published settings. The Neo
Group's other clinics stop following the main template's Appearance, so their own colours stay; they keep
following its Templates. Every palette keeps text readable: white on the main colour and text on the surface
are at least 4.5 : 1 (WCAG AA).
"""

import asyncio
import json
import sys
from typing import Any

import asyncpg

from app.core.config import get_settings

# The sites' own colours: neofollicletransplant.com (--color-primary #3C72D7, -dark #1A4FB2, -accent #E2ECFF,
# -surface #F8FAFC); dermasolutions.co.in (--color-primary #481E0B, -accent #8B5E45, -accent-light #C9A58C,
# -secondary #F7F2EE, -body #69615D); neofertility.co.in (pink-600 primary, plum-900 ink, pink-50, gold-400,
# from OKLCH); neosculpt6.com (accent #C92A45, primary #D98391, secondary #FAF3EC, tertiary #E4C98A,
# background #221A19, text #D9C5BE, border #38292E).
PALETTES: dict[str, dict[str, Any]] = {
    "NFHT": {"main": "#3C72D7", "main_dark": "#1A4FB2", "accent": "#94B1E9", "tint": "#E2ECFF",
             "surface": "#F8FAFC", "line": "#E5E7EB", "text": "#1A1A1A", "muted": "#444444",
             "highlight": "#FFCC70"},
    "DS": {"main": "#481E0B", "main_dark": "#2B1207", "accent": "#C9A58C", "tint": "#F1ECE9",
           "surface": "#F7F2EE", "line": "#EAE2DE", "text": "#2B1207", "muted": "#69615D",
           "highlight": "#C9A58C"},
    "NF": {"main": "#CE3A92", "main_dark": "#BF2A85", "accent": "#E89DC2", "tint": "#FFE7F2",
           "surface": "#FAF7F8", "line": "#EAE2E5", "text": "#3D203F", "muted": "#666666",
           "highlight": "#FFCE3E"},
    "NS6": {"main": "#C92A45", "main_dark": "#8D1D30", "accent": "#D98391", "tint": "#F9ECEE",
            "surface": "#FAF3EC", "line": "#E8DCD8", "text": "#221A19", "muted": "#6B5A55",
            "highlight": "#E4C98A",
            # The site itself is dark: its own colours for visitors whose device is in dark mode.
            "dark_page": "#221A19", "dark_card": "#0B0B0D", "dark_text": "#D9C5BE", "dark_line": "#38292E"},
}  # fmt: skip
OWN_LOOK = {"DS", "NF", "NS6"}  # stop following the main's Appearance (Templates still followed)


def obj(raw: Any) -> Any:
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def recolour(settings: dict[str, Any], palette: dict[str, Any]) -> list[str]:
    """Sets the palette; returns what changed ("main #3E74D9 -> #3C72D7")."""
    look = settings.setdefault("appearance", {})
    colours = look.setdefault("colours", {})
    launcher = look.setdefault("launcher", {})
    changes = [f"{k} {colours.get(k)} -> {v}" for k, v in palette.items() if colours.get(k) != v]
    colours.update(palette)
    if launcher.get("background") != palette["main"]:
        changes.append(f"launcher {launcher.get('background')} -> {palette['main']}")
        launcher["background"] = palette["main"]
    return changes


async def main(apply: bool) -> None:
    conn = await asyncpg.connect(get_settings().database_url, statement_cache_size=0, timeout=30)
    try:
        async with conn.transaction():
            for code, palette in PALETTES.items():
                row = await conn.fetchrow(
                    "select draft, published, shared, follows, version from app.clinic_settings "
                    "where clinic_id = $1 for update",
                    code,
                )
                if row is None:
                    print(f"{code}: no chatbot settings, skipped")
                    continue
                draft, published, shared = obj(row["draft"]), obj(row["published"]), obj(row["shared"])
                changes = recolour(published, palette)
                recolour(draft, palette)
                if shared.get("appearance"):  # the main's for-all version
                    recolour(shared, palette)
                follows = [p for p in row["follows"] if not (code in OWN_LOOK and p == "appearance")]
                if follows != list(row["follows"]):
                    changes.append(f"follows {list(row['follows'])} -> {follows}")
                print(f"{code}: {len(changes)} changes")
                for c in changes:
                    print("   ", c)
                if apply and changes:
                    version = row["version"] + 1
                    await conn.execute(
                        """update app.clinic_settings set draft = $2::jsonb, published = $3::jsonb,
                             shared = $4::jsonb, follows = $5, version = $6, published_at = now(),
                             updated_at = now() where clinic_id = $1""",
                        code, json.dumps(draft), json.dumps(published),
                        json.dumps(shared) if row["shared"] is not None else None, follows, version,
                    )  # fmt: skip
                    await conn.execute(
                        """insert into app.clinic_setting_versions (clinic_id, version, settings,
                             published_at)
                           values ($1, $2, $3::jsonb, now())""",
                        code, version, json.dumps(published),
                    )  # fmt: skip
    finally:
        await conn.close()
    print("Saved." if apply else "Nothing changed. Run with --apply to save.")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
