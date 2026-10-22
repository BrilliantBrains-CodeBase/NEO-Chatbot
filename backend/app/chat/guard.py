"""Who may call the chat API: the clinic must exist and be active, the request must come from that
clinic's own website, and no visitor or IP may send more than a set number of messages a minute.
"""

import os
import time
from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.db import get_pool

VISITOR_PER_MIN = 20
IP_PER_MIN = 60
CLINIC_CACHE_S = 60

# Local addresses are accepted only outside production (the dev playground and tests).
LOCAL_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
}


@dataclass(frozen=True)
class Clinic:
    id: str
    bot_name: str
    allowed_origins: tuple[str, ...]


_clinics: dict[str, tuple[float, Clinic | None]] = {}


async def get_clinic(clinic_id: str) -> Clinic | None:
    """An active clinic, cached for a minute so every message does not cost a database query."""
    now = time.monotonic()
    hit = _clinics.get(clinic_id)
    if hit and now - hit[0] < CLINIC_CACHE_S:
        return hit[1]
    pool = await get_pool()
    row = await pool.fetchrow(
        "select id, bot_name, allowed_origins from app.clinics where id = $1 and active", clinic_id
    )
    clinic = Clinic(row["id"], row["bot_name"], tuple(row["allowed_origins"])) if row else None
    _clinics[clinic_id] = (now, clinic)
    return clinic


def origin_allowed(clinic: Clinic, origin: str | None) -> bool:
    if not origin:
        return False
    origin = origin.rstrip("/")
    if origin in clinic.allowed_origins:
        return True
    # The www and bare forms of the clinic's site are the same site.
    alt = origin.replace("://www.", "://") if "://www." in origin else origin.replace("://", "://www.", 1)
    if alt in clinic.allowed_origins:
        return True
    return get_settings().app_env != "production" and origin in LOCAL_ORIGINS


class RateLimiter:
    """Sliding one-minute windows. In memory per server instance: a first line of defence; Vercel's
    firewall rate limit is the second (and Redis replaces this in Phase 2)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        if len(self._hits) > 10_000:  # forget idle keys, so fake ids cannot fill the memory
            self._hits = defaultdict(deque, {k: q for k, q in self._hits.items() if q and now - q[-1] <= 60})
        q = self._hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


def client_ip(headers: Mapping[str, str], direct: str | None) -> str:
    """The visitor's IP. On Vercel every request comes from Vercel's proxy, which sets x-real-ip;
    anywhere else that header could be faked, so the direct address is used."""
    if os.environ.get("VERCEL") == "1":
        real = headers.get("x-real-ip")
        if real:
            return real
    return direct or "unknown"


limiter = RateLimiter()
