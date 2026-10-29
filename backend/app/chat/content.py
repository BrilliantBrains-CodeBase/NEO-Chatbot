"""Clinic content (menus, fixed answers, treatments), read-only JSON in app/clinics.

CL01.json is exported from the approved Arya mock (frontend/widgets/mock/arya.ts), so the wording and
links are exactly the ones the widget tests check.
"""

import json
from functools import cache
from pathlib import Path
from typing import Any

DIR = Path(__file__).resolve().parent.parent / "clinics"


@cache
def content(clinic_id: str) -> dict[str, Any] | None:
    path = DIR / f"{clinic_id}.json"
    if not path.is_file():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


# ---------- Dashboard → Menu buttons ----------
# The chat runs on the clinic's file above, with its published Menu buttons laid over it: the welcome message,
# the main buttons and their sub-buttons. Each button keeps doing what the chat already does (book, the
# treatments, a page, a call, a link), so nothing else changes. The service loads the published menu before
# each message (refresh); live() is what the chat reads.
_menus: dict[str, tuple[str, dict[str, Any] | None]] = {}  # clinic -> (published menu JSON, content with it)
START = ("book", "online", "cancel", "reschedule", "callback")


def _tap(b: dict[str, Any]) -> dict[str, Any] | None:
    """A Dashboard button as the chat's own button (None: it cannot be shown)."""
    action, value = b.get("action", ""), str(b.get("value", ""))
    out: dict[str, Any] = {"label": b["label"]}
    if b.get("icon"):
        out["icon"] = b["icon"]
    if b.get("variant") in ("wa", "sos"):
        out["variant"] = b["variant"]
    if action in START:
        return out | ({"action": "callback", "value": value} if action == "callback" and value else
                      {"action": "start", "value": action})  # fmt: skip
    if action == "treatment" and value:
        return out | {"action": "treat", "value": value}
    if action == "treatments":
        return out | {"action": "go", "value": "treatments"}
    if action == "emergency":
        return out | {"action": "go", "value": "emergency", "variant": "sos"}
    if action == "page" and value:
        return out | {"action": "go", "value": value}
    if action == "call" and value:
        return out | {"href": "tel:" + value}
    if action in ("link", "whatsapp") and value.startswith("https://"):
        return out | {"href": value} | ({"variant": "wa"} if action == "whatsapp" else {})
    return None


def with_menu(base: dict[str, Any], menu: dict[str, Any]) -> dict[str, Any]:
    """The clinic's content with its published Menu buttons."""
    nodes = dict(base.get("nodes") or {})
    items = []
    for i, b in enumerate(x for x in menu.get("buttons", []) if x.get("visible", True)):
        if b.get("action") in ("submenu", "answer"):
            if b["action"] == "answer":  # the button's own text, then the Main menu link
                text, options = b.get("value", ""), []
            else:
                text = b.get("message") or "What would you like to do?"
                subs = [_sub(s, nodes, i) for s in b.get("sub", []) if s.get("visible", True)]
                options = [o for o in subs if o]
            nodes[f"m{i}"] = {
                "messages": [{"type": "text", "text": text}] if text else [],
                "ui": {"type": "chips", "main": True, "options": options},
                "input": {"mode": "text", "placeholder": "Type your question"},
            }
            item = {"label": b["label"], "action": "go", "value": f"m{i}"}
            items.append(item | ({"icon": b["icon"]} if b.get("icon") else {}) |
                         ({"variant": b["variant"]} if b.get("variant") else {}))  # fmt: skip
        elif tap := _tap(b):
            items.append(tap)
    out = {**base, "nodes": nodes}
    if menu.get("welcome"):
        out["greeting"] = menu["welcome"]
    if menu.get("fallback"):  # when no answer is found (with the call-back offer)
        out["fallback"] = menu["fallback"]
    shown = [f"{f['value']} {f['label']}".strip() for f in menu.get("figures", []) if f.get("value")]
    if menu.get("show_figures", True) and shown:  # under the welcome, e.g. "4.8★ Google rating"
        out["figures"] = " · ".join(shown)
    if items:
        out["menu"] = {**(base.get("menu") or {"type": "menu", "layout": "cards3"}), "items": items}
    return out


def _sub(s: dict[str, Any], nodes: dict[str, Any], i: int) -> dict[str, Any] | None:
    """A sub-button; an "answer" one gets its own page with its text."""
    if s.get("action") == "answer":
        key = f"m{i}_{len(nodes)}"
        nodes[key] = {
            "messages": [{"type": "text", "text": s.get("value") or s["label"]}],
            "ui": {"type": "chips", "main": True, "options": []},
            "input": {"mode": "text", "placeholder": "Type your question"},
        }
        return {"label": s["label"], "action": "go", "value": key}
    return _tap(s)


async def refresh(conn: Any, clinic: str) -> None:
    """Loads the clinic's published Menu buttons (call once per message, before live())."""
    saved = await conn.fetchval(
        "select published->'menu' from app.clinic_settings where clinic_id = $1", clinic
    )
    key = saved if isinstance(saved, str) else json.dumps(saved)
    if _menus.get(clinic, ("",))[0] == key:
        return
    base = content(clinic)
    menu = json.loads(saved) if isinstance(saved, str) else saved
    _menus[clinic] = (key, with_menu(base, menu) if base is not None and menu else None)


def live(clinic: str) -> dict[str, Any] | None:
    """What the chat runs on: the clinic's content with its published Menu buttons (after refresh())."""
    return _menus.get(clinic, ("", None))[1] or content(clinic)
