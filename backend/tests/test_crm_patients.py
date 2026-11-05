"""CRM Patients: everyone in a clinic with their visits, on temporary people in the test clinic (CL99)."""

from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.db import get_pool
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture


def _ago(days: int) -> date:
    return date.today() - timedelta(days=days)


@needs_db
async def test_patients_lists_everyone_with_filters_sort_and_pages(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    # name -> source, stage, campaign, consent, the days ago of each visit, no-shows, days ahead of a booking
    people: dict[str, tuple[str, str, str | None, bool, list[int], int, int | None]] = {
        "ZzPat Never": ("meta_ads", "new", "Diwali", False, [], 0, None),
        "ZzPat Once": ("chatbot", "booked", None, True, [10], 1, 5),
        "ZzPat Twice": ("google_ads", "visited", None, True, [40, 20], 0, None),
        "ZzPat Regular": ("chatbot", "visited", None, True, [90, 60, 3], 0, None),
        "ZzPat Gone": ("referral", "visited", None, True, [400, 300, 200], 0, None),
        "ZzPat ByHand": ("walk_in", "visited", None, False, [], 0, None),
    }
    ids: dict[str, Any] = {}
    try:
        for n, (name, (src, stage, camp, agreed, visits, missed, ahead)) in enumerate(people.items()):
            ids[name] = await pool.fetchval(
                """insert into app.leads (clinic_id, full_name, phone_e164, source, stage, campaign,
                     treatment, consent_at)
                   values ('CL99', $1, $2, $3, $4, $5, 'ZZ Treatment', case when $6 then now() end)
                   returning id""",
                name, f"+91900000{7200 + n}", src, stage, camp, agreed,
            )  # fmt: skip
            for status, days in [("visited", d) for d in visits] + [("no_show", 7)] * missed:
                await pool.execute(
                    """insert into app.appointments (clinic_id, lead_id, type, status, preferred_date,
                         confirmed_at)
                       values ('CL99', $1, 'in_clinic', $2, $3, now())""",
                    ids[name], status, _ago(days),
                )  # fmt: skip
            if ahead:
                await pool.execute(
                    """insert into app.appointments (clinic_id, lead_id, type, status, preferred_date)
                       values ('CL99', $1, 'in_clinic', 'pending', $2)""",
                    ids[name], _ago(-ahead),
                )  # fmt: skip

        async def got(**params: Any) -> dict[str, Any]:
            r = await api.get(
                "/v1/crm/patients", params={"clinic": "CL99", "q": "zzpat", **params}, headers=headers
            )
            assert r.status_code == 200, r.text
            body: dict[str, Any] = r.json()
            return body

        async def names(**params: Any) -> set[str]:
            return {i["name"].removeprefix("ZzPat ") for i in (await got(**params))["items"]}

        everyone = await got()
        assert everyone["total"] == 6  # visited or not, every status
        by = {i["name"]: i for i in everyone["items"]}
        assert by["ZzPat Never"]["activity"] == "never" and by["ZzPat Never"]["visits"] == 0
        assert by["ZzPat Once"]["activity"] == "new" and by["ZzPat Once"]["no_shows"] == 1
        assert by["ZzPat Once"]["next_visit"] and by["ZzPat Never"]["next_visit"] is None
        assert by["ZzPat Twice"]["activity"] == "returning"
        assert by["ZzPat Regular"]["activity"] == "regular" and by["ZzPat Regular"]["visits"] == 3
        assert by["ZzPat Gone"]["activity"] == "inactive"  # 3 visits, but the last was 200 days ago
        assert by["ZzPat ByHand"]["visits"] == 1  # moved to Visited by hand, with no appointment
        assert {c["key"]: c["count"] for c in everyone["activities"]} == {
            "never": 1, "new": 2, "returning": 1, "regular": 1, "inactive": 1,
        }  # fmt: skip

        assert await names(activity="never") == {"Never"}  # those to retarget
        assert await names(stage="booked") == {"Once"}
        assert await names(source="referral") == {"Gone"}
        assert await names(campaign="Diwali") == {"Never"}
        assert await names(consent="no") == {"Never", "ByHand"}
        assert await names(no_shows="yes") == {"Once"}
        assert await names(upcoming="yes") == {"Once"}
        assert await names(visits_min=2, visits_max=3) == {"Twice", "Regular", "Gone"}

        # The date range goes by the date chosen; someone without that date does not match.
        last_7 = {"from": _ago(6).isoformat(), "to": date.today().isoformat()}
        assert await names(date_field="last_visit", **last_7) == {"Regular"}
        assert await names(date_field="first_visit", to=_ago(350).isoformat()) == {"Gone"}
        assert len(await names(date_field="added", **last_7)) == 6
        assert await names(date_field="last_visit", **{"from": "2031-01-01"}) == set()

        # The tabs count the other filters, not themselves.
        counted = await got(activity="never", source="chatbot")
        assert counted["total"] == 0
        assert {c["key"]: c["count"] for c in counted["activities"]}["regular"] == 1

        # Sorting: no date goes last in both directions; pages do not repeat anyone.
        order = [i["name"] for i in (await got(sort="visits", direction="desc"))["items"]]
        assert set(order[:2]) == {"ZzPat Regular", "ZzPat Gone"} and order[-1] == "ZzPat Never"
        for way in ("asc", "desc"):
            shown = (await got(sort="last_visit", direction=way))["items"]
            assert all(i["last_visit"] is None for i in shown[-2:])
        pages = [(await got(sort="name", direction="asc", limit=2, offset=o))["items"] for o in (0, 2, 4)]
        assert [i["name"] for p in pages for i in p] == sorted(people, key=str.lower)

        for odd in ("-", "%", "_", "\\"):  # typed text is plain text, and never an error
            r = await api.get("/v1/crm/patients", params={"clinic": "CL99", "q": odd}, headers=headers)
            assert r.status_code == 200, odd
        bad = await api.get("/v1/crm/patients", params={"clinic": "CL99", "sort": "1;drop"}, headers=headers)
        assert bad.status_code == 422
    finally:
        made = list(ids.values())
        await pool.execute("delete from app.appointments where lead_id = any($1::uuid[])", made)
        await pool.execute("delete from app.lead_events where lead_id = any($1::uuid[])", made)
        await pool.execute("delete from app.leads where id = any($1::uuid[])", made)


async def test_patients_needs_a_sign_in(api: AsyncClient) -> None:
    assert (await api.get("/v1/crm/patients", params={"clinic": "CL99"})).status_code == 401
