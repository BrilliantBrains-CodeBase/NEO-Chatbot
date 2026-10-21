import asyncio
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.core.cache import get_redis
from app.core.db import get_pool

router = APIRouter(tags=["health"])

CHECK_TIMEOUT_S = 3

Check = Literal["ok", "down"]
SwitchableCheck = Literal["ok", "down", "off"]


class Live(BaseModel):
    status: Literal["ok"] = "ok"


class Ready(BaseModel):
    status: Literal["ok", "degraded"]
    database: Check
    redis: SwitchableCheck


@router.get("/health", response_model=Live)
async def live() -> Live:
    """The process is up. Used by Docker and Caddy."""
    return Live()


async def _database() -> Check:
    try:
        pool = await asyncio.wait_for(get_pool(), CHECK_TIMEOUT_S)
        await asyncio.wait_for(pool.fetchval("select 1"), CHECK_TIMEOUT_S)
        return "ok"
    except Exception:
        return "down"


async def _redis() -> SwitchableCheck:
    client = get_redis()
    if client is None:
        return "off"
    try:
        await asyncio.wait_for(client.ping(), CHECK_TIMEOUT_S)
        return "ok"
    except Exception:
        return "down"


@router.get("/health/ready", response_model=Ready)
async def ready(response: Response) -> Ready:
    """Database (and Redis, when switched on) are reachable. 503 if any is down."""
    database, redis = await asyncio.gather(_database(), _redis())
    ok = database == "ok" and redis != "down"
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Ready(status="ok" if ok else "degraded", database=database, redis=redis)
