"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";

// Integrations → Google Sheet leads: the clinic's sheets. Each has its own private link inside a ready Apps
// Script: paste it in the sheet and run it once; its tabs and column names then appear here.

type Tab = {
  id: string;
  tab: string;
  headers: string[];
  active: boolean;
  mapping: Record<string, string>;
  hidden: boolean; // not listed in "Tab to set up"
  sample: string[]; // one example row, shown the CRM's way
};
type Sheet = {
  id: string;
  name: string;
  last_seen_at: string | null;
  tabs: Tab[];
};

export default function SheetsPanel({ clinicId }: { clinicId: string }) {
  const { toast } = useCrm();
  const [sheets, setSheets] = useState<Sheet[] | null>(null);
  const [name, setName] = useState("");
  const [script, setScript] = useState<{ id: string; text: string } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const url = `/v1/crm/console/${clinicId}/integrations/sheets`;

  useEffect(() => {
    let live = true;
    api<Sheet[]>(url).then(
      (s) => live && setSheets(s),
      (e) =>
        live &&
        setError(
          e instanceof ApiError ? e.message : "Could not load the sheets.",
        ),
    );
    return () => {
      live = false;
    };
  }, [url]);

  async function call(
    path: string,
    method: string,
    body?: object,
    done?: string,
  ) {
    setBusy(true);
    setError("");
    try {
      setSheets(
        await api<Sheet[]>(url + path, {
          method,
          body: body ? JSON.stringify(body) : undefined,
        }),
      );
      if (done) toast(done);
      return true;
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        marginTop: 10,
        borderTop: "1px solid var(--line)",
        paddingTop: 10,
      }}
    >
      <p className="sub2" style={{ margin: "0 0 8px", fontSize: 12.5 }}>
        Add each Google Sheet of leads, copy its script and paste it in the
        sheet (Extensions → Apps Script), then run &quot;crmSetup&quot; once.
        Its tabs and column names appear here within 5 minutes.
      </p>
      {sheets?.map((s) => (
        <div
          key={s.id}
          className="card"
          style={{ marginBottom: 8, padding: 10 }}
        >
          <div
            style={{
              display: "flex",
              gap: 8,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <b style={{ flex: 1 }}>{s.name}</b>
            <span className={`badge ${s.last_seen_at ? "b-vi" : "b-fu"}`}>
              {s.last_seen_at ? "Reporting" : "Waiting for the script"}
            </span>
            <button
              className="btn g"
              disabled={busy}
              onClick={async () => {
                const got = await api<{ script: string }>(
                  `${url}/${s.id}/script`,
                );
                setScript(
                  script?.id === s.id ? null : { id: s.id, text: got.script },
                );
              }}
            >
              {script?.id === s.id ? "Hide script" : "Get script"}
            </button>
            <button
              className="btn g"
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    `Remove "${s.name}"? Its link stops working (leads already made stay).`,
                  )
                )
                  void call(`/${s.id}`, "DELETE", undefined, "Sheet removed");
              }}
            >
              Remove
            </button>
          </div>
          <p className="sub2" style={{ margin: "4px 0 0", fontSize: 12 }}>
            {s.last_seen_at
              ? `Last report ${new Date(s.last_seen_at).toLocaleString("en-IN")} · ${s.tabs.length} tab(s)`
              : "Not reported yet"}
          </p>
          {s.tabs.length > 0 && (
            <TabMapping
              sheet={s}
              url={`${url}/${s.id}/tabs`}
              onSaved={(list) => setSheets(list)}
            />
          )}
          {script?.id === s.id && (
            <div style={{ marginTop: 8 }}>
              <textarea
                readOnly
                rows={8}
                value={script.text}
                style={{
                  width: "100%",
                  fontFamily: "ui-monospace, monospace",
                  fontSize: 12,
                }}
                onFocus={(e) => e.target.select()}
              />
              <button
                className="btn"
                style={{ marginTop: 6 }}
                onClick={() =>
                  navigator.clipboard.writeText(script.text).then(
                    () => toast("Script copied"),
                    () => toast("Select the script and copy it"),
                  )
                }
              >
                Copy script
              </button>
              <p className="sub2" style={{ margin: "6px 0 0", fontSize: 12 }}>
                Keep it private: its link lets this sheet send leads. If it
                leaks, remove the sheet and add it again.
              </p>
            </div>
          )}
        </div>
      ))}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input
          className="f"
          style={{ flex: 1, minWidth: 200 }}
          placeholder="Sheet name, e.g. Meta leads Oct 2026"
          maxLength={80}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button
          className="btn"
          disabled={busy || !name.trim()}
          onClick={async () => {
            if (
              await call(
                "",
                "POST",
                { name: name.trim() },
                "Sheet added: copy its script",
              )
            )
              setName("");
          }}
        >
          Add sheet
        </button>
      </div>
      {error && (
        <p className="warnbox" style={{ marginTop: 6 }}>
          {error}
        </p>
      )}
    </div>
  );
}

// Our fields (backend: crm_sheets.FIELDS). "skip": the column is not imported.
const FIELDS: [string, string][] = [
  ["skip", "Skip"],
  ["name", "Name"],
  ["phone", "Phone"],
  ["email", "Email"],
  ["city", "City"],
  ["treatment", "Treatment"],
  ["campaign", "Campaign"],
  ["ad_name", "Ad name"],
  ["notes", "Notes"],
  ["date", "Lead date"],
];

/** A first guess from the column's name (staff correct the rest). */
function guess(col: string): string {
  const c = col.toLowerCase();
  if (/^(full[ _]?)?name$|patient name|lead name/.test(c)) return "name";
  if (/phone|mobile|contact number|whatsapp/.test(c)) return "phone";
  if (/e-?mail/.test(c)) return "email";
  if (/\bcity\b|location/.test(c)) return "city";
  if (/concern|treatment|service/.test(c)) return "treatment";
  if (/campaign[ _]?name|^campaign$/.test(c)) return "campaign";
  if (/^ad[ _]?name$/.test(c)) return "ad_name";
  if (/remark|note|comment/.test(c)) return "notes";
  if (/^date$|created[ _]?time|^created$|lead date|submitted/.test(c))
    return "date";
  return "skip";
}

/** Choose a tab, then for each of its columns: the sheet's name (top) and our field (below). */
function TabMapping({
  sheet,
  url,
  onSaved,
}: {
  sheet: Sheet;
  url: string;
  onSaved: (list: Sheet[]) => void;
}) {
  const { toast } = useCrm();
  const [tabId, setTabId] = useState("");
  const tab = sheet.tabs.find((t) => t.id === tabId);
  const [draft, setDraft] = useState<{
    id: string;
    active: boolean;
    mapping: Record<string, string>;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showHidden, setShowHidden] = useState(false);
  const hiddenCount = sheet.tabs.filter((t) => t.hidden).length;
  const edit =
    draft && draft.id === tabId
      ? draft
      : tab
        ? {
            id: tab.id,
            active: tab.active,
            mapping: Object.fromEntries(
              tab.headers.map((h) => [
                h,
                tab.mapping[h] ??
                  (Object.keys(tab.mapping).length ? "skip" : guess(h)),
              ]),
            ),
          }
        : null;
  const on = sheet.tabs.filter((t) => t.active).map((t) => t.tab);
  return (
    <div style={{ marginTop: 8 }}>
      <label
        style={{
          display: "flex",
          gap: 8,
          alignItems: "center",
          flexWrap: "wrap",
          fontSize: 13,
        }}
      >
        Tab to set up
        <select
          className="sel"
          value={tabId}
          onChange={(e) => {
            setTabId(e.target.value);
            setDraft(null);
            setError("");
          }}
        >
          <option value="">Choose a tab…</option>
          {sheet.tabs
            .filter((t) => showHidden || !t.hidden || t.id === tabId)
            .map((t) => (
              <option key={t.id} value={t.id} disabled={!t.headers.length}>
                {t.tab}
                {t.active ? " (importing)" : ""}
                {!t.headers.length ? " (no columns)" : ""}
                {t.hidden ? " (hidden)" : ""}
              </option>
            ))}
        </select>
        {hiddenCount > 0 && (
          <button className="pill" onClick={() => setShowHidden((v) => !v)}>
            {showHidden
              ? "Hide hidden tabs"
              : `Show hidden tabs (${hiddenCount})`}
          </button>
        )}
        <span className="sub2" style={{ fontSize: 12 }}>
          {on.length ? `Importing: ${on.join(", ")}` : "No tab is imported yet"}
        </span>
      </label>
      {edit && tab && (
        <div style={{ marginTop: 10 }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))",
              gap: 8,
            }}
          >
            {tab.headers.map((h) => (
              <div
                key={h}
                style={{
                  border: "1px solid var(--line)",
                  borderRadius: 8,
                  padding: 6,
                }}
              >
                <div
                  style={{
                    fontSize: 12.5,
                    fontWeight: 600,
                    wordBreak: "break-word",
                  }}
                  title="Column in the sheet"
                >
                  {h}
                </div>
                <div
                  className="sub2"
                  style={{
                    fontSize: 11.5,
                    wordBreak: "break-word",
                    minHeight: 16,
                  }}
                  title="Example from the sheet, shown the CRM's way"
                >
                  {tab.sample[tab.headers.indexOf(h)] || "—"}
                </div>
                <select
                  className="sel"
                  style={{ width: "100%", marginTop: 4 }}
                  aria-label={`Our field for ${h}`}
                  value={edit.mapping[h] ?? "skip"}
                  onChange={(e) =>
                    setDraft({
                      ...edit,
                      mapping: { ...edit.mapping, [h]: e.target.value },
                    })
                  }
                >
                  {FIELDS.map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
          <label
            style={{
              display: "flex",
              gap: 6,
              alignItems: "center",
              marginTop: 10,
              fontSize: 13,
            }}
          >
            <input
              type="checkbox"
              checked={edit.active}
              onChange={(e) => setDraft({ ...edit, active: e.target.checked })}
            />
            Import this tab&apos;s rows as leads
          </label>
          <button
            className="pill"
            style={{ marginTop: 8 }}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                onSaved(
                  await api<Sheet[]>(`${url}/${tab.id}`, {
                    method: "PUT",
                    body: JSON.stringify({
                      hidden: !tab.hidden,
                      active: false,
                      mapping: tab.mapping,
                    }),
                  }),
                );
                toast(
                  tab.hidden ? `${tab.tab}: shown again` : `${tab.tab}: hidden`,
                );
                if (!tab.hidden) setTabId("");
              } catch (e) {
                setError(
                  e instanceof ApiError
                    ? e.message
                    : "Could not save. Please try again.",
                );
              } finally {
                setBusy(false);
              }
            }}
          >
            {tab.hidden
              ? "Show this tab again"
              : "Hide this tab (never imported)"}
          </button>
          {error && (
            <p className="warnbox" style={{ marginTop: 6 }}>
              {error}
            </p>
          )}
          <button
            className="btn"
            style={{ marginTop: 8 }}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                onSaved(
                  await api<Sheet[]>(`${url}/${tab.id}`, {
                    method: "PUT",
                    body: JSON.stringify({
                      active: edit.active,
                      mapping: edit.mapping,
                    }),
                  }),
                );
                setDraft(null);
                toast(
                  edit.active
                    ? `${tab.tab}: saved, importing`
                    : `${tab.tab}: saved`,
                );
              } catch (e) {
                setError(
                  e instanceof ApiError
                    ? e.message
                    : "Could not save. Please try again.",
                );
              } finally {
                setBusy(false);
              }
            }}
          >
            Save
          </button>
        </div>
      )}
    </div>
  );
}
