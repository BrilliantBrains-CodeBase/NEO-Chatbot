"""CRM sign-in check (app.crm.auth) and GET /v1/crm/me. The token check against Supabase's signing keys is
replaced by a stub; the profile and roles come from the real database (skipped without one)."""

import asyncio
import csv
import io
import uuid
from collections.abc import AsyncIterator
from typing import Any

import jwt
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.v1.crm import _import_phone, bulk_access, cell, export_phone, initials
from app.core.config import get_settings
from app.core.db import close_pool, get_pool
from app.crm import auth, webhooks, whatsapp
from app.crm.auth import Staff
from app.main import create_app

needs_db = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL not set")


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        yield client
    await close_pool()


def signed_in_as(monkeypatch: pytest.MonkeyPatch, user_id: str) -> dict[str, str]:
    def verify(token: str) -> dict[str, Any]:
        if token != "good":
            raise jwt.InvalidTokenError("bad")
        return {"sub": user_id}

    monkeypatch.setattr(auth, "verify", verify)
    return {"Authorization": "Bearer good"}


async def test_no_or_bad_token_is_401(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert (await api.get("/v1/crm/me")).status_code == 401
    signed_in_as(monkeypatch, str(uuid.uuid4()))
    r = await api.get("/v1/crm/me", headers={"Authorization": "Bearer bad"})
    assert r.status_code == 401 and r.json()["detail"].startswith("Your sign-in has expired")


@needs_db
async def test_a_valid_login_without_an_approved_profile_has_no_access(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = await api.get("/v1/crm/me", headers=signed_in_as(monkeypatch, str(uuid.uuid4())))
    assert r.status_code == 403 and r.json()["detail"] == auth.NO_ACCESS


@needs_db
async def test_bb_admin_sees_every_active_clinic(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        """select p.id from app.profiles p join app.user_clinics u on u.user_id = p.id
           where u.role = 'bb_admin' and u.active and p.active limit 1"""
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    r = await api.get("/v1/crm/me", headers=signed_in_as(monkeypatch, str(admin)))
    assert r.status_code == 200
    me = r.json()
    assert me["bb_admin"] and me["role_label"] == "Super Admin"
    ids = [c["id"] for c in me["clinics"]]
    assert "CL01" in ids and "CL99" not in ids  # the test clinic is never listed
    assert all(c["role"] == "bb_admin" for c in me["clinics"])


@pytest.mark.parametrize(
    ("name", "want"), [("Mohammed Abdul Abid", "MA"), ("Priya", "P"), ("Dr Sandeep Mahapatra", "SM")]
)
def test_initials(name: str, want: str) -> None:
    assert initials(name) == want


@needs_db
async def test_dashboard_returns_the_numbers(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    admin = await (await get_pool()).fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    r = await api.get("/v1/crm/dashboard?clinic=CL01&days=7", headers=headers)
    assert r.status_code == 200
    d = r.json()
    assert [f["key"] for f in d["funnel"]] == ["new", "follow_up", "booked", "visited", "lost", "invalid"]
    assert d["new_leads"] >= 0 and isinstance(d["today"], list)
    assert (await api.get("/v1/crm/dashboard?clinic=bad", headers=headers)).status_code == 422


@needs_db
async def test_dashboard_needs_access_to_the_clinic(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = await get_pool()
    row = await pool.fetchrow(
        """select u.user_id, c.id from app.user_clinics u join app.profiles p on p.id = u.user_id
           cross join app.clinics c
           where u.active and p.active and u.role <> 'bb_admin' and c.id not in
             (select clinic_id from app.user_clinics where user_id = u.user_id)
             and u.user_id not in  -- a Super Admin anywhere has every clinic
               (select user_id from app.user_clinics where role = 'bb_admin' and active) limit 1"""
    )
    if row is None:
        pytest.skip("no staff member without access to some clinic")
    r = await api.get(f"/v1/crm/dashboard?clinic={row[1]}", headers=signed_in_as(monkeypatch, str(row[0])))
    assert r.status_code == 403


@needs_db
async def test_leads_list_and_one_lead(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    r = await api.get("/v1/crm/leads?clinic=CL01&limit=5", headers=headers)
    assert r.status_code == 200
    d = r.json()
    assert [s["key"] for s in d["stages"]][0] == "new" and len(d["items"]) <= 5
    assert d["total"] == sum(s["count"] for s in d["stages"])
    assert (await api.get("/v1/crm/leads/NOPE-0", headers=headers)).status_code == 404
    none = (await api.get("/v1/crm/leads?clinic=CL01&from=2020-01-01&to=2020-01-02", headers=headers)).json()
    assert none["total"] == 0 and none["items"] == []
    if d["items"]:
        one = (await api.get(f"/v1/crm/leads/{d['items'][0]['code']}", headers=headers)).json()
        assert one["code"] == d["items"][0]["code"] and isinstance(one["events"], list)


@needs_db
async def test_leads_search_by_phone_with_spaces_and_by_treatment(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    lead = await pool.fetchrow(
        """select lead_code, phone_e164, treatment from app.leads where clinic_id = 'CL01'
           and deleted_at is null and phone_e164 like '+91%' and treatment is not null limit 1"""
    )
    if admin is None or lead is None:
        pytest.skip("no Super Admin, or no lead with a phone and treatment, in this database")
    headers = signed_in_as(monkeypatch, str(admin))

    async def search(q: str) -> dict[str, Any]:
        r = await api.get("/v1/crm/leads", params={"clinic": "CL01", "q": q, "limit": 200}, headers=headers)
        assert r.status_code == 200
        found: dict[str, Any] = r.json()
        return found

    phone = lead["phone_e164"]
    spaced = await search(f"{phone[:3]} {phone[3:8]}-{phone[8:]}")  # as staff may type it
    assert [i["code"] for i in spaced["items"]] == [lead["lead_code"]]
    assert (await search(lead["treatment"].upper()))["total"] >= 1
    assert (await search("no such lead or treatment xyz"))["total"] == 0
    # Typed characters are plain text: none of these may match every lead, or fail.
    for odd in ("-", "- -", "%", "_", "\\", "[(", "o'brien"):
        assert (await search(odd))["total"] == 0, odd


@needs_db
async def test_lead_stage_owner_note_and_call(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    lead = await pool.fetchrow(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Test Lead', '+919000000001', 'manual') returning id, lead_code"""
    )
    code = lead["lead_code"]
    added = await pool.execute(  # the admin takes leads in the test clinic during this test only
        """insert into app.user_clinics (user_id, clinic_id, role) values ($1, 'CL99', 'front_desk')
           on conflict do nothing""",
        admin,
    )
    try:
        r = await api.patch(f"/v1/crm/leads/{code}", json={"stage": "lost"}, headers=headers)
        assert r.status_code == 422  # Lost needs a reason
        r = await api.patch(
            f"/v1/crm/leads/{code}", json={"stage": "lost", "stage_reason": "price"}, headers=headers
        )
        assert r.status_code == 200 and r.json()["stage"] == "lost" and r.json()["stage_reason"] == "price"
        r = await api.patch(f"/v1/crm/leads/{code}", json={"assigned_to": str(admin)}, headers=headers)
        assert r.json()["assigned"]
        await api.post(f"/v1/crm/leads/{code}/notes", json={"text": "Prefers evening"}, headers=headers)
        r = await api.post(f"/v1/crm/leads/{code}/calls", json={"outcome": "no_answer"}, headers=headers)
        kinds = [e["kind"] for e in r.json()["events"]]
        assert kinds[:4] == ["call", "note", "assigned", "stage_change"]
        assert r.json()["events"][3]["by"]  # who did it
    finally:
        await pool.execute("select app.delete_patient_data($1)", lead["id"])
        if added.endswith("1"):
            await pool.execute(
                "delete from app.user_clinics where user_id = $1 and clinic_id = 'CL99'", admin
            )


def test_import_phone_reads_what_a_spreadsheet_holds() -> None:
    for held in (
        "9876543210",
        "98765 43210",
        "+91 98765 43210",
        "+919876543210",
        "919876543210",
        "09876543210",
    ):
        assert _import_phone(held) == "+91 9876543210", held
    assert _import_phone("+971 501234567") == "+971 501234567"
    for bad in ("", "12345", "9.88E+11", "abc", "+971501234567"):
        assert _import_phone(bad) is None, bad


def test_export_cells_stay_text_in_a_spreadsheet() -> None:
    assert cell("=HYPERLINK(1)") == "'=HYPERLINK(1)" and cell("@x") == "'@x" and cell("-1") == "'-1"
    assert cell("Asha Rao") == "Asha Rao" and cell(None) == ""
    assert export_phone("+919876543210", "+91") == "+91 9876543210" and export_phone(None, None) == ""


@needs_db
async def test_imported_leads_are_told_in_turn_only_with_a_template_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []

    async def quiet(clinic: str, purpose: str, phone: str, data: dict[str, Any]) -> None:
        sent.append(phone)

    monkeypatch.setattr(whatsapp, "_quiet", quiet)
    items: list[tuple[str, dict[str, Any]]] = [("+91 9000000001", {}), ("+91 9000000002", {})]

    async def off(clinic: str, purpose: str) -> bool:
        return False

    monkeypatch.setattr(whatsapp, "template_on", off)
    whatsapp.notify_each("CL99", "imported_lead", items)
    await asyncio.gather(*list(whatsapp._running))
    assert sent == []  # no template on: nobody is messaged

    async def on(clinic: str, purpose: str) -> bool:
        return True

    monkeypatch.setattr(whatsapp, "template_on", on)
    whatsapp.notify_each("CL99", "imported_lead", items)
    await asyncio.gather(*list(whatsapp._running))
    assert sent == ["+91 9000000001", "+91 9000000002"]
    assert "imported_lead" in whatsapp.PURPOSES


def test_only_managers_export_and_import() -> None:
    def person(role: str) -> Staff:
        return Staff(id="u", email="", name="", bb_admin=False, roles={"CL99": role})

    bulk_access(person("clinic_manager"), "CL99")
    for role in ("front_desk", "doctor"):
        with pytest.raises(HTTPException) as refused:
            bulk_access(person(role), "CL99")
        assert refused.value.status_code == 403
    with pytest.raises(HTTPException):
        bulk_access(person("clinic_manager"), "CL98")  # another clinic


@needs_db
async def test_import_export_and_pages_newest_first(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    hooks: list[tuple[str, str, list[dict[str, Any]]]] = []
    messages: list[tuple[str, str, list[tuple[str, dict[str, Any]]]]] = []
    monkeypatch.setattr(webhooks, "emit_each", lambda *a: hooks.append(a))  # nobody is really contacted
    monkeypatch.setattr(whatsapp, "notify_each", lambda *a: messages.append(a))
    phones = [f"+91900000{i:04d}" for i in range(7000, 7005)]
    await pool.execute("delete from app.lead_events where lead_id in (select id from app.leads"
                       " where clinic_id = 'CL99' and phone_e164 = any($1::text[]))", phones)  # fmt: skip
    await pool.execute(
        "delete from app.leads where clinic_id = 'CL99' and phone_e164 = any($1::text[])", phones
    )
    existing = await pool.fetchrow(
        """insert into app.leads (clinic_id, full_name, phone_e164, source)
           values ('CL99', 'Old Lead', $1, 'manual') returning id, lead_code""",
        phones[0],
    )
    rows = [
        {"row": 2, "name": "New  One", "phone": "90000 07001", "treatment": "PRP", "source": "Meta Ads"},
        {"row": 3, "name": "=Two", "phone": "+919000007002", "email": "TWO@example.com"},
        {"row": 4, "name": "Same File", "phone": "9000007001"},  # line 2's number
        {"row": 5, "name": "Old Again", "phone": "9000007000"},  # already a lead
        {"row": 6, "name": "No Phone", "phone": "123"},
        {"row": 7, "name": "X", "phone": "9000007003"},
        {"row": 8, "name": "Bad Mail", "phone": "9000007004", "email": "nope"},
    ]
    url = "/v1/crm/leads/import"
    try:
        check = (await api.post(url, json={"clinic": "CL99", "rows": rows}, headers=headers)).json()
        assert check["ready"] == 2 and check["added"] == 0
        assert not hooks and not messages  # the check alone tells nobody
        assert {d["row"] for d in check["duplicates"]} == {4, 5}
        assert {i["row"] for i in check["invalid"]} == {6, 7, 8}
        assert await pool.fetchval(
            "select count(*) from app.leads where clinic_id = 'CL99' and phone_e164 = any($1::text[])", phones
        ) == 1  # fmt: skip

        done = (
            await api.post(url, json={"clinic": "CL99", "rows": rows, "confirm": True}, headers=headers)
        ).json()
        assert done["added"] == 2
        again = (
            await api.post(url, json={"clinic": "CL99", "rows": rows, "confirm": True}, headers=headers)
        ).json()
        assert again["added"] == 0 and again["ready"] == 0  # importing the same file twice adds nothing
        assert len(hooks) == 1 and len(messages) == 1  # and tells nobody twice
        assert hooks[0][:2] == ("CL99", "lead_new") and messages[0][:2] == ("CL99", "imported_lead")
        told = {phone: data for phone, data in messages[0][2]}
        assert set(told) == {"+91 9000007001", "+91 9000007002"}  # only the two new leads
        assert told["+91 9000007001"]["name"] == "New One" and told["+91 9000007001"]["treatment"] == "PRP"
        assert {h["phone"] for h in hooks[0][2]} == {"+919000007001", "+919000007002"}

        one = await pool.fetchrow(
            "select * from app.leads where clinic_id = 'CL99' and phone_e164 = $1", phones[1]
        )
        assert one["full_name"] == "New One" and one["treatment"] == "PRP" and one["source"] == "meta_ads"
        assert one["stage"] == "new" and one["assigned_to"] is None
        kinds = await pool.fetch("select kind, data from app.lead_events where lead_id = $1", one["id"])
        assert [k["kind"] for k in kinds] == ["contact"] and "imported" in kinds[0]["data"]

        listed = (await api.get("/v1/crm/leads?clinic=CL99&limit=2", headers=headers)).json()
        assert len(listed["items"]) == 2 and listed["total"] >= 3
        codes = {i["code"] for i in listed["items"]}
        assert existing["lead_code"] not in codes  # the imported leads are newer, so they come first
        second = (await api.get("/v1/crm/leads?clinic=CL99&limit=2&offset=2", headers=headers)).json()
        assert not codes & {i["code"] for i in second["items"]}  # pages never repeat a lead

        r = await api.get("/v1/crm/leads/export", params={"clinic": "CL99", "q": "7002"}, headers=headers)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        sheet = list(csv.reader(io.StringIO(r.text.lstrip("\ufeff"))))
        assert sheet[0][:3] == ["Code", "Name", "Phone"] and len(sheet) == 2
        assert sheet[1][1] == "'=Two" and sheet[1][2] == "+91 9000007002" and sheet[1][3] == "two@example.com"

        by_treatment = await api.get(
            "/v1/crm/leads", params={"clinic": "CL99", "treatment": "PRP"}, headers=headers
        )
        assert {i["treatment"] for i in by_treatment.json()["items"]} == {"PRP"}
        assert "PRP" in by_treatment.json()["treatments"]
        assert one["lead_code"] in {i["code"] for i in by_treatment.json()["items"]}
        file = await api.get(
            "/v1/crm/leads/export", params={"clinic": "CL99", "treatment": "PRP"}, headers=headers
        )
        assert one["lead_code"] in file.text and existing["lead_code"] not in file.text

        other = await pool.fetchval(
            "select lead_code from app.leads where clinic_id <> 'CL99' and deleted_at is null limit 1"
        )
        picked = await api.post(
            "/v1/crm/leads/export",
            json={"clinic": "CL99", "codes": [one["lead_code"], *([other] if other else [])]},
            headers=headers,
        )
        rows_out = list(csv.reader(io.StringIO(picked.text.lstrip("\ufeff"))))
        assert [r[0] for r in rows_out[1:]] == [one["lead_code"]]  # only what was ticked, this clinic only
        none = await api.post("/v1/crm/leads/export", json={"clinic": "CL99", "codes": []}, headers=headers)
        assert none.status_code == 422
    finally:
        await pool.execute("delete from app.lead_events where lead_id in (select id from app.leads"
                           " where clinic_id = 'CL99' and phone_e164 = any($1::text[]))", phones)  # fmt: skip
        await pool.execute(
            "delete from app.leads where clinic_id = 'CL99' and phone_e164 = any($1::text[])", phones
        )


@needs_db
async def test_add_lead_and_duplicate_phone(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no Super Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    body = {
        "clinic": "CL99",
        "name": "Walk  In",
        "phone": "9000000002",
        "source": "manual",
        "note": "Walk-in",
    }
    assert (
        await api.post("/v1/crm/leads", json=body | {"phone": "12345"}, headers=headers)
    ).status_code == 422
    r = await api.post("/v1/crm/leads", json=body, headers=headers)
    assert r.status_code == 201
    lead = r.json()
    try:
        assert lead["name"] == "Walk In" and lead["phone"] == "+919000000002" and lead["notes"] == "Walk-in"
        assert lead["events"][0]["kind"] == "contact"
        dup = await api.post("/v1/crm/leads", json=body, headers=headers)
        assert dup.status_code == 409 and lead["code"] in dup.json()["detail"]
        opts = await api.get("/v1/crm/lead-options?clinic=CL01", headers=headers)
        assert "Hair Transplant for Men" in opts.json()["treatments"]
    finally:
        lead_id = await pool.fetchval("select id from app.leads where lead_code = $1", lead["code"])
        await pool.execute("select app.delete_patient_data($1)", lead_id)
