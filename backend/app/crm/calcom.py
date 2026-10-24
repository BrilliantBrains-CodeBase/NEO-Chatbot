"""Cal.com: books an approved online consult and returns its Google Meet link (API v2).

The event type (CALCOM_EVENT_TYPE_ID) has Google Meet as its location and the clinic's hours; Cal.com
emails the patient the confirmation, the link and reminders."""

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


def _headers() -> dict[str, str]:
    key = get_settings().calcom_api_key
    if not key:
        raise CalcomError("Online consults are not connected to Cal.com yet (CALCOM_API_KEY is missing).")
    return {"Authorization": f"Bearer {key}", "cal-api-version": VERSION}


async def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(API + path, json=body, headers=_headers())
    except httpx.HTTPError:
        raise CalcomError("Cal.com could not be reached. Please try again.") from None
    data: dict[str, Any] = r.json() if r.content else {}
    if r.status_code >= 400 or data.get("status") != "success":
        err = data.get("error")
        msg = err.get("message") if isinstance(err, dict) else err
        raise CalcomError(f"Cal.com did not accept the booking: {msg or r.status_code}.")
    return data


async def book(start: datetime, name: str, email: str, phone: str | None, note: dict[str, str]) -> Booking:
    """Books the consult at `start` (a timezone-aware time)."""
    event = get_settings().calcom_event_type_id
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
    data = (await _post("/bookings", body))["data"]
    link = data.get("meetingUrl") or data.get("location")
    return Booking(
        uid=data["uid"], meet_link=link if str(link).startswith("https://meet.google.com/") else None
    )


async def cancel(uid: str, reason: str) -> None:
    await _post(f"/bookings/{uid}/cancel", {"cancellationReason": reason[:500]})
