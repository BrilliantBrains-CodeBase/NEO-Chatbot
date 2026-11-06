"""Who sees what (migration 0032): for each screen and role, hidden, view or edit. Super Admin always has edit
everywhere. The rules stack: BUILTIN (today's behaviour) ← BB's defaults for all clinics (app.platform) ← the
clinic's own changes (app.clinic_permissions). Only changes are stored.
"""

import json
from contextvars import ContextVar
from typing import Any, Literal

from fastapi import Request

Level = Literal["hidden", "view", "edit"]
LEVELS: tuple[Level, ...] = ("hidden", "view", "edit")
ROLES = ("clinic_manager", "front_desk", "doctor")

# key -> (label, group). CRM screens, then the Dashboard's tabs (lib/assistant.ts ids, as "dash_<id>").
CRM = {
    "dashboard": "Dashboard", "leads": "Leads", "inbox": "Inbox", "doctors": "Doctors",
    "appointments": "Appointments", "tasks": "Tasks", "patients": "Patients", "reports": "Reports",
    "team": "Team", "settings": "Settings",
}  # fmt: skip
DASHBOARD = {
    "overview": "Overview", "appearance": "Appearance", "templates": "Templates", "menu": "Menu buttons",
    "content": "Clinic info", "doctors": "Doctors", "ai": "Answers", "legal": "Legal",
    "unanswered": "Unanswered questions",
    "chats": "Chat transcripts", "quality": "Test & quality", "install": "Website install",
    "integrations": "Integrations", "security": "Login & security", "privacy": "Privacy & data",
    "activity": "Activity", "alerts": "Alerts", "versions": "Versions",
}  # fmt: skip
SCREENS: dict[str, tuple[str, str]] = (
    {k: (v, "CRM") for k, v in CRM.items()}
    | {"dash_open": ("Open the Chatbot settings", "Chatbot")}  # the whole chatbot console; its tabs below
    | {f"dash_{k}": (v, "Chatbot") for k, v in DASHBOARD.items()}
)

# Rows the "Who sees what" table leaves out: screens turned off for everyone, and screens whose access is
# fixed by role whatever the table says (Team: Admins and Super Admin. Login & security: Super Admin).
FIXED = {
    "tasks", "reports", "team", "dash_overview", "dash_legal", "dash_unanswered", "dash_chats",
    "dash_quality", "dash_privacy", "dash_security", "dash_activity", "dash_alerts", "dash_versions",
}  # fmt: skip

# Built in: managers change everything; Front Desk works leads, inbox, appointments and patients; Doctors see
# their own appointments and patients and change their own hours and leave (front desk any doctor's); only
# managers open the Dashboard and Team.
_desk: dict[str, Level] = {
    "dashboard": "view", "leads": "edit", "inbox": "edit", "doctors": "edit", "appointments": "edit",
    "tasks": "edit", "patients": "edit", "reports": "view", "team": "hidden", "settings": "hidden",
}  # fmt: skip
_doctor: dict[str, Level] = {
    "dashboard": "hidden", "leads": "hidden", "inbox": "hidden", "doctors": "edit", "appointments": "view",
    "tasks": "hidden", "patients": "view", "reports": "hidden", "team": "hidden", "settings": "hidden",
}  # fmt: skip
BUILTIN: dict[str, dict[str, Level]] = {
    "clinic_manager": {k: "edit" for k in SCREENS},
    "front_desk": {k: _desk.get(k, "hidden") for k in SCREENS},
    "doctor": {k: _doctor.get(k, "hidden") for k in SCREENS},
}


def _obj(v: Any) -> dict[str, Any]:
    return dict(json.loads(v) if isinstance(v, str) else v or {})


def clean(rules: dict[str, Any]) -> dict[str, dict[str, Level]]:
    """Only known roles, screens and levels."""
    out: dict[str, dict[str, Level]] = {}
    for role, screens in (rules or {}).items():
        if role in ROLES and isinstance(screens, dict):
            kept = {s: lv for s, lv in screens.items() if s in SCREENS and lv in LEVELS}
            if kept:
                out[role] = kept
    return out


def stack(*layers: dict[str, Any]) -> dict[str, dict[str, Level]]:
    """BUILTIN with each layer's changes on top."""
    out = {role: dict(screens) for role, screens in BUILTIN.items()}
    for layer in layers:
        for role, screens in clean(layer).items():
            out[role].update(screens)
    return out


async def effective(conn: Any, clinic: str) -> dict[str, dict[str, Level]]:
    """The rules in force for a clinic: built-in ← BB defaults ← the clinic's own."""
    row = await conn.fetchrow(
        """select (select permissions from app.platform where id = 1) defaults,
             (select rules from app.clinic_permissions where clinic_id = $1) own""",
        clinic,
    )
    return stack(_obj(row["defaults"]), _obj(row["own"]))


def rank(level: str) -> int:
    return LEVELS.index(level) if level in LEVELS else 0


async def for_person(conn: Any, clinic: str, user_id: str, role: str) -> dict[str, Level]:
    """What one person has in a clinic: their role's rules, raised by any access given to them for a time
    that has not ended. Super Admin: edit everywhere."""
    if role == "bb_admin":
        return {k: "edit" for k in SCREENS}
    mine = dict((await effective(conn, clinic)).get(role, {}))
    for g in await conn.fetch(
        """select screen, level from app.access_grants
           where clinic_id = $1 and user_id::text = $2 and until > now()""",
        clinic, user_id,
    ):  # fmt: skip
        if g["screen"] in SCREENS and rank(g["level"]) > rank(mine.get(g["screen"], "hidden")):
            mine[g["screen"]] = g["level"]
    return mine


async def require(conn: Any, user: Any, clinic: str, screen: str, need: Level) -> None:
    """Refuses (403) unless this person has at least `need` on the screen in this clinic (Who sees what)."""
    from fastapi import HTTPException, status

    role = "bb_admin" if user.bb_admin else user.roles.get(clinic)
    if role is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this clinic.")
    if rank((await for_person(conn, clinic, user.id, role)).get(screen, "hidden")) < rank(need):
        what = "change" if need == "edit" else "see"
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"You cannot {what} {SCREENS[screen][0]} here.")


# ---------- Dashboard tabs (their own modules) ----------
# A router-level check on /crm/.../{clinic} addresses: Super Admin passes; anyone else, Admins included,
# needs the Dashboard open and the tab's level (view to read, edit to save). Someone other than a manager is
# then let through the module's own manager check for this request (granted). Public addresses (forms, sheets,
# webhooks) have no clinic: untouched.
_granted: ContextVar[tuple[str, str] | None] = ContextVar("dash_granted", default=None)
SECTION_TAB = {
    "appearance": "appearance", "template": "templates", "menu": "menu", "flow": "menu", "chat": "menu",
    "contact": "content", "services": "content", "reviews": "content",
}  # fmt: skip


def granted(user: Any, clinic: str) -> bool:
    """This request passed the Dashboard tab check for this person and clinic."""
    return _granted.get() == (user.id, clinic)


def dash_guard(tab: str | None) -> Any:
    """The check for one Dashboard tab's module (None: the settings module; the tab comes from the path)."""

    async def guard(request: Request) -> None:
        clinic = request.path_params.get("clinic")
        if not clinic or "/crm/" not in request.url.path:
            return
        from app.core.db import get_pool
        from app.crm.auth import staff

        user = await staff(request.headers.get("authorization", ""))
        if user.bb_admin:
            return
        section = str(request.path_params.get("section") or "")
        t = tab or SECTION_TAB.get(section) or ("menu" if "/flow" in request.url.path else "open")
        need: Level = "view" if request.method == "GET" else "edit"
        pool = await get_pool()
        await require(pool, user, clinic, "dash_open", "view")
        await require(pool, user, clinic, f"dash_{t}", need)
        _granted.set((user.id, clinic))

    return guard
