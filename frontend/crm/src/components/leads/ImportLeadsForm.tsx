"use client";

import { useState, type ChangeEvent } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError, saveFile, type LeadImportResult } from "@/lib/api";
import { parseCsv } from "@/lib/kb-import";

const MAX_ROWS = 2000;
const TEMPLATE = "Name,Phone,Email,Treatment,Campaign,Source\r\n";
// The words a column's heading may use (lower case); Name and Phone are needed.
const COLUMNS: Record<string, string[]> = {
  name: ["name", "full name", "patient", "patient name"],
  phone: ["phone", "phone number", "mobile", "mobile number", "contact", "contact number", "whatsapp"],
  email: ["email", "email address", "e-mail"],
  treatment: ["treatment", "service"],
  campaign: ["campaign"],
  source: ["source"],
};

type Row = Record<string, string | number>;

function readRows(text: string): Row[] {
  const [head, ...lines] = parseCsv(text);
  const at = (head ?? []).map((h) => h.trim().toLowerCase());
  const column = (key: string) => at.findIndex((h) => COLUMNS[key].includes(h));
  if (column("name") < 0 || column("phone") < 0) {
    throw new Error("The file needs a Name column and a Phone column. Download the template to see the format.");
  }
  const rows: Row[] = [];
  lines.forEach((cells, i) => {
    if (!cells.some((c) => c.trim())) return; // an empty line
    const row: Row = { row: i + 2 }; // the line in the file, for the report
    for (const key of Object.keys(COLUMNS)) {
      const c = column(key);
      row[key] = c < 0 ? "" : (cells[c] ?? "").trim().slice(0, 500);
    }
    rows.push(row);
  });
  if (!rows.length) throw new Error("The file has no leads in it.");
  if (rows.length > MAX_ROWS) throw new Error(`Import at most ${MAX_ROWS} leads at a time.`);
  return rows;
}

/** Import leads (in the pop-up): a CSV is checked first and shown; nothing is saved until it is confirmed. */
export default function ImportLeadsForm({ clinicId, onDone }: { clinicId: string; onDone: () => void }) {
  const { toast, closeModal } = useCrm();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [check, setCheck] = useState<LeadImportResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const send = (confirm: boolean, list: Row[]) =>
    api<LeadImportResult>("/v1/crm/leads/import", {
      method: "POST",
      body: JSON.stringify({ clinic: clinicId, rows: list, confirm }),
    });

  async function choose(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // the same file can be chosen again
    if (!file) return;
    setRows(null);
    setCheck(null);
    setError("");
    if (!/\.csv$/i.test(file.name)) {
      setError("Upload a CSV file. In Excel: File → Save As → CSV UTF-8.");
      return;
    }
    setBusy(true);
    try {
      const list = readRows(await file.text());
      setCheck(await send(false, list));
      setRows(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read the file.");
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!rows) return;
    setBusy(true);
    setError("");
    try {
      const done = await send(true, rows);
      toast(`${done.added} lead${done.added === 1 ? "" : "s"} imported`);
      closeModal();
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not import the leads. Please try again.");
      setBusy(false);
    }
  }

  const skipped = [
    ...(check?.duplicates ?? []).map((p) => ({ ...p, reason: `Already a lead: ${p.reason}` })),
    ...(check?.invalid ?? []),
  ].sort((a, b) => a.row - b.row);

  return (
    <div style={{ display: "grid", gap: 12 }}>
      {error && <div className="warnbox">{error}</div>}
      <p className="sub2" style={{ margin: 0 }}>
        Upload a CSV with Name and Phone columns; Email, Treatment, Campaign and Source are optional. Numbers already
        in this clinic are skipped. Each new lead gets your webhooks and the &quot;Imported lead&quot; WhatsApp message, when
        that template is on in Integrations.
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <label className="btn g" style={{ opacity: busy ? 0.6 : 1 }}>
          {busy && !check ? "Checking…" : "Choose CSV file"}
          <input type="file" accept=".csv,text/csv" hidden disabled={busy} onChange={choose} />
        </label>
        <button
          type="button"
          className="btn g"
          onClick={() =>
            saveFile(new Blob(["﻿" + TEMPLATE], { type: "text/csv;charset=utf-8" }), "leads-import-template.csv")
          }
        >
          Download template
        </button>
      </div>
      {check && (
        <>
          <p style={{ margin: 0 }}>
            <b>{check.ready}</b> ready to import, <b>{check.duplicates.length}</b> already in this clinic,{" "}
            <b>{check.invalid.length}</b> with a problem.
          </p>
          {!!skipped.length && (
            <div style={{ maxHeight: 180, overflowY: "auto" }} className="sub2">
              {skipped.slice(0, 100).map((p) => (
                <div key={p.row}>
                  Line {p.row}
                  {p.name ? ` (${p.name})` : ""}: {p.reason}
                </div>
              ))}
              {skipped.length > 100 && <div>…and {skipped.length - 100} more.</div>}
            </div>
          )}
          <button type="button" className="btn" disabled={busy || !check.ready} onClick={confirm}>
            {busy ? "Importing…" : `Import ${check.ready} lead${check.ready === 1 ? "" : "s"}`}
          </button>
        </>
      )}
    </div>
  );
}
