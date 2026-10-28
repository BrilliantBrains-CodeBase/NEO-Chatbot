"""Dashboard → Integrations → Google Sheet leads (migration 0021), JSON only.

Each sheet has its own secret (Supabase Vault) inside its private link. The Dashboard gives a ready Apps
Script with that link: the clinic pastes it in the sheet and runs it once. Every 5 minutes it sends the
sheet's tabs and their column headers; staff turn tabs on and map each column to our field (G2); rows of
those tabs become leads (G3). Any number of sheets per clinic, several tabs on at once.
"""

import hmac
import json
import re
import secrets
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.chat.leads import _assignee
from app.core.config import get_settings
from app.core.db import get_pool
from app.crm import vault, webhooks
from app.crm.auth import Staff, staff
from app.crm.sheet_values import now_utc, phone, shown, when

router = APIRouter(tags=["crm"])


class Tab(BaseModel):
    id: str
    tab: str
    headers: list[str]
    active: bool
    mapping: dict[str, str]  # sheet column -> our field
    date_order: str | None
    hidden: bool  # not shown in the list of tabs to set up
    sample: list[str]  # one example row, shown the CRM's way (the sheet keeps its own values)


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
                    mapping=dict(_json(t["mapping"])), date_order=t["date_order"], hidden=t["hidden"],
                    sample=[shown(v) for v in t["sample"]])
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


# Our fields a sheet column can go to (more are added later). "date": when the lead came (any format; G3).
FIELDS = {
    "name": "Name", "phone": "Phone", "email": "Email", "city": "City", "treatment": "Treatment",
    "campaign": "Campaign", "ad_name": "Ad name", "notes": "Notes", "date": "Lead date",
}  # fmt: skip


class TabSettings(BaseModel):
    hidden: bool = False  # hidden tabs are never imported
    active: bool = False
    mapping: dict[str, str] = Field(default={}, max_length=100)  # sheet column -> our field
    date_order: Literal["dmy", "mdy"] | None = None  # how the tab writes dates (None: worked out)


@router.get("/crm/console/integrations/sheet-fields")
async def sheet_fields(user: Annotated[Staff, Depends(staff)]) -> dict[str, str]:
    """Our fields, for the mapping boxes."""
    return FIELDS


@router.put("/crm/console/{clinic}/integrations/sheets/{sheet}/tabs/{tab}", response_model=list[Sheet])
async def save_tab(
    user: Annotated[Staff, Depends(staff)], clinic: str, sheet: str, tab: str, body: TabSettings
) -> list[Sheet]:
    """Turns a tab on or off and saves its columns -> our fields. On needs Name and Phone or Email."""
    _manager(user, clinic)
    pool = await get_pool()
    row = await pool.fetchrow(
        "select headers from app.lead_sheet_tabs "
        "where id = $1::uuid and sheet_id = $2::uuid and clinic_id = $3",
        tab, sheet, clinic,
    )  # fmt: skip
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tab not found.")
    if body.hidden:
        body.active = False
    mapping = {col: f for col, f in body.mapping.items() if f and f != "skip"}
    for col, f in mapping.items():
        if col not in row["headers"] or f not in FIELDS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"'{col}' cannot go to '{f}'.")
    used = list(mapping.values())
    twice = sorted({FIELDS[f] for f in used if used.count(f) > 1})
    if twice:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Two columns go to {', '.join(twice)}.")
    if body.active and not ("name" in used and ("phone" in used or "email" in used)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "To import this tab, choose its Name and Phone (or Email)."
        )
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", user.id)
        await conn.execute(
            "update app.lead_sheet_tabs set active = $2, mapping = $3::jsonb, date_order = $4, hidden = $5 "
            "where id = $1::uuid",
            tab, body.active, json.dumps(mapping), body.date_order, body.hidden,
        )  # fmt: skip
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
            "select id, clinic_id, secret, name from app.lead_sheets where id::text = $1", sheet
        )
        sheet_name = row["name"] if row else ""
        real = await vault.read(conn, row["secret"]) if row else None
        if row is None or not real or not hmac.compare_digest(real, key):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "This sheet's link is not valid. Copy the script again."
            )
        for t in body.tabs:
            name = str(t.get("tab") or "").strip()[:100]
            cols = [str(h).strip()[:100] for h in (t.get("headers") or [])][:100]
            raw = [str(v)[:300] for v in (t.get("sample") or [])][: len(cols)]
            raw += [""] * (len(cols) - len(raw))
            keep = [i for i, h in enumerate(cols) if h and h != "CRM"]  # blank and our CRM column skipped
            headers, sample = [cols[i] for i in keep], [raw[i] for i in keep]
            if name:
                await conn.execute(
                    """insert into app.lead_sheet_tabs (sheet_id, clinic_id, tab, headers, sample)
                       values ($1, $2, $3, $4, $5)
                       on conflict (sheet_id, tab) do update set headers = $4,
                         sample = case when cardinality($5::text[]) > 0 then $5
                                       else lead_sheet_tabs.sample end""",
                    row["id"], row["clinic_id"], name, headers, sample,
                )  # fmt: skip
        await conn.execute("update app.lead_sheets set last_seen_at = now() where id = $1", row["id"])
        tabs = {
            t["tab"]: t
            for t in await conn.fetch(
                "select tab, mapping, date_order from app.lead_sheet_tabs where sheet_id = $1 and active",
                row["id"],
            )
        }
        clinic = await conn.fetchrow(
            "select id, lead_assignment from app.clinics where id = $1 and active", row["clinic_id"]
        )
        results = []
        for r in body.rows[:50]:
            tab = tabs.get(str(r.get("tab", "")))
            if tab is None:
                continue  # turned off meanwhile
            try:
                code = await _lead_from_row(conn, clinic, sheet_name, tab, r)
                results.append({"tab": tab["tab"], "row": r.get("row"), "status": f"{code} ✓"})
            except ValueError as e:
                results.append({"tab": tab["tab"], "row": r.get("row"), "status": str(e)})
        active = await conn.fetch(
            "select tab from app.lead_sheet_tabs where sheet_id = $1 and active", row["id"]
        )
    return {"ok": True, "active_tabs": [a["tab"] for a in active], "results": results}


async def _lead_from_row(
    conn: Any, clinic: Any, sheet_name: str, tab: Any, r: dict[str, Any], source: str = "meta_ads"
) -> str:
    """One sheet row as a lead (source Meta Ads), by the tab's mapping and shown the CRM's way. One lead per
    phone (or email) per clinic: a repeat counts up. Unmapped columns go in the notes. Returns the lead code;
    ValueError (the reason, written in the sheet's CRM column) when the row cannot be a lead."""
    mapping: dict[str, str] = dict(_json(tab["mapping"]))
    values = {str(k).strip(): str(v).strip() for k, v in (r.get("values") or {}).items() if str(v).strip()}
    got = {f: values.get(col, "") for col, f in mapping.items()}
    name = " ".join(shown(got.get("name", "")).split())[:100]
    tel = phone(got.get("phone", "")) if got.get("phone") else None
    email = got.get("email", "").lower()
    email = email if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", email) else ""
    if len(name) < 2 or not (tel or email):
        raise ValueError("Not imported: needs a name and a valid phone or email")
    e164 = tel.replace(" ", "") if tel else None
    cc = "+91" if e164 and e164.startswith("+91") else ""
    came = when(got["date"], tab["date_order"]) if got.get("date") else None
    if came and came > now_utc():
        came = None  # a date in the future is not when the lead came
    extra = {f: shown(got[f]) for f in ("city", "ad_name", "notes") if got.get(f)}
    unmapped = {k: shown(v) for k, v in values.items() if k not in mapping and k != "CRM"}
    note = "\n".join(
        [*(f"{FIELDS[k]}: {v}" for k, v in extra.items()), *(f"{k}: {v}" for k, v in unmapped.items())]
    )
    treatment = shown(got.get("treatment", ""))[:100] or None
    campaign = shown(got.get("campaign", ""))[:100] or None
    code = str(r.get("lead_code") or "").strip().rstrip(" ✓")
    lead = None
    if code:  # sent before (its CRM cell had the code): update that lead
        lead = await conn.fetchrow(
            "select id, lead_code from app.leads "
            "where lead_code = $1 and clinic_id = $2 and deleted_at is null",
            code, clinic["id"],
        )  # fmt: skip
    if lead is None:
        lead = await conn.fetchrow(
            """select id, lead_code from app.leads where clinic_id = $1 and deleted_at is null
               and (phone_e164 = $2 or ($2::text is null and email = $3)) for update""",
            clinic["id"], e164, email or None,
        )  # fmt: skip
    if lead is not None:
        await conn.execute(
            """update app.leads set phone_e164 = coalesce($2, phone_e164), email = coalesce($3, email),
                 campaign = coalesce($4, campaign), treatment = coalesce(treatment, $5),
                 contact_count = contact_count + 1, last_contact_at = now(), updated_at = now()
               where id = $1""",
            lead["id"], e164, email or None, campaign, treatment,
        )  # fmt: skip
    else:
        lead = await conn.fetchrow(
            """insert into app.leads (clinic_id, full_name, phone_e164, phone_cc, email, source, campaign,
                 treatment, assigned_to, notes, first_contact_at, last_contact_at)
               values ($1, $2, $3, nullif($4, ''), $5, $11, $6, $7, $8, $9, coalesce($10, now()),
                 greatest(coalesce($10, now()), now())) returning id, lead_code""",
            clinic["id"], name, e164, cc, email or None, campaign, treatment, await _assignee(conn, clinic),
            note[:2000], came, source,
        )  # fmt: skip
        webhooks.emit(clinic["id"], "lead_new", {
            "lead_code": lead["lead_code"], "name": name, "phone": tel, "email": email or None,
            "treatment": treatment, "campaign": campaign, "source": source,
        })  # fmt: skip
    data = {
        "source": source,
        "via": "google_sheet" if source == "meta_ads" else "webhook",
        "sheet": sheet_name,
        "tab": tab["tab"],
        "row": r.get("row"),
    }
    await conn.execute(
        "insert into app.lead_events (clinic_id, lead_id, kind, data) values ($1, $2, 'contact', $3::jsonb)",
        clinic["id"], lead["id"], json.dumps(data),
    )  # fmt: skip
    return str(lead["lead_code"])


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

function crmPost(body) {
  const res = UrlFetchApp.fetch(CRM_LINK, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(body),
    muteHttpExceptions: true,
  });
  if (res.getResponseCode() >= 300) throw new Error("CRM: " + res.getContentText());
  return JSON.parse(res.getContentText());
}

function crmSend() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return; // the previous run is still going
  try {
    const tabs = SpreadsheetApp.getActiveSpreadsheet().getSheets().map((s) => {
      const cols = s.getLastColumn(), last = s.getLastRow();
      return {
        tab: s.getName(),
        headers: cols ? s.getRange(1, 1, 1, cols).getDisplayValues()[0] : [],
        sample: cols && last > 1 ? s.getRange(last, 1, 1, cols).getDisplayValues()[0] : [], // the newest row
      };
    });
    const first = crmPost({ tabs: tabs });
    // Rows of the tabs turned on in the Dashboard: each row without a lead code in its CRM column (at most
    // 50 a run). The CRM column (added at the end) then shows the lead code, or why the row was not taken.
    const book = SpreadsheetApp.getActiveSpreadsheet();
    const rows = [], cells = [];
    for (const name of first.active_tabs || []) {
      const s = book.getSheetByName(name);
      if (!s || s.getLastRow() < 2) continue;
      let head = s.getRange(1, 1, 1, s.getLastColumn()).getDisplayValues()[0];
      let crm = head.indexOf("CRM");
      if (crm < 0) {
        crm = head.length;
        s.getRange(1, crm + 1).setValue("CRM");
        head = head.concat(["CRM"]);
      }
      const data = s.getRange(2, 1, s.getLastRow() - 1, head.length).getDisplayValues();
      for (let i = 0; i < data.length && rows.length < 50; i++) {
        const status = data[i][crm];
        if (status && status.endsWith("✓")) continue; // already a lead
        if (data[i].every((v, j) => j === crm || !v)) continue; // an empty row
        const values = {};
        head.forEach((h, j) => { if (h && j !== crm) values[h] = data[i][j]; });
        rows.push({ tab: name, row: i + 2, values: values });
        cells.push(s.getRange(i + 2, crm + 1));
      }
    }
    if (rows.length) {
      const done = crmPost({ rows: rows }).results || [];
      done.forEach((r, k) => cells[k] && cells[k].setValue(r.status));
    }
  } finally {
    lock.releaseLock();
  }
}
"""
