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


@needs_db
async def test_test_chat_runs_the_draft(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    url = "/v1/crm/console/CL01/flow/test"  # reads the draft only; nothing is saved
    r = (await api.post(url, json={}, headers=headers)).json()
    assert r["at"] == "opening" and r["messages"][0]["buttons"]
    nxt = (await api.post(url, json={"state": r["state"], "tap": "m2"}, headers=headers)).json()
    assert nxt["at"] != "opening" and nxt["messages"]


@needs_db
async def test_test_leads_go_to_cl99_and_are_deleted(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.v1.crm_console import _save_test_lead
    from app.crm.auth import Staff

    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    user = Staff(id=str(admin), email="", name="", bb_admin=True, roles={})
    lead = {
        "type": "book",
        "block": "book",
        "name": "Test Asha",
        "phone": "+91 9000000099",
        "date": "2026-11-02",
    }
    saved = await _save_test_lead(user, lead, "desktop")
    assert saved["clinic"] == "CL99" and saved["code"].startswith("CL99")
    again = await _save_test_lead(user, lead, "desktop")  # the same phone: one lead, two requests
    assert again["code"] == saved["code"]
    row = await pool.fetchrow(
        """select l.page_url, count(r.id) n from app.leads l join app.requests r on r.lead_id = l.id
           where l.lead_code = $1 group by l.page_url""",
        saved["code"],
    )
    assert row["page_url"] == "crm:test-chat" and row["n"] == 2
    assert (await _save_test_lead(user, {"type": "callback", "name": "No contact"}, "desktop"))["error"]
    r = await api.delete("/v1/crm/console/CL01/flow/test-leads", headers=headers)
    assert r.status_code == 200 and r.json()["deleted"] >= 1
    assert await pool.fetchval("select count(*) from app.leads where lead_code = $1", saved["code"]) == 0


def test_phrases_follow_their_buttons() -> None:
    p1 = {"id": "p1", "target": "opening:m1", "text": "I want to book"}
    gone = {"id": "p2", "target": "opening:m9", "text": "old button"}
    twice = {"id": "p3", "target": "opening:m1", "text": "i want to BOOK!"}
    saved = normalise({"nodes": [OPENING], "phrases": [p1, gone, twice]})
    assert [p["id"] for p in saved["phrases"]] == ["p1"] and saved["phrases"][0]["status"] == "pending"
    two = OPENING | {"settings": {"buttons": [{"id": "m1", "label": "Book"}, {"id": "m2", "label": "Call"}]}}
    with pytest.raises(FlowError, match="already leads to"):
        normalise({"nodes": [two], "phrases": [p1, twice | {"target": "opening:m2"}]})


@needs_db
async def test_only_the_approve_action_approves_phrases(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    headers = signed_in_as(monkeypatch, str(admin))
    url = "/v1/crm/console/CL99"
    sneaky = {"id": "p1", "target": "opening:m1", "text": "I want to book", "status": "approved"}
    flow = {"nodes": [OPENING, BOOK], "edges": [{"source": "opening", "exit": "m1", "target": "book"}]}
    await pool.execute("delete from app.clinic_settings where clinic_id = 'CL99'")
    try:
        r = await api.put(f"{url}/settings/flow", json=flow | {"phrases": [sneaky]}, headers=headers)
        assert r.json()["draft"]["flow"]["phrases"][0]["status"] == "pending"  # a save never approves
        r = await api.post(f"{url}/flow/phrases/approve", json={"ids": ["p1"]}, headers=headers)
        approved = r.json()["draft"]["flow"]["phrases"][0]
        assert approved["status"] == "approved" and approved["approved_by"] == str(admin)
        r = await api.put(f"{url}/settings/flow", json=flow | {"phrases": [approved]}, headers=headers)
        assert r.json()["draft"]["flow"]["phrases"][0]["status"] == "approved"  # unchanged: kept
        edited = approved | {"text": "I want to book now"}
        r = await api.put(f"{url}/settings/flow", json=flow | {"phrases": [edited]}, headers=headers)
        assert r.json()["draft"]["flow"]["phrases"][0]["status"] == "pending"  # edited: approve again
    finally:
        await pool.execute("delete from app.clinic_settings where clinic_id = 'CL99'")


@needs_db
async def test_test_chat_reads_the_knowledge_base_and_appointments(api: AsyncClient) -> None:
    from app.api.v1.crm_console import _kb_answer, _save_test_lead, _upcoming
    from app.crm.auth import Staff

    pool = await get_pool()
    admin = await pool.fetchval(
        "select user_id from app.user_clinics where role = 'bb_admin' and active limit 1"
    )
    if admin is None:
        pytest.skip("no BB Admin in this database")
    assert "10:00 AM" in (await _kb_answer("CL01", "what are your clinic timings") or "")
    user = Staff(id=str(admin), email="", name="", bb_admin=True, roles={})
    saved = await _save_test_lead(
        user, {"type": "book", "name": "Test Appt", "phone": "+91 9000000098"}, "desktop"
    )
    try:
        lead = await pool.fetchval("select id from app.leads where lead_code = $1", saved["code"])
        await pool.execute(
            """insert into app.appointments (clinic_id, lead_id, type, preferred_date)
               values ('CL99', $1, 'in_clinic', current_date + 1)""",
            lead,
        )
        [line] = await _upcoming("CL99", "90000 00098")
        assert "time to be confirmed" in line and line.endswith("in clinic · pending")
        assert await _upcoming("CL99", "9000000097") == []
    finally:
        await pool.execute("delete from app.leads where lead_code = $1", saved["code"])


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


def test_doctor_card_buttons() -> None:
    card: dict[str, Any] = {"doctor": "Dr. A", "book_label": "Book with {doctor}", "treatments_label": "View"}
    doc: dict[str, Any] = {"id": "doc", "type": "doctor_card", "settings": card}
    more = card | {"treatments": ["FUE"], "buttons": [{"id": "b1", "label": "Ask a question"}]}
    lines = [{"source": "doc", "exit": e, "target": "book"} for e in ("book", "b1")]
    saved = normalise({"nodes": [OPENING, doc | {"settings": more}, BOOK], "edges": lines})
    assert saved["edges"] == lines  # Book with and its own buttons each have a line; treatments open cards
    with pytest.raises(FlowError, match="at least one treatment"):
        normalise({"nodes": [OPENING, doc | {"settings": card}]})


def test_information_blocks() -> None:
    kb = {"id": "kb", "type": "knowledge", "settings": {}}
    lines = [{"source": "kb", "exit": e, "target": "book"} for e in ("answered", "not_found")]
    assert normalise({"nodes": [OPENING, kb, BOOK], "edges": lines})["edges"] == lines
    faq: dict[str, Any] = {"id": "faq", "type": "faq", "settings": {"items": []}}
    with pytest.raises(FlowError):
        normalise({"nodes": [OPENING, faq]})  # an FAQ list needs a question
    same = [{"question": "Is it painful?", "answer": "No."}] * 2
    with pytest.raises(FlowError, match="same"):
        normalise({"nodes": [OPENING, faq | {"settings": {"items": same}}]})
    for t in ("location", "reviews"):
        normalise({"nodes": [OPENING, {"id": t, "type": t, "settings": {}}]})


def test_check_open_and_goto_blocks() -> None:
    blocks = [
        {"id": "rep", "type": "callback", "settings": {}},
        {"id": "chk", "type": "check_appointment", "settings": {}},
        {"id": "open", "type": "clinic_open", "settings": {}},
        {"id": "go", "type": "goto", "settings": {"target": "chk"}},
    ]
    exits = [("opening", "m1", "open"), ("open", "open", "rep"), ("open", "closed", "go")]
    lines = [{"source": s, "exit": e, "target": t} for s, e, t in exits]
    lines += [{"source": "chk", "exit": e, "target": "rep"} for e in ("found", "not_found")]
    saved = normalise({"nodes": [OPENING, *blocks], "edges": lines})
    assert check(saved) == []  # the Go to reaches 'chk' with no line
    otp = {"id": "chk", "type": "check_appointment", "settings": {"otp": True}}
    failed = [{"source": "chk", "exit": "code_failed", "target": "opening"}]
    assert normalise({"nodes": [OPENING, otp], "edges": failed})["edges"] == failed  # OTP adds code_failed
    with pytest.raises(FlowError, match="does not exist"):
        normalise({"nodes": [OPENING, {"id": "go", "type": "goto", "settings": {"target": "nope"}}]})
    with pytest.raises(FlowError, match="itself"):
        normalise({"nodes": [OPENING, {"id": "go", "type": "goto", "settings": {"target": "go"}}]})


def test_condition_block() -> None:
    def cond(*tests: dict[str, Any]) -> dict[str, Any]:
        branch = {"id": "c1", "label": "Weekend", "tests": list(tests)}
        return {"id": "if", "type": "condition", "settings": {"branches": [branch]}}

    weekend = {"subject": "weekday", "op": "is", "value": "sat,sun"}
    lines = [{"source": "if", "exit": e, "target": "book"} for e in ("c1", "else")]
    assert normalise({"nodes": [OPENING, cond(weekend), BOOK], "edges": lines})["edges"] == lines
    bad = [
        ({"subject": "weekday", "op": "is", "value": "funday"}, "Days are"),
        ({"subject": "time", "op": "after", "value": "7pm"}, "13:30"),
        ({"subject": "time", "op": "is", "value": "10:00"}, "cannot be used"),
        ({"subject": "device", "op": "is", "value": "tablet"}, "mobile or desktop"),
        ({"subject": "field", "field": "nope", "op": "empty"}, "field that does not exist"),
        ({"subject": "field", "field": "treatment", "op": "is"}, "needs a value"),
    ]
    for test, words in bad:
        with pytest.raises(FlowError, match=words):
            normalise({"nodes": [OPENING, cond(test)]})


def test_no_reply_and_global_triggers() -> None:
    saved = normalise({"nodes": [OPENING]})
    assert saved["globals"]["no_reply"]["minutes"] == 3  # on by default
    sos = {"id": "sos", "type": "emergency", "settings": {"text": "Call 108."}}
    globals_ = {"triggers": [{"kind": "emergency", "target": "sos"}], "no_reply": {"minutes": 5}}
    saved = normalise({"nodes": [OPENING, sos], "globals": globals_})
    assert [p for p in check(saved) if p.node == "sos"] == []  # reached from anywhere, no warning
    with pytest.raises(FlowError, match="needs a block"):
        normalise({"nodes": [OPENING], "globals": {"triggers": [{"kind": "talk_to_person"}]}})
    with pytest.raises(FlowError, match="set once"):
        normalise({"nodes": [OPENING], "globals": {"triggers": [{"kind": "main_menu"}] * 2}})
    with pytest.raises(FlowError):
        normalise({"nodes": [OPENING], "globals": {"no_reply": {"minutes": 99}}})


def test_emergency_call_buttons() -> None:
    calls = [
        {"id": "b1", "label": "Call 108", "action": "call", "value": "108"},
        {"id": "b2", "label": "Call the clinic", "action": "call", "value": ""},  # Contact & hours
    ]
    sos = {"id": "sos", "type": "emergency", "settings": {"text": "Call 108.", "buttons": calls}}
    assert check(normalise({"nodes": [OPENING | {"settings": {"buttons": []}}, sos]}))[0].level == "warning"
    wrong = [calls[0] | {"value": "call me"}]
    with pytest.raises(FlowError, match="not valid"):
        normalise({"nodes": [OPENING, sos | {"settings": {"text": "Call 108.", "buttons": wrong}}]})


def test_media_carousel_and_typing_delay() -> None:
    pic = {"id": "pic", "type": "media", "typing": 1.5, "settings": {"url": "https://x.in/a.jpg"}}
    line = [{"source": "pic", "exit": "next", "target": "book"}]
    saved = normalise({"nodes": [OPENING, pic, BOOK], "edges": line})
    assert saved["nodes"][1]["typing"] == 1.5 and saved["edges"] == line
    with pytest.raises(ValueError):  # the API answers 422 "nodes → 1 → typing: ..."
        normalise({"nodes": [OPENING, pic | {"typing": 9}]})
    book = {"id": "b1", "label": "Book", "action": "book", "value": "FUE"}
    card = {"title": "FUE", "buttons": [book]}
    car = {"id": "car", "type": "carousel", "settings": {"source": "custom", "cards": [card, card]}}
    normalise({"nodes": [OPENING, car]})
    normalise({"nodes": [OPENING, car | {"settings": {"category": "Hair transplant"}}]})  # live treatments
    with pytest.raises(FlowError, match="at least 2 cards"):
        normalise({"nodes": [OPENING, car | {"settings": {"source": "custom", "cards": [card]}}]})
    plain = card | {"buttons": [{"id": "b1", "label": "More"}]}
    with pytest.raises(FlowError, match="job of its own"):
        normalise({"nodes": [OPENING, car | {"settings": {"source": "custom", "cards": [plain, card]}}]})


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
