"""Clinic settings and My profile (migration 0038): Admins read and save the clinic's details, alerts and
look; Front Desk cannot open Settings but every page still gets the clinic's logo; each person changes their
own name, phone and photo, and a confirmed sign-in email reaches their profile. Test clinic CL99."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_crm_access import world
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api", "world"]  # the fixtures

URL = "/v1/crm/clinic-settings/CL99"
pytestmark = needs_db
PNG = (  # one pixel
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJ"
    "RU5ErkJggg=="
)
DETAILS = {
    "name": "Test Clinic",
    "email": "Front@Test.invalid",
    "phone": "+919000000001",
    "alt_phone": None,
    "whatsapp": "+919000000002",
    "website": "https://test.invalid",
    "address": "  1st floor,   Test House ",
    "city": "Bengaluru",
    "state": "Karnataka",
    "postal_code": "560037",
    "country": "India",
    "registration_no": "",
    "gstin": "29abcde1234f1z5",
    "lead_assignment": "manual",
}


@pytest.fixture
async def kept() -> AsyncIterator[None]:
    """CL99 as it was before the test."""
    pool = await get_pool()
    cols = "name, email, phone, alt_phone, whatsapp, website, address, city, state, postal_code, country, " \
        "registration_no, gstin, lead_assignment"  # fmt: skip
    was = await pool.fetchrow(f"select {cols} from app.clinics where id = 'CL99'")
    try:
        yield
    finally:
        pool = await get_pool()
        sets = ", ".join(f"{k} = ${i + 1}" for i, k in enumerate(was.keys()))
        await pool.execute(f"update app.clinics set {sets} where id = 'CL99'", *was.values())
        await pool.execute("delete from app.clinic_branding where clinic_id = 'CL99'")
        await pool.execute("delete from app.clinic_alerts where clinic_id = 'CL99'")


async def test_admins_save_the_clinic_and_front_desk_cannot(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any], kept: None
) -> None:
    manager = signed_in_as(monkeypatch, world["manager"]["id"])
    got = await api.get(URL, headers=manager)
    assert got.status_code == 200, got.text
    assert got.json()["can_edit"] is True
    assert got.json()["alerts"] == {"emergency_admins": True, "emergency_emails": []}

    body = {
        "details": DETAILS,
        "alerts": {"emergency_admins": False, "emergency_emails": ["Desk@Test.invalid "]},
    }
    put = await api.put(URL, json=body, headers=manager)
    assert put.status_code == 200, put.text
    d = put.json()["details"]
    assert d["email"] == "front@test.invalid" and d["address"] == "1st floor, Test House"
    assert (
        d["gstin"] == "29ABCDE1234F1Z5" and d["registration_no"] is None and d["lead_assignment"] == "manual"
    )
    assert put.json()["alerts"] == {"emergency_admins": False, "emergency_emails": ["desk@test.invalid"]}

    bad = await api.put(URL, json={**body, "details": {**DETAILS, "gstin": "12"}}, headers=manager)
    assert bad.status_code == 422

    desk = signed_in_as(monkeypatch, world["desk"]["id"])
    assert (await api.get(URL, headers=desk)).status_code == 403
    assert (await api.put(URL, json=body, headers=desk)).status_code == 403


async def test_the_logo_shows_to_everyone_but_only_admins_change_it(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any], kept: None
) -> None:
    manager = signed_in_as(monkeypatch, world["manager"]["id"])
    assert (await api.get(f"{URL}/branding", headers=manager)).json()["logo"] is None
    put = await api.put(f"{URL}/branding", json={"logo": PNG, "favicon": PNG}, headers=manager)
    assert put.status_code == 200, put.text
    assert put.json()["updated_at"]
    refused = await api.put(f"{URL}/branding", json={"logo": "https://x.invalid/a.png"}, headers=manager)
    assert refused.status_code == 422

    desk = signed_in_as(monkeypatch, world["desk"]["id"])
    seen = await api.get(f"{URL}/branding", headers=desk)
    assert seen.status_code == 200 and seen.json()["logo"] == PNG
    assert (await api.put(f"{URL}/branding", json={}, headers=desk)).status_code == 403

    manager = signed_in_as(monkeypatch, world["manager"]["id"])
    gone = await api.put(f"{URL}/branding", json={"logo": None, "favicon": PNG}, headers=manager)
    assert gone.json()["logo"] is None and gone.json()["favicon"] == PNG


async def test_my_profile_name_phone_photo_and_email(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch, world: dict[str, Any]
) -> None:
    desk = signed_in_as(monkeypatch, world["desk"]["id"])
    r = await api.patch("/v1/crm/me", json={"name": "Desk  Person", "phone": "+919000000003"}, headers=desk)
    assert r.status_code == 200, r.text
    assert (r.json()["name"], r.json()["phone"]) == ("Desk Person", "+919000000003")
    kept_phone = await api.patch("/v1/crm/me", json={"name": "Desk Person"}, headers=desk)
    assert kept_phone.json()["phone"] == "+919000000003"  # left out: unchanged
    assert (
        await api.patch("/v1/crm/me", json={"name": "Desk", "phone": "12"}, headers=desk)
    ).status_code == 422

    photo = await api.put("/v1/crm/me/photo", json={"photo": PNG}, headers=desk)
    assert photo.status_code == 200 and photo.json()["photo"] == PNG
    svg = await api.put(
        "/v1/crm/me/photo", json={"photo": "data:image/svg+xml;base64,PHN2Zz4="}, headers=desk
    )
    assert svg.status_code == 422  # an SVG can carry script: photos are PNG, JPG or WebP
    assert (await api.put("/v1/crm/me/photo", json={"photo": None}, headers=desk)).json()["photo"] is None

    taken = await api.post("/v1/crm/me/email", json={"email": world["manager"]["email"]}, headers=desk)
    assert taken.status_code == 409
    same = await api.post("/v1/crm/me/email", json={"email": world["desk"]["email"].upper()}, headers=desk)
    assert same.status_code == 422
    assert (
        await api.post("/v1/crm/me/email", json={"email": "new@test.invalid"}, headers=desk)
    ).status_code == 204

    # Supabase Auth changes the sign-in email once the person confirms it: the profile follows.
    pool = await get_pool()
    await pool.execute(
        "update auth.users set email = 'Moved@Test.invalid' where id = $1::uuid", world["desk"]["id"]
    )
    assert (
        await pool.fetchval("select email from app.profiles where id = $1::uuid", world["desk"]["id"])
        == "moved@test.invalid"
    )
