"""Shared test tools for database tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import pytest

from app.core.config import get_settings

# A rejected row: a rule (constraint) error, or a data error raised while a generated column is
# computed (e.g. an inverted time range). Either way the row does not get in.
Rejected = (asyncpg.exceptions.IntegrityConstraintViolationError, asyncpg.exceptions.DataError)


@pytest.fixture
async def tx() -> AsyncIterator[asyncpg.Connection]:
    """A database connection inside a transaction that is always rolled back."""
    get_settings.cache_clear()
    conn = await asyncpg.connect(get_settings().database_url, statement_cache_size=0, timeout=15)
    tr = conn.transaction()
    await tr.start()
    try:
        yield conn
    finally:
        await tr.rollback()
        await conn.close()


@asynccontextmanager
async def rejected(db: asyncpg.Connection) -> AsyncIterator[None]:
    """Expect the block to be rejected. A savepoint keeps the test's transaction usable afterwards."""
    with pytest.raises(Rejected):
        async with db.transaction():
            yield
