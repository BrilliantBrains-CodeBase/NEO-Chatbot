"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";
import OnlineSetup from "./OnlineSetup";
import SheetsPanel from "./SheetsPanel";
import FormsPanel from "./FormsPanel";
import GmailPanel from "./GmailPanel";
import WebhooksPanel from "./WebhooksPanel";
import WhatsAppPanel from "./WhatsAppPanel";

// Dashboard → Integrations: which outside services are connected and what they did lately. Keys stay in the
// backend's settings and are never shown here: only "Connected" or not.

type Integration = {
  id: string;
  name: string;
  does: string;
  state: "connected" | "not_connected" | "not_built";
  detail: string[];
  last: string | null;
};

const STATE = {
  connected: ["b-vi", "Connected"],
  not_connected: ["b-fu", "Not connected"],
  not_built: ["b-lo", "Not built yet"],
} as const;

export default function IntegrationsView() {
  const { clinic, me } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const [data, setData] = useState<{
    clinic: string;
    list: Integration[];
  } | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<string | null>(null); // one service open at a time

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Integration[]>(`/v1/crm/console/${clinicId}/integrations`).then(
      (list) => live && setData({ clinic: clinicId, list }),
      (e) =>
        live &&
        setError(
          e instanceof ApiError
            ? e.message
            : "Could not load the integrations.",
        ),
    );
    return () => {
      live = false;
    };
  }, [clinicId]);

  const list = data && data.clinic === clinicId ? data.list : null;
  return (
    <div className="page" style={{ maxWidth: 820 }}>
      <h2 style={{ margin: "0 0 4px" }}>Integrations</h2>
      <p className="sub2" style={{ margin: "0 0 14px" }}>
        Outside services the chatbot and the CRM use. Keys are kept on the
        server and never shown.
      </p>
      {error && <div className="warnbox">{error}</div>}
      {list === null && !error && <p className="sub2">Loading…</p>}
      {list?.map((i) => (
        <div key={i.id} className="card" style={{ marginBottom: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <b style={{ flex: 1 }}>{i.name}</b>
            <span className={`badge ${STATE[i.state][0]}`}>
              {STATE[i.state][1]}
            </span>
            <button
              className="btn g"
              aria-expanded={open === i.id}
              onClick={() => setOpen(open === i.id ? null : i.id)}
            >
              {open === i.id ? "Close" : "Open"}
            </button>
          </div>
          {open === i.id && (
            <>
              <p className="sub2" style={{ margin: "4px 0 6px" }}>
                {i.does}
              </p>
              {i.detail.map((d) => (
                <p
                  key={d}
                  style={{
                    margin: "2px 0",
                    fontSize: 12.5,
                    wordBreak: "break-all",
                  }}
                >
                  {d}
                </p>
              ))}
              <p className="sub2" style={{ margin: "4px 0 0", fontSize: 12 }}>
                {i.last
                  ? `Last used ${new Date(i.last).toLocaleString("en-IN")}`
                  : "Not used yet"}
              </p>
              {i.id === "whatsapp" && clinicId && (
                <WhatsAppPanel clinicId={clinicId} />
              )}
              {i.id === "webhooks" && clinicId && (
                <WebhooksPanel clinicId={clinicId} />
              )}
              {i.id === "email" && clinicId && (
                <GmailPanel
                  url={`/v1/crm/console/${clinicId}/integrations/email`}
                  fallbackNote="Until then, emails come from the BB Gmail (if BB connected one)."
                />
              )}
              {i.id === "forms" && clinicId && (
                <FormsPanel clinicId={clinicId} />
              )}
              {i.id === "sheet" && clinicId && (
                <SheetsPanel clinicId={clinicId} />
              )}
              {i.id === "calcom" && clinicId && (
                <CalcomConnect
                  clinicId={clinicId}
                  own={i.detail[0]?.startsWith("Account: ") ?? false}
                  onDone={(list) => setData({ clinic: clinicId, list })}
                />
              )}
            </>
          )}
        </div>
      ))}
    </div>
  );
}

/** The clinic's own Cal.com: paste the API key (Cal.com → Settings → Developer → API keys). It is checked with
 * Cal.com and kept in Supabase Vault; it is never shown again. */
function CalcomConnect({
  clinicId,
  own,
  onDone,
}: {
  clinicId: string;
  own: boolean;
  onDone: (list: Integration[]) => void;
}) {
  const { toast } = useCrm();
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function send(method: "POST" | "DELETE") {
    setBusy(true);
    setError("");
    try {
      onDone(
        await api<Integration[]>(
          `/v1/crm/console/${clinicId}/integrations/calcom`,
          {
            method,
            body:
              method === "POST" ? JSON.stringify({ api_key: key }) : undefined,
          },
        ),
      );
      setKey("");
      toast(method === "POST" ? "Cal.com connected" : "Cal.com disconnected");
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Could not connect. Please try again.",
      );
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
      <p className="sub2" style={{ margin: "0 0 6px", fontSize: 12.5 }}>
        {own ? "Replace the API key" : "Connect the clinic's Cal.com"}: Cal.com
        → Settings → Developer → API keys. The key is checked with Cal.com, kept
        encrypted (Supabase Vault) and never shown again.
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input
          className="f"
          type="password"
          autoComplete="off"
          style={{ flex: 1, minWidth: 200 }}
          placeholder="cal_live_…"
          value={key}
          maxLength={300}
          onChange={(e) => setKey(e.target.value)}
        />
        <button
          className="btn"
          disabled={busy || key.trim().length < 10}
          onClick={() => send("POST")}
        >
          {busy ? "Checking…" : own ? "Replace key" : "Connect"}
        </button>
        {own && (
          <button
            className="btn g"
            disabled={busy}
            onClick={() => {
              if (
                window.confirm(
                  "Disconnect the clinic's Cal.com? Online consults stop using it.",
                )
              )
                void send("DELETE");
            }}
          >
            Disconnect
          </button>
        )}
      </div>
      {error && (
        <p className="warnbox" style={{ marginTop: 6 }}>
          {error}
        </p>
      )}
      {own && <OnlineSetup clinicId={clinicId} />}
    </div>
  );
}
