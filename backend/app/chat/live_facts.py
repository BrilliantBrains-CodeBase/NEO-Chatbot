"""Facts the Knowledge base reads LIVE from the Dashboard and CRM (user, 2026-10-31): the clinic's details,
hours, services, doctors and online consults already have a home there, so they are never typed again. Each
has a stable key (the clinic onboarding questionnaire uses the same keys) and wins over a Knowledge base fact
with that key. Q&A answers link them like any fact: "We are at {clinic_address}." shows the current address.
"""

import json
import time as clock
from datetime import time, timedelta
from typing import Any

import asyncpg

DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

# key -> where staff change it (shown in the Knowledge base and the onboarding file).
SOURCE = {
    "clinic_name": "Chatbot → Login & security → Clinics",
    "clinic_phone": "Chatbot → Clinic info → Contact & hours",
    "clinic_whatsapp": "Chatbot → Clinic info → Contact & hours",
    "clinic_website": "Chatbot → Login & security → Clinics",
    "clinic_address": "Chatbot → Clinic info → Contact & hours",
    "landmark": "Chatbot → Clinic info → Contact & hours",
    "google_maps_link": "Chatbot → Clinic info → Contact & hours",
    "clinic_email": "Chatbot → Clinic info → Contact & hours",
    "parking_available": "Chatbot → Clinic info → Contact & hours",
    "emergency_contact_number": "Chatbot → Clinic info → Contact & hours",
    "outside_working_hours": "Chatbot → Clinic info → Contact & hours (closed message)",
    **{f"timings_{d.lower()}": "Chatbot → Clinic info → Contact & hours" for d in DAYS},
    "clinic_open_time": "Chatbot → Clinic info → Contact & hours",
    "clinic_close_time": "Chatbot → Clinic info → Contact & hours",
    "last_appointment_time": "Chatbot → Doctors (clinic slot lengths) / clinic settings",
    "consultation_length": "Chatbot → Doctors (clinic slot lengths)",
    "booking_window": "Clinic settings (booking window)",
    "services_provided": "Chatbot → Clinic info → Services",
    "services_not_provided": "Chatbot → Clinic info → Services (not offered)",
    "doctors_count": "Chatbot → Doctors",
    "doctors_names": "Chatbot → Doctors",
    "online_consultations": "Chatbot → Doctors (online hours) / Integrations → Cal.com",
    "online_doctors": "Chatbot → Doctors (online hours)",
    "online_timings": "Chatbot → Doctors (online hours)",
    "online_platform": "Chatbot → Integrations → Cal.com",
    "chatbot_clinic_name": "Chatbot → Appearance (bot name)",
}


def _t(hm: Any) -> str:
    """09:30 / time(9, 30) -> 9:30 AM."""
    h, m = (hm.hour, hm.minute) if isinstance(hm, time) else (int(str(hm)[:2]), int(str(hm)[3:5]))
    return f"{(h + 11) % 12 + 1}:{m:02d} {'AM' if h < 12 else 'PM'}"


def _settings(raw: Any) -> dict[str, Any]:
    value = json.loads(raw) if isinstance(raw, str) else raw
    return value if isinstance(value, dict) else {}


_kept: dict[str, tuple[float, dict[str, str]]] = {}


async def live_facts(conn: asyncpg.Connection, clinic_id: str) -> dict[str, str]:
    """key -> today's value, read from the Dashboard and CRM (kept a minute). Empty values are left out."""
    hit = _kept.get(clinic_id)
    if hit and clock.monotonic() - hit[0] < 60:
        return hit[1]
    out = await _read(conn, clinic_id)
    _kept[clinic_id] = (clock.monotonic(), out)
    return out


async def _read(conn: asyncpg.Connection, clinic_id: str) -> dict[str, str]:
    c = await conn.fetchrow("select * from app.clinics where id = $1", clinic_id)
    if c is None:
        return {}
    pub = _settings(
        await conn.fetchval("select published from app.clinic_settings where clinic_id = $1", clinic_id)
    )
    contact, services = pub.get("contact") or {}, pub.get("services") or {}
    out: dict[str, str] = {
        "clinic_name": c["name"] or "",
        "clinic_phone": contact.get("phone") or c["phone"] or "",
        "clinic_whatsapp": contact.get("whatsapp") or c["whatsapp"] or "",
        "clinic_website": c["website"] or "",
        "clinic_address": contact.get("address") or "",
        "landmark": contact.get("landmark") or "",
        "google_maps_link": contact.get("maps_link") or "",
        "clinic_email": contact.get("email") or "",
        "parking_available": contact.get("parking") or "",
        "emergency_contact_number": contact.get("emergency_number") or "",
        "outside_working_hours": contact.get("closed_message") or "",
        "chatbot_clinic_name": c["bot_name"] or "",
        "consultation_length": f"About {c['slot_minutes']} minutes",
        "booking_window": f"Up to {c['booking_window_days']} days ahead",
    }
    hours = {h.get("day"): h for h in contact.get("hours") or []}
    for i, day in enumerate(DAYS):
        h = hours.get(day)
        if h:
            open_ = h.get("open") and h.get("start") and h.get("end")
            out[f"timings_{day.lower()}"] = f"{_t(h['start'])} to {_t(h['end'])}" if open_ else "Closed"
        else:
            closed = i in (c["closed_weekdays"] or [])
            out[f"timings_{day.lower()}"] = (
                "Closed" if closed else f"{_t(c['open_time'])} to {_t(c['close_time'])}"
            )
    out["clinic_open_time"] = _t(c["open_time"])
    out["clinic_close_time"] = _t(c["close_time"])
    last = timedelta(hours=c["close_time"].hour, minutes=c["close_time"].minute) - timedelta(
        minutes=c["last_slot_before_close_min"]
    )
    out["last_appointment_time"] = _t(f"{last.seconds // 3600:02d}:{last.seconds % 3600 // 60:02d}")
    shown = [s["name"] for s in services.get("items") or [] if s.get("show") and s.get("name")]
    out["services_provided"] = ", ".join(shown)
    not_offered = services.get("not_offered") or []
    out["services_not_provided"] = (
        ", ".join(str(x) for x in not_offered) if isinstance(not_offered, list) else str(not_offered)
    )

    doctors = await conn.fetch(
        "select id, name from app.doctors where clinic_id = $1 and active order by sort_order, name",
        clinic_id,
    )
    out["doctors_count"] = str(len(doctors)) if doctors else ""
    out["doctors_names"] = ", ".join(d["name"] for d in doctors)
    online = await conn.fetch(
        """select d.name, a.weekday, a.start_time, a.end_time from app.doctor_availability a
           join app.doctors d on d.id = a.doctor_id and d.active
           where a.clinic_id = $1 and a.mode = 'online'
           order by d.sort_order, d.name, a.weekday, a.start_time""",
        clinic_id,
    )
    names = list(dict.fromkeys(r["name"] for r in online))
    out["online_consultations"] = "Yes" if names else "No"
    out["online_doctors"] = ", ".join(names)

    def hours_of(n: str) -> str:
        return ", ".join(
            f"{DAYS[r['weekday']][:3]} {_t(r['start_time'])} to {_t(r['end_time'])}"
            for r in online
            if r["name"] == n
        )

    out["online_timings"] = "; ".join(f"{n}: {hours_of(n)}" for n in names)
    calcom = await conn.fetchval("select 1 from app.calcom_accounts where clinic_id = $1", clinic_id)
    out["online_platform"] = (
        "Google Meet (the link is emailed when the consult is confirmed)" if calcom else ""
    )
    return {k: v.strip() for k, v in out.items() if v and v.strip()}
