"""Secrets in Supabase Vault (a clinic's Cal.com key, a sheet's secret ...). Vault encrypts them with a key
Supabase keeps outside the database; our tables keep only the secret's id. Only the backend reads them (the
browser's role has no access to the vault schema)."""

from uuid import UUID, uuid4

import asyncpg


async def save(conn: asyncpg.Connection, value: str, name: str) -> UUID:
    """A new secret; returns its id. The name only helps to find it in Supabase (never the value); Vault wants
    each name once, so it gets a random ending (a key is replaced by saving the new one, then deleting)."""
    unique = f"{name} {uuid4().hex[:8]}"
    found: UUID = await conn.fetchval("select vault.create_secret($1, $2)", value, unique)
    return found


async def read(conn: asyncpg.Connection, secret: UUID | str | None) -> str | None:
    if not secret:
        return None
    value: str | None = await conn.fetchval(
        "select decrypted_secret from vault.decrypted_secrets where id = $1::uuid", str(secret)
    )
    return value


async def delete(conn: asyncpg.Connection, *secrets: UUID | str | None) -> None:
    for s in secrets:
        if s:
            await conn.execute("delete from vault.secrets where id = $1::uuid", str(s))
