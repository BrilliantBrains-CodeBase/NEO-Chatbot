"""An outside service that failed shows in the bell of those who can see Dashboard → Integrations, once per
service, clinic and day. It names the service only: the details stay in that service's log. Never raises:
telling staff about a failure must not cause another one."""

import logging
from datetime import UTC, datetime
from typing import Any

from app.core.db import get_pool

log = logging.getLogger(__name__)


async def record(conn: Any, clinic: str, service: str) -> None:
    day = datetime.now(UTC).date().isoformat()
    await conn.execute(
        """insert into app.notifications (clinic_id, kind, screen, detail, dedupe_key)
           values ($1, 'integration_failed', 'dash_integrations', $2, $3)
           on conflict (dedupe_key) do nothing""",
        clinic, service, f"failed:{clinic}:{service}:{day}",
    )  # fmt: skip


async def report(clinic: str | None, service: str) -> None:
    if not clinic:
        return  # the BB Gmail, for no clinic: the email log shows it
    try:
        await record(await get_pool(), clinic, service)
    except Exception:
        log.exception("could not report that %s failed for %s", service, clinic)
