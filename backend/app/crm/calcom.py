"""Cal.com: books an approved online consult and returns its Google Meet link (API v2); connects a clinic's
own account (its API key, kept in Vault) and the webhook that syncs its bookings back.

Without a clinic's own key, the backend's CALCOM_API_KEY and CALCOM_EVENT_TYPE_ID are used (as before).
The event type has Google Meet as its location; Cal.com emails the patient the confirmation, link and
reminders."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.core.config import get_settings

API = "https://api.cal.com/v2"
VERSION = "2024-08-13"  # bookings API version


class CalcomError(Exception):
    """Cal.com refused or could not be reached; the message is shown to staff."""


@dataclass
class Booking:
    uid: str
    meet_link: str | None


def _headers(key: str | None = None, version: str = VERSION) -> dict[str, str]:
    key = key or get_settings().calcom_api_key
    if not key:
        raise CalcomError("Online consults are not connected to Cal.com yet (CALCOM_API_KEY is missing).")
    return {"Authorization": f"Bearer {key}", "cal-api-version": version}


async def _call(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    key: str | None = None,
    what: str = "the booking",
    version: str = VERSION,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.request(method, API + path, json=body, headers=_headers(key, version))
    except httpx.HTTPError:
        raise CalcomError("Cal.com could not be reached. Please try again.") from None
    data: dict[str, Any] = r.json() if r.content else {}
    if r.status_code >= 400 or data.get("status") != "success":
        err = data.get("error")
        msg = err.get("message") if isinstance(err, dict) else err
        if r.status_code in (401, 403):
            raise CalcomError("Cal.com did not accept the API key. Please check it and try again.")
        raise CalcomError(f"Cal.com did not accept {what}: {msg or r.status_code}.")
    return data


async def _post(path: str, body: dict[str, Any], key: str | None = None) -> dict[str, Any]:
    return await _call("POST", path, body, key)


@dataclass
class Account:
    """Which Cal.com to use: the clinic's own (key from Vault, the doctor's event) or the backend's."""

    key: str | None = None  # None: CALCOM_API_KEY
    event: int | None = None  # None: CALCOM_EVENT_TYPE_ID


# ---------- a clinic's own account ----------
TRIGGERS = ["BOOKING_CREATED", "BOOKING_RESCHEDULED", "BOOKING_CANCELLED"]


async def account(key: str) -> str:
    """Checks the API key with Cal.com; returns the account's name (shown to staff)."""
    data = (await _call("GET", "/me", key=key, what="the API key"))["data"]
    return str(data.get("name") or data.get("username") or data.get("email") or "Cal.com account")


async def add_webhook(key: str, url: str, secret: str) -> str:
    """Creates the webhook that tells us when a booking is made, moved or cancelled; returns its id."""
    body = {"active": True, "subscriberUrl": url, "triggers": TRIGGERS, "secret": secret}
    data = (await _call("POST", "/webhooks", body, key=key, what="the webhook"))["data"]
    return str(data["id"])


async def remove_webhook(key: str, webhook_id: str) -> None:
    await _call("DELETE", f"/webhooks/{webhook_id}", key=key, what="removing the webhook")


async def book(
    start: datetime,
    name: str,
    email: str,
    phone: str | None,
    note: dict[str, str],
    acc: Account | None = None,
) -> Booking:
    """Books the consult at `start` (a timezone-aware time), in the clinic's Cal.com when it has one."""
    acc = acc or Account()
    event = acc.event or get_settings().calcom_event_type_id
    if not event:
        raise CalcomError(
            "Online consults are not connected to Cal.com yet (CALCOM_EVENT_TYPE_ID is missing)."
        )
    body: dict[str, Any] = {
        "start": start.isoformat(),
        "eventTypeId": event,
        "attendee": {"name": name, "email": email, "timeZone": "Asia/Kolkata", "language": "en"},
        "metadata": {k: v[:500] for k, v in note.items() if v},
    }
    if phone:
        body["attendee"]["phoneNumber"] = phone
    data = (await _post("/bookings", body, acc.key))["data"]
    link = data.get("meetingUrl") or data.get("location")
    return Booking(
        uid=data["uid"], meet_link=link if str(link).startswith("https://meet.google.com/") else None
    )


async def reschedule(uid: str, start: datetime, reason: str, acc: Account | None = None) -> Booking:
    """Moves the booking. Cal.com gives it a new uid, emails the patient the new time, may change the link."""
    data = (
        await _post(
            f"/bookings/{uid}/reschedule",
            {"start": start.isoformat(), "reschedulingReason": reason[:500]},
            (acc or Account()).key,
        )
    )["data"]
    link = data.get("meetingUrl") or data.get("location")
    return Booking(
        uid=data["uid"], meet_link=link if str(link).startswith("https://meet.google.com/") else None
    )


async def cancel(uid: str, reason: str, acc: Account | None = None) -> None:
    await _post(f"/bookings/{uid}/cancel", {"cancellationReason": reason[:500]}, (acc or Account()).key)


# ---------- a doctor's online consults: a schedule (hours, holidays blocked) and an event ----------
SCHEDULES, EVENTS = "2024-06-11", "2024-06-14"  # the API versions of these endpoints
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]  # 0 = Sunday (CRM)


async def save_schedule(
    key: str, schedule_id: int | None, name: str, hours: list[tuple[int, str, str]], blocked: list[str]
) -> int:
    """Creates or updates the doctor's schedule: weekly hours (weekday 0 = Sunday, "HH:MM") and the days
    blocked (holidays, leave: "YYYY-MM-DD"). Returns its id."""
    body = {
        "name": name[:100],
        "timeZone": "Asia/Kolkata",
        "availability": [{"days": [DAYS[d]], "startTime": a, "endTime": b} for d, a, b in hours],
        "overrides": [{"date": day, "startTime": "00:00", "endTime": "00:00"} for day in blocked],
    }
    if schedule_id:
        data = await _call("PATCH", f"/schedules/{schedule_id}", body, key, "the schedule", SCHEDULES)
    else:
        data = await _call("POST", "/schedules", body | {"isDefault": False}, key, "the schedule", SCHEDULES)
    return int(data["data"]["id"])


async def save_event(
    key: str, event_id: int | None, title: str, slug: str, minutes: int, schedule_id: int
) -> int:
    """Creates or updates the doctor's online consult (Google Meet, on that schedule). Returns its id."""
    # Hidden: not listed on the clinic's Cal.com page; consults are booked through the chatbot / CRM only.
    body: dict[str, Any] = {
        "title": title[:100],
        "lengthInMinutes": minutes,
        "scheduleId": schedule_id,
        "hidden": True,
    }
    if event_id:
        data = await _call("PATCH", f"/event-types/{event_id}", body, key, "the consult", EVENTS)
    else:
        body |= {"slug": slug, "locations": [{"type": "integration", "integration": "google-meet"}]}
        data = await _call("POST", "/event-types", body, key, "the consult", EVENTS)
    return int(data["data"]["id"])


async def remove_doctor(key: str, event_id: int | None, schedule_id: int | None) -> None:
    """Removes a doctor's consult and schedule from Cal.com (best effort: they may be gone already)."""
    for path, version in ((f"/event-types/{event_id}", EVENTS), (f"/schedules/{schedule_id}", SCHEDULES)):
        if path.rsplit("/", 1)[1] not in ("None", ""):
            try:
                await _call("DELETE", path, key=key, what="removing it", version=version)
            except CalcomError:
                pass
