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
          {s.tabs.map((t) => (
            <p key={t.id} style={{ margin: "4px 0 0", fontSize: 12.5 }}>
              <b>{t.tab}</b>{" "}
              <span className="sub2">
                · {t.headers.join(", ") || "no columns"}
              </span>
            </p>
          ))}
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
