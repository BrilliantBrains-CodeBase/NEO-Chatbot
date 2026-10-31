"""Dashboard → Doctors: add and save a doctor with all settings; in-clinic and online hours may overlap but
two rows of one kind may not; 5 / 10 minute slots; clinic defaults. Uses test clinic CL99 and cleans up."""

from typing import Any

import pytest
from httpx import AsyncClient

from app.core.db import close_pool, get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture

URL = "/v1/crm/console/CL99/doctors"


def _doctor(**over: Any) -> dict[str, Any]:
    return {
        "name": "Dr Test Doctor",
        "role_title": "Consultant",
        "qualifications": "MBBS",
        "photo": "https://example.com/dr.jpg",
        "about": "Test doctor.",
        "stats": [{"label": "Years experience", "value": "10+"}],
        "in_clinic_minutes": 10,
        "online_minutes": None,
        "in_clinic": [{"weekday": 1, "start": "10:00", "end": "13:00"}],
        "online": [{"weekday": 1, "start": "14:00", "end": "16:00"}],
        "leave": [{"from_date": "2030-01-05", "to_date": "2030-01-06", "reason": "Conference"}],
        **over,
    }


@needs_db
async def test_doctor_with_all_settings(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    before = await pool.fetchrow(
        "select slot_minutes, online_slot_minutes from app.clinics where id = 'CL99'"
    )
    made: str | None = None
    try:
        # Add: every setting comes back as saved.
        r = await api.post(URL, json=_doctor(), headers=headers)
        assert r.status_code == 200, r.text
        d = next(x for x in r.json()["doctors"] if x["name"] == "Dr Test Doctor")
        made = d["id"]
        assert d["in_clinic_minutes"] == 10 and d["online_minutes"] is None and not d["calcom"]
        assert d["in_clinic"] == [{"weekday": 1, "start": "10:00", "end": "13:00"}]
        assert d["online"] == [{"weekday": 1, "start": "14:00", "end": "16:00"}]
        assert d["leave"][0]["reason"] == "Conference" and d["stats"][0]["value"] == "10+"
        assert d["photo"] == "https://example.com/dr.jpg"

        # In-clinic and online hours may overlap (a booking in one hides that time in the other).
        both = _doctor(online=[{"weekday": 1, "start": "10:00", "end": "13:00"}])
        r = await api.put(f"{URL}/{made}", json=both, headers=headers)
        assert r.status_code == 200, r.text

        # Two rows of the same kind that overlap are refused, and nothing changes.
        bad = _doctor(
            online=[
                {"weekday": 1, "start": "10:00", "end": "13:00"},
                {"weekday": 1, "start": "12:00", "end": "14:00"},
            ]
        )
        r = await api.put(f"{URL}/{made}", json=bad, headers=headers)
        assert r.status_code == 422 and "overlap" in r.text
        rows = await pool.fetchval(
            "select count(*) from app.doctor_availability where doctor_id = $1::uuid", made
        )
        assert rows == 2

        # A length that is not offered is refused; 5 minutes is fine.
        r = await api.put(f"{URL}/{made}", json=_doctor(online_minutes=25), headers=headers)
        assert r.status_code == 422
        r = await api.put(
            f"{URL}/{made}",
            json=_doctor(online_minutes=5, active=False, online=[], about="Changed."),
            headers=headers,
        )
        assert r.status_code == 200, r.text
        d = next(x for x in r.json()["doctors"] if x["id"] == made)
        assert d["online_minutes"] == 5 and d["active"] is False
        assert d["online"] == [] and d["about"] == "Changed."

        # Clinic defaults.
        r = await api.put(
            "/v1/crm/console/CL99/doctors-defaults",
            json={"slot_minutes": 10, "online_slot_minutes": 20},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["defaults"] == {"slot_minutes": 10, "online_slot_minutes": 20}
        r = await api.put(
            "/v1/crm/console/CL99/doctors-defaults",
            json={"slot_minutes": 7, "online_slot_minutes": 20},
            headers=headers,
        )
        assert r.status_code == 422
    finally:
        if made:
            await pool.execute("delete from app.doctors where id = $1::uuid", made)
        await pool.execute(
            "update app.clinics set slot_minutes = $1, online_slot_minutes = $2 where id = 'CL99'",
            before["slot_minutes"], before["online_slot_minutes"],
        )  # fmt: skip
        await close_pool()
