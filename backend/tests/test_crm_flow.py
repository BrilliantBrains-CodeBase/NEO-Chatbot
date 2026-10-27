"""Workflow canvas (app.crm.flow): the flow format, its checks and the import of today's chat."""

from typing import Any

import pytest
from httpx import AsyncClient

from app.chat.content import content
from app.core.db import get_pool
from app.crm.flow import FlowError, check, import_content, normalise
from tests.test_crm_auth import api, needs_db, signed_in_as

__all__ = ["api"]  # the client fixture

OPENING = {"id": "opening", "type": "opening", "settings": {"buttons": [{"id": "m1", "label": "Book"}]}}
BOOK = {"id": "book", "type": "book", "settings": {"fields": ["name", "phone"]}}


def test_cl01_imports_completely_with_no_problems() -> None:
    flow = import_content(content("CL01") or {})
    types = [n["type"] for n in flow["nodes"]]
    assert types.count("opening") == 1 and "treatment_card" not in types and "link" not in types
    assert {"book", "online", "cancel", "reschedule", "callback", "emergency"} <= set(types)
    # Simple buttons do their job by themselves (no line, no extra block): the 18 treatments, links, WhatsApp.
    actions = [b["action"] for n in flow["nodes"] for b in n["settings"].get("buttons", [])]
    assert "whatsapp" in actions and "link" in actions
    # Treatment lists take their treatments live from Clinic info → Services, by category.
    lists = {n["settings"]["category"] for n in flow["nodes"] if n["type"] == "treatment_list"}
    assert lists == {"Hair transplant", "Hair fall & scalp"}
    assert len(flow["nodes"]) < 35
    assert {n["settings"]["topic"] for n in flow["nodes"] if n["type"] == "typed"} >= {"cost", "clinic"}
    assert check(flow) == []  # every button leads somewhere, every block is reachable
    assert all(n["x"] >= 0 and n["y"] >= 0 for n in flow["nodes"])


def test_structure_errors_refuse_the_save() -> None:
    line = {"source": "opening", "exit": "m1", "target": "book"}
    assert normalise({"nodes": [OPENING, BOOK], "edges": [line]})["edges"] == [line]
    cases: list[tuple[dict[str, Any], str]] = [
        ({"nodes": [OPENING, OPENING | {"id": "opening2"}]}, "exactly one Opening"),
        ({"nodes": [OPENING, BOOK | {"id": "opening"}]}, "same id"),
        ({"nodes": [OPENING, BOOK], "edges": [line | {"exit": "m9"}]}, "no exit"),
        ({"nodes": [OPENING, BOOK], "edges": [line, line]}, "same exit"),
        ({"nodes": [OPENING], "edges": [line]}, "does not exist"),
        ({"nodes": [OPENING, BOOK | {"settings": {"mode": "chat"}}]}, "Block 'book'"),
    ]
    for flow, words in cases:
        with pytest.raises(FlowError, match=words):
            normalise(flow)


def test_loose_ends_are_errors_and_unreachable_blocks_warnings() -> None:
    problems = check({"nodes": [OPENING, BOOK], "edges": []})
    assert [(p.level, p.node) for p in problems] == [("error", "opening"), ("warning", "book")]
    hidden = OPENING | {"settings": {"buttons": [{"id": "m1", "label": "Book", "visible": False}]}}
    assert [p.level for p in check({"nodes": [hidden], "edges": []})] == []  # a hidden button needs no line


@needs_db
async def test_publish_is_blocked_by_a_loose_end(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    url = "/v1/crm/console/CL99"
    await pool.execute("delete from app.clinic_settings where clinic_id = 'CL99'")
    try:
        r = await api.put(
            f"{url}/settings/flow", json={"nodes": [OPENING, BOOK], "edges": []}, headers=headers
        )
        assert r.status_code == 200 and r.json()["flow_problems"][0]["level"] == "error"
        p = await api.post(f"{url}/publish", headers=headers)
        assert p.status_code == 409 and "leads nowhere" in p.json()["detail"]
        bad = await api.put(f"{url}/settings/flow", json={"nodes": [BOOK]}, headers=headers)
        assert bad.status_code == 422 and "Opening" in bad.json()["detail"]
    finally:
        await pool.execute("delete from app.clinic_settings where clinic_id = 'CL99'")


def test_blocks_can_be_off_or_scheduled() -> None:
    line = {"source": "opening", "exit": "m1", "target": "book"}
    off = BOOK | {"enabled": False, "show_from": "2026-11-01", "show_until": "2026-11-30"}
    saved = normalise({"nodes": [OPENING, off], "edges": [line]})
    assert saved["nodes"][1]["show_from"] == "2026-11-01"  # stored as text (JSON)
    assert [(p.level, p.node) for p in check(saved)] == [("warning", "book")]
    with pytest.raises(FlowError, match="ends before it starts"):
        normalise({"nodes": [OPENING, BOOK | {"show_from": "2026-11-10", "show_until": "2026-11-01"}]})
    with pytest.raises(FlowError, match="Opening block cannot be off"):
        normalise({"nodes": [OPENING | {"enabled": False}]})


def test_appointment_block_settings() -> None:
    settings = {"fields": ["name", "phone"], "questions": {"name": "Your full name, please?"}, "retries": 1}
    saved = normalise({"nodes": [OPENING, BOOK | {"settings": settings}]})["nodes"][1]["settings"]
    assert saved["questions"] == {"name": "Your full name, please?"} and saved["consent"] is True
    with pytest.raises(FlowError, match="Question 'age'"):
        normalise({"nodes": [OPENING, BOOK | {"settings": {"questions": {"age": "How old?"}}}]})
    with pytest.raises(FlowError):
        normalise({"nodes": [OPENING, BOOK | {"settings": {"retries": 9}}]})


def test_question_block_kinds_and_exits() -> None:
    base: dict[str, Any] = {"question": "Have you had a transplant before?"}

    def ask(**settings: Any) -> dict[str, Any]:
        return {"id": "q1", "type": "question", "settings": base | settings}

    line_yes = {"source": "q1", "exit": "yes", "target": "book"}
    saved = normalise({"nodes": [OPENING, ask(kind="yes_no", field="reason"), BOOK], "edges": [line_yes]})
    assert saved["edges"] == [line_yes]  # yes / no are its two exits
    with pytest.raises(FlowError, match="at least 2 options"):
        normalise({"nodes": [OPENING, ask(kind="choice", field="reason", options=[{"label": "A"}])]})
    with pytest.raises(FlowError, match="field that does not exist"):
        normalise({"nodes": [OPENING, ask(field="nope")]})


def test_fields_set_field_and_unknown_fields_in_messages() -> None:
    welcome = OPENING | {"settings": {"welcome": "Hi {name}, about {interest}?", "buttons": []}}
    set_it = {
        "id": "set-1",
        "type": "set_field",
        "settings": {"field": "interest", "value": "Hair transplant"},
    }
    flow = {"nodes": [welcome, set_it], "fields": [{"key": "interest", "label": "Interest"}]}
    saved = normalise(flow)
    assert saved["fields"][0]["key"] == "interest"
    assert not [p for p in check(saved) if p.level == "error"]
    unknown = check(normalise(flow | {"fields": []} | {"nodes": [welcome]}))
    assert [p.message for p in unknown if p.level == "error"] == ["Uses {interest}, which is not a field."]
    with pytest.raises(FlowError, match="field that does not exist"):
        normalise(flow | {"fields": []})
    with pytest.raises(FlowError, match="own name"):
        normalise(flow | {"fields": [{"key": "name", "label": "Name"}]})
