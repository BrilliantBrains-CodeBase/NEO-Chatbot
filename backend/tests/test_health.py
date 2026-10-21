from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import cache, db
from app.core.config import get_settings
from app.main import create_app


async def _client(monkeypatch: pytest.MonkeyPatch, **env: str) -> AsyncClient:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    db._pool = None
    cache._redis = None
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


@pytest.fixture(autouse=True)
async def reset() -> AsyncIterator[None]:
    yield
    await cache.close_redis()
    get_settings.cache_clear()


# Ports where nothing listens, so the checks must report "down".
DEAD_DB = "postgresql://u:p@127.0.0.1:1/x"
DEAD_REDIS = "redis://127.0.0.1:1/0"


async def test_live(monkeypatch: pytest.MonkeyPatch) -> None:
    async with await _client(monkeypatch, DATABASE_URL=DEAD_DB, REDIS_URL="") as c:
        r = await c.get("/v1/health")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/json"
    assert r.json() == {"status": "ok"}


async def test_ready_database_down_redis_off(monkeypatch: pytest.MonkeyPatch) -> None:
    async with await _client(monkeypatch, DATABASE_URL=DEAD_DB, REDIS_URL="") as c:
        r = await c.get("/v1/health/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded", "database": "down", "redis": "off"}


async def test_ready_database_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    async with await _client(monkeypatch, DATABASE_URL="", REDIS_URL="") as c:
        r = await c.get("/v1/health/ready")
    assert r.status_code == 503
    assert r.json()["database"] == "down"


async def test_ready_redis_switched_on_but_down(monkeypatch: pytest.MonkeyPatch) -> None:
    async with await _client(monkeypatch, DATABASE_URL=DEAD_DB, REDIS_URL=DEAD_REDIS) as c:
        r = await c.get("/v1/health/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded", "database": "down", "redis": "down"}
