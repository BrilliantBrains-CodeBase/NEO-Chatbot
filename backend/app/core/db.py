import asyncpg

from app.core.config import get_settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """One shared connection pool, created on first use.

    statement_cache_size=0 because the live database is reached through the Supavisor pooler
    in transaction mode, which does not support prepared statements.
    """
    global _pool
    if _pool is None:
        if not get_settings().database_url:
            raise RuntimeError("DATABASE_URL is not set (see backend/.env.example)")
        _pool = await asyncpg.create_pool(
            get_settings().database_url,
            min_size=1,
            max_size=10,
            statement_cache_size=0,
            command_timeout=10,
            timeout=5,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
