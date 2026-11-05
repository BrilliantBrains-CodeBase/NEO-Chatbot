"""CRM notifications (JSON only): what the bell shows. The rows are the clinic's (migration 0036); read and
cleared are each person's own. Clearing never touches the patient's request. An emergency cannot be cleared
until it is handled, and one with no request (the patient gave no phone number) is acknowledged for everyone.
"""

import json
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.v1.crm import can_see
from app.core.db import get_pool
from app.crm import permissions as perm
from app.crm.auth import Staff, staff

router = APIRouter(prefix="/crm", tags=["crm"])

CLINIC = Annotated[str, Query(pattern=r"^CL\d{2,3}$")]
Kind = Literal[
    "book", "online", "cancel", "reschedule", "callback", "question", "callback_late", "booking_late",
    "lead_new", "lead_assigned", "access_request", "integration_failed",
]  # fmt: skip
# A notification shows to those who can see its screen (Who sees what).
SCREENS = ("inbox", "leads", "team", "dash_integrations")

# $1 clinic, $2 the person, $3 the screens they can see. Cleared rows and kinds this person turned off are
# left out; an emergency never is. One meant for a colleague alone shows only to them.
SEEN = """from app.notifications n
  left join app.notification_receipts r on r.notification_id = n.id and r.user_id = $2::uuid
  left join app.notification_state s on s.user_id = $2::uuid and s.clinic_id = n.clinic_id
  left join app.notification_prefs f on f.user_id = $2::uuid
  where n.clinic_id = $1 and r.dismissed_at is null
    and n.screen = any($3::text[]) and (n.user_id is null or n.user_id = $2::uuid)
    and (n.severity = 'urgent' or not n.kind = any(coalesce(f.off_kinds, '{}'::text[])))"""
# "Mark as unread" leaves a receipt with no read time, which wins over "mark all read".
READ = """(r.read_at is not null
  or (r.user_id is null and s.read_all_at is not null and n.created_at <= s.read_all_at))"""
UNREAD = f"(not {READ} and n.resolved_at is null)"
URGENT_OPEN = "(n.severity = 'urgent' and n.resolved_at is null)"


class Summary(BaseModel):
    unread: int
    urgent: int  # emergencies nobody has handled yet, read or not


class Notification(BaseModel):
    id: str
    kind: str
    severity: str
    created_at: str
    read: bool
    resolved: bool
    resolved_by: str | None
    request_id: str | None
    tab: str | None  # the Inbox tab that holds the request
    lead_code: str | None
    name: str | None
    treatment: str | None
    reason: str | None
    time_passed: bool  # a booking whose time has gone while it waited: still worth a call
    count: int  # new leads grouped into this one
    detail: str | None  # the service that failed


class NotificationList(BaseModel):
    items: list[Notification]
    total: int
    unread: int
    urgent: int


class Prefs(BaseModel):
    off_kinds: list[Kind] = Field(default=[], max_length=12)
    sound: bool = False
    desktop: bool = False


async def _screens(conn: Any, clinic: str, user: Staff) -> list[str]:
    """Which of the bell's screens this person can see in this clinic."""
    role = "bb_admin" if user.bb_admin else user.roles.get(clinic)
    if role is None:
        return []
    rules = await perm.for_person(conn, clinic, user.id, role)
    dashboard = rules.get("dash_open", "hidden") != "hidden"  # a Dashboard tab needs the Dashboard open
    return [
        s for s in SCREENS if rules.get(s, "hidden") != "hidden" and (dashboard or not s.startswith("dash_"))
    ]


async def _allowed(user: Staff, clinic: str) -> None:
    can_see(user, clinic)
    if not await _screens(await get_pool(), clinic, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot see notifications here.")


async def _summary(conn: Any, clinic: str, user: Staff) -> Summary:
    row = await conn.fetchrow(
        f"""select count(*) filter (where {UNREAD}) unread,
              count(*) filter (where {URGENT_OPEN}) urgent {SEEN}""",
        clinic, user.id, await _screens(conn, clinic, user),
    )  # fmt: skip
    return Summary(unread=row["unread"], urgent=row["urgent"])


@router.get("/notifications/summary", response_model=Summary)
async def summary(user: Annotated[Staff, Depends(staff)], clinic: CLINIC) -> Summary:
    """The badge: quick enough to read every 30 seconds."""
    await _allowed(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await _summary(conn, clinic, user)


@router.get("/notifications/clinics", response_model=dict[str, Summary])
async def by_clinic(user: Annotated[Staff, Depends(staff)]) -> dict[str, Summary]:
    """The counts in each clinic where this person can see notifications, for the clinic switch."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        ids = (
            [r["id"] for r in await conn.fetch("select id from app.clinics where active")]
            if user.bb_admin
            else list(user.roles)
        )
        out: dict[str, Summary] = {}
        for clinic in ids:
            if await _screens(conn, clinic, user):
                out[clinic] = await _summary(conn, clinic, user)
    return out


@router.get("/notifications", response_model=NotificationList)
async def notifications(
    user: Annotated[Staff, Depends(staff)],
    clinic: CLINIC,
    show: Literal["all", "unread"] = "all",
    kind: Kind | Literal["emergency"] | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotificationList:
    """Emergencies nobody has handled come first, then the newest, a page at a time."""
    await _allowed(user, clinic)
    where = f"{SEEN} and ($4::text is null or n.kind = $4)" + (f" and {UNREAD}" if show == "unread" else "")
    pool = await get_pool()
    async with pool.acquire() as conn:
        screens = await _screens(conn, clinic, user)
        total = await conn.fetchval(f"select count(*) {where}", clinic, user.id, screens, kind)
        rows = await conn.fetch(
            f"""select n.*, {READ} is_read, q.type tab, q.data, l.lead_code, l.full_name,
                  p.full_name resolver,
                  q.status = 'pending' and exists (select 1 from app.appointments a
                    where a.request_id = q.id and a.status = 'missed') time_passed
                from (select n.id {where}
                      order by {URGENT_OPEN} desc, n.created_at desc, n.id desc limit $5 offset $6) page
                join app.notifications n on n.id = page.id
                left join app.notification_receipts r on r.notification_id = n.id and r.user_id = $2::uuid
                left join app.notification_state s on s.user_id = $2::uuid and s.clinic_id = n.clinic_id
                left join app.requests q on q.id = n.request_id
                left join app.leads l on l.id = n.lead_id
                left join app.profiles p on p.id = n.resolved_by
                order by {URGENT_OPEN} desc, n.created_at desc, n.id desc""",
            clinic, user.id, screens, kind, limit, offset,
        )  # fmt: skip
        counts = await _summary(conn, clinic, user)
    items = []
    for r in rows:
        data = r["data"] or {}
        if isinstance(data, str):
            data = json.loads(data)
        items.append(
            Notification(
                id=str(r["id"]),
                kind=r["kind"],
                severity=r["severity"],
                created_at=r["created_at"].isoformat(),
                read=r["is_read"],
                resolved=r["resolved_at"] is not None,
                resolved_by=r["resolver"],
                request_id=str(r["request_id"]) if r["request_id"] else None,
                tab=r["tab"],
                lead_code=r["lead_code"],
                name=data.get("name") or r["full_name"],
                treatment=data.get("treatment"),
                reason=data.get("reason"),
                time_passed=bool(r["time_passed"]),
                count=r["count"],
                detail=r["detail"],
            )  # fmt: skip
        )
    return NotificationList(items=items, total=total, unread=counts.unread, urgent=counts.urgent)


@router.get("/notifications/prefs", response_model=Prefs)
async def get_prefs(user: Annotated[Staff, Depends(staff)]) -> Prefs:
    row = await (await get_pool()).fetchrow(
        "select off_kinds, sound, desktop from app.notification_prefs where user_id = $1::uuid", user.id
    )
    return Prefs(**dict(row)) if row else Prefs()


@router.put("/notifications/prefs", response_model=Prefs)
async def put_prefs(user: Annotated[Staff, Depends(staff)], body: Prefs) -> Prefs:
    """One person's choices, the same on every device. Emergencies cannot be turned off."""
    await (await get_pool()).execute(
        """insert into app.notification_prefs (user_id, off_kinds, sound, desktop)
           values ($1::uuid, $2, $3, $4)
           on conflict (user_id) do update
             set off_kinds = $2, sound = $3, desktop = $4, updated_at = now()""",
        user.id, list(dict.fromkeys(body.off_kinds)), body.sound, body.desktop,
    )  # fmt: skip
    return body


@router.post("/notifications/read-all", response_model=Summary)
async def read_all(user: Annotated[Staff, Depends(staff)], clinic: CLINIC) -> Summary:
    await _allowed(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """insert into app.notification_state (user_id, clinic_id, read_all_at)
               values ($1::uuid, $2, now())
               on conflict (user_id, clinic_id) do update set read_all_at = now()""",
            user.id, clinic,
        )  # fmt: skip
        await conn.execute(  # those marked unread by hand are read now too
            """update app.notification_receipts r set read_at = now() from app.notifications n
               where n.id = r.notification_id and r.user_id = $1::uuid and n.clinic_id = $2
                 and r.read_at is null""",
            user.id, clinic,
        )  # fmt: skip
        return await _summary(conn, clinic, user)


@router.post("/notifications/clear-read", response_model=Summary)
async def clear_read(user: Annotated[Staff, Depends(staff)], clinic: CLINIC) -> Summary:
    """Clears what this person has read. Emergencies nobody has handled stay."""
    await _allowed(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            f"""insert into app.notification_receipts (notification_id, user_id, read_at, dismissed_at)
                select n.id, $2::uuid, now(), now() {SEEN} and {READ} and not {URGENT_OPEN}
                on conflict (notification_id, user_id) do update set dismissed_at = now()""",
            clinic, user.id, await _screens(conn, clinic, user),
        )  # fmt: skip
        return await _summary(conn, clinic, user)


async def _one(user: Staff, notification_id: UUID) -> Any:
    row = await (await get_pool()).fetchrow(
        """select id, clinic_id, severity, request_id, resolved_at, screen, user_id
           from app.notifications where id = $1""",
        notification_id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found.")
    await _allowed(user, row["clinic_id"])
    meant_for = row["user_id"]
    hidden = row["screen"] not in await _screens(await get_pool(), row["clinic_id"], user)
    if hidden or (meant_for and str(meant_for) != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found.")
    return row


@router.post("/notifications/{notification_id}/read", response_model=Summary)
async def mark_read(user: Annotated[Staff, Depends(staff)], notification_id: UUID) -> Summary:
    row = await _one(user, notification_id)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """insert into app.notification_receipts (notification_id, user_id, read_at)
               values ($1, $2::uuid, now())
               on conflict (notification_id, user_id) do update set read_at = now()""",
            notification_id, user.id,
        )  # fmt: skip
        return await _summary(conn, row["clinic_id"], user)


@router.post("/notifications/{notification_id}/unread", response_model=Summary)
async def mark_unread(user: Annotated[Staff, Depends(staff)], notification_id: UUID) -> Summary:
    row = await _one(user, notification_id)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """insert into app.notification_receipts (notification_id, user_id, read_at)
               values ($1, $2::uuid, null)
               on conflict (notification_id, user_id) do update set read_at = null""",
            notification_id, user.id,
        )  # fmt: skip
        return await _summary(conn, row["clinic_id"], user)


@router.post("/notifications/{notification_id}/dismiss", response_model=Summary)
async def dismiss(user: Annotated[Staff, Depends(staff)], notification_id: UUID) -> Summary:
    """Clears it from this person's bell; the request stays in the Inbox. An emergency with a request waits
    until it is handled. One with no request has nothing to handle: this acknowledges it for everyone."""
    row = await _one(user, notification_id)
    urgent_open = row["severity"] == "urgent" and row["resolved_at"] is None
    if urgent_open and row["request_id"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Handle this emergency in the Inbox first.")
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        if urgent_open:
            await conn.execute(
                "update app.notifications set resolved_at = now(), resolved_by = $2::uuid where id = $1",
                notification_id, user.id,
            )  # fmt: skip
        await conn.execute(
            """insert into app.notification_receipts (notification_id, user_id, read_at, dismissed_at)
               values ($1, $2::uuid, now(), now())
               on conflict (notification_id, user_id) do update set dismissed_at = now(),
                 read_at = coalesce(app.notification_receipts.read_at, now())""",
            notification_id, user.id,
        )  # fmt: skip
        return await _summary(conn, row["clinic_id"], user)
