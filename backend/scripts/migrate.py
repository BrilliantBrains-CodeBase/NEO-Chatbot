"""Apply database migrations in order, each exactly once, each inside one transaction.

Usage (from backend/):
    uv run python -m scripts.migrate            # show what would be applied, change nothing
    uv run python -m scripts.migrate --apply    # apply pending migrations

Migrations are the numbered files in supabase/migrations. Applied ones are recorded in
app.schema_migrations together with a checksum, so an applied file that was edited afterwards is
refused instead of silently ignored (fixes go in a new numbered file).
"""

import asyncio
import hashlib
import re
import sys
from pathlib import Path

import asyncpg

from app.core.config import get_settings

MIGRATIONS = Path(__file__).resolve().parent.parent / "supabase" / "migrations"
NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

BOOTSTRAP = """
create schema if not exists app;
create table if not exists app.schema_migrations (
  version    text primary key,
  checksum   text not null,
  applied_at timestamptz not null default now()
);
"""


def files() -> list[Path]:
    found = sorted(MIGRATIONS.glob("*.sql"))
    bad = [p.name for p in found if not NAME.match(p.name)]
    if bad:
        raise SystemExit(f"Bad migration file names (want 0001_name.sql): {bad}")
    return found


def checksum(path: Path) -> str:
    # Line endings normalised: Git gives Windows CRLF and Linux LF, and both must match.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


async def main(apply: bool) -> None:
    url = get_settings().database_url
    if not url:
        raise SystemExit("DATABASE_URL is not set (backend/.env)")
    conn = await asyncpg.connect(url, statement_cache_size=0, timeout=15)
    try:
        if apply:
            await conn.execute(BOOTSTRAP)
        exists = await conn.fetchval("select to_regclass('app.schema_migrations') is not null")
        rows = await conn.fetch("select version, checksum from app.schema_migrations") if exists else []
        done = {r["version"]: r["checksum"] for r in rows}

        pending = []
        for path in files():
            version = path.name
            if version in done:
                if done[version] != checksum(path):
                    raise SystemExit(f"{version} was changed after it was applied. Put fixes in a new file.")
                continue
            pending.append(path)

        if not pending:
            print("Database is up to date.")
            return
        for path in pending:
            if not apply:
                print(f"would apply {path.name}")
                continue
            async with conn.transaction():
                await conn.execute(path.read_text(encoding="utf-8"))
                await conn.execute(
                    "insert into app.schema_migrations (version, checksum) values ($1, $2)",
                    path.name,
                    checksum(path),
                )
            print(f"applied {path.name}")
        if not apply:
            print("Nothing changed. Run with --apply to apply.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
