"""Dashboard → Integrations → Google Sheet leads (migration 0021), JSON only.

Each sheet has its own secret (Supabase Vault) inside its private link. The Dashboard gives a ready Apps
Script with that link: the clinic pastes it in the sheet and runs it once. Every 5 minutes it sends the
sheet's tabs and their column headers; staff turn tabs on and map each column to our field (G2); rows of
those tabs become leads (G3). Any number of sheets per clinic, several tabs on at once.
"""

import hmac
import json
import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.db import get_pool
from app.crm import vault
from app.crm.auth import Staff, staff

router = APIRouter(tags=["crm"])


class Tab(BaseModel):
    id: str
    tab: str
    headers: list[str]
    active: bool
    mapping: dict[str, str]  # sheet column -> our field
    date_order: str | None


class Sheet(BaseModel):
    id: str
    name: str
    last_seen_at: str | None  # the Apps Script last reported in
    tabs: list[Tab]


class NewSheet(BaseModel):
    name: str = Field(min_length=1, max_length=80)


def _manager(user: Staff, clinic: str) -> None:
    if not (user.bb_admin or user.roles.get(clinic) == "clinic_manager"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Integrations are for clinic managers and BB Admin.")


async def _list(clinic: str) -> list[Sheet]:
    pool = await get_pool()
    sheets = await pool.fetch(
        "select * from app.lead_sheets where clinic_id = $1 order by created_at", clinic
    )
    tabs = await pool.fetch("select * from app.lead_sheet_tabs where clinic_id = $1 order by tab", clinic)
    return [
        Sheet(
            id=str(s["id"]), name=s["name"],
            last_seen_at=s["last_seen_at"].isoformat() if s["last_seen_at"] else None,
            tabs=[
                Tab(id=str(t["id"]), tab=t["tab"], headers=list(t["headers"]), active=t["active"],
                    mapping=dict(_json(t["mapping"])), date_order=t["date_order"])
                for t in tabs if t["sheet_id"] == s["id"]
            ],
        )
        for s in sheets
    ]  # fmt: skip


def _json(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


@router.get("/crm/console/{clinic}/integrations/sheets", response_model=list[Sheet])
async def sheets(user: Annotated[Staff, Depends(staff)], clinic: str) -> list[Sheet]:
    _manager(user, clinic)
    return await _list(clinic)


@router.post("/crm/console/{clinic}/integrations/sheets", response_model=list[Sheet])
async def add_sheet(user: Annotated[Staff, Depends(staff)], clinic: str, body: NewSheet) -> list[Sheet]:
    """A new sheet with its own secret (kept in Vault)."""
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        if await conn.fetchval(
            "select 1 from app.lead_sheets where clinic_id = $1 and name = $2", clinic, body.name.strip()
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "A sheet with this name is already added.")
        secret = await vault.save(conn, secrets.token_urlsafe(32), f"sheet {clinic} {body.name.strip()[:40]}")
        await conn.execute(
            "insert into app.lead_sheets (clinic_id, name, secret, created_by) values ($1, $2, $3, $4::uuid)",
            clinic, body.name.strip(), secret, user.id,
        )  # fmt: skip
    return await _list(clinic)


@router.delete("/crm/console/{clinic}/integrations/sheets/{sheet}", response_model=list[Sheet])
async def delete_sheet(user: Annotated[Staff, Depends(staff)], clinic: str, sheet: str) -> list[Sheet]:
    """Removes a sheet: its link stops working at once (leads already made stay)."""
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        old = await conn.fetchval(
            "delete from app.lead_sheets where clinic_id = $1 and id = $2::uuid returning secret",
            clinic,
            sheet,
        )
        if old is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sheet not found.")
        await vault.delete(conn, old)
    return await _list(clinic)


class Script(BaseModel):
    link: str
    script: str


@router.get("/crm/console/{clinic}/integrations/sheets/{sheet}/script", response_model=Script)
async def sheet_script(
    user: Annotated[Staff, Depends(staff)], clinic: str, sheet: str, request: Request
) -> Script:
    """The Apps Script to paste in the sheet, with this sheet's private link inside."""
    _manager(user, clinic)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select secret, name from app.lead_sheets where clinic_id = $1 and id = $2::uuid", clinic, sheet
        )
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sheet not found.")
        key = await vault.read(conn, row["secret"])
    base = (get_settings().public_url or str(request.base_url)).rstrip("/")
    link = f"{base}/v1/integrations/sheets/{sheet}?key={key}"
    return Script(link=link, script=SCRIPT.replace("__LINK__", link).replace("__NAME__", row["name"]))


class Incoming(BaseModel):
    tabs: list[dict[str, Any]] = Field(default=[], max_length=100)  # {"tab": name, "headers": [...]}
    rows: list[dict[str, Any]] = Field(default=[], max_length=500)  # G3


@router.post("/integrations/sheets/{sheet}")
async def from_sheet(sheet: str, key: str, body: Incoming) -> dict[str, Any]:
    """Called by the sheet's Apps Script: the tabs and headers it has (rows: G3). Answers which tabs are
    on."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "select id, clinic_id, secret from app.lead_sheets where id::text = $1", sheet
        )
        real = await vault.read(conn, row["secret"]) if row else None
        if row is None or not real or not hmac.compare_digest(real, key):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "This sheet's link is not valid. Copy the script again."
            )
        for t in body.tabs:
            name = str(t.get("tab") or "").strip()[:100]
            headers = [str(h).strip()[:100] for h in (t.get("headers") or []) if str(h).strip()][:100]
            if name:
                await conn.execute(
                    """insert into app.lead_sheet_tabs (sheet_id, clinic_id, tab, headers)
                       values ($1, $2, $3, $4)
                       on conflict (sheet_id, tab) do update set headers = $4""",
                    row["id"], row["clinic_id"], name, headers,
                )  # fmt: skip
        await conn.execute("update app.lead_sheets set last_seen_at = now() where id = $1", row["id"])
        active = await conn.fetch(
            "select tab from app.lead_sheet_tabs where sheet_id = $1 and active", row["id"]
        )
    return {"ok": True, "active_tabs": [a["tab"] for a in active]}


# The Apps Script given to the clinic (one per sheet). Pasted in the sheet (Extensions → Apps Script) and run
# once ("crmSetup"); it then reports every 5 minutes. Names start with "crm" so they never clash.
SCRIPT = """// ===================== NEO CRM: leads from this sheet ("__NAME__") =====================
// 1. Extensions > Apps Script: paste this at the END (it does not change the existing code).
// 2. Choose the function "crmSetup" and press Run once; allow the permissions Google asks for.
// That is all. Every 5 minutes this sheet's tabs and column names are sent to the CRM; in the Dashboard,
// turn on the tabs to import and match their columns. Keep this link private: it lets the sheet send leads.
const CRM_LINK = "__LINK__";

function crmSetup() {
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === "crmSend")
    .forEach((t) => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger("crmSend").timeBased().everyMinutes(5).create();
  crmSend();
}

function crmSend() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return; // the previous run is still going
  try {
    const tabs = SpreadsheetApp.getActiveSpreadsheet().getSheets().map((s) => ({
      tab: s.getName(),
      headers: s.getLastColumn() ? s.getRange(1, 1, 1, s.getLastColumn()).getDisplayValues()[0] : [],
    }));
    const res = UrlFetchApp.fetch(CRM_LINK, {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify({ tabs: tabs }),
      muteHttpExceptions: true,
    });
    if (res.getResponseCode() >= 300) throw new Error("CRM: " + res.getContentText());
  } finally {
    lock.releaseLock();
  }
}
"""
