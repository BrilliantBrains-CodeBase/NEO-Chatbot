"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";

// Integrations → WhatsApp (Interakt). WhatsApp lets a business write first only with a template approved in the
// clinic's Interakt: for each message, its name, language and what fills each blank ({{1}}, {{2}} ...).

type Template = {
  name: string;
  language: string;
  values: string[];
  on: boolean;
};
type State = {
  connected: boolean;
  templates: Record<string, Template>;
  purposes: Record<string, string>;
  values: Record<string, string>;
  log: {
    purpose: string;
    to_phone: string;
    ok: boolean;
    error: string | null;
    at: string;
  }[];
};

export default function WhatsAppPanel({ clinicId }: { clinicId: string }) {
  const { toast } = useCrm();
  const [state, setState] = useState<State | null>(null);
  const [draft, setDraft] = useState<Record<string, Template> | null>(null);
  const [key, setKey] = useState("");
  const [test, setTest] = useState({
    purpose: "inclinic_confirmed",
    phone: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const url = `/v1/crm/console/${clinicId}/integrations/whatsapp`;

  useEffect(() => {
    let live = true;
    api<State>(url).then(
      (s) => live && setState(s),
      (e) =>
        live &&
        setError(
          e instanceof ApiError ? e.message : "Could not load WhatsApp.",
        ),
    );
    return () => {
      live = false;
    };
  }, [url]);

  async function call(
    path: string,
    method: string,
    body: object | undefined,
    done: string,
  ) {
    setBusy(true);
    setError("");
    try {
      setState(
        await api<State>(url + path, {
          method,
          body: body ? JSON.stringify(body) : undefined,
        }),
      );
      setDraft(null);
      toast(done);
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

  if (!state)
    return error ? (
      <p className="warnbox">{error}</p>
    ) : (
      <p className="sub2">Loading…</p>
    );
  const tpl = draft ?? state.templates;
  const put = (p: string, patch: Partial<Template>) =>
    setDraft({ ...tpl, [p]: { ...tpl[p], ...patch } });

  return (
    <div
      style={{
        marginTop: 10,
        borderTop: "1px solid var(--line)",
        paddingTop: 10,
        fontSize: 13,
      }}
    >
      <p className="sub2" style={{ margin: "0 0 6px", fontSize: 12.5 }}>
        {state.connected
          ? "Replace the Interakt API key"
          : "Connect the clinic's Interakt"}
        : Interakt → Settings → Developer Setting. Kept encrypted (Supabase
        Vault), never shown again; checked by the first message.
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input
          className="f"
          type="password"
          autoComplete="off"
          style={{ flex: 1, minWidth: 200 }}
          placeholder="Interakt API key"
          value={key}
          maxLength={300}
          onChange={(e) => setKey(e.target.value)}
        />
        <button
          className="btn"
          disabled={busy || key.trim().length < 10}
          onClick={async () => {
            if (
              await call(
                "",
                "POST",
                { api_key: key.trim() },
                "Interakt connected",
              )
            )
              setKey("");
          }}
        >
          {state.connected ? "Replace key" : "Connect"}
        </button>
        {state.connected && (
          <button
            className="btn g"
            disabled={busy}
            onClick={() => {
              if (
                window.confirm(
                  "Disconnect Interakt? No WhatsApp messages are sent after this.",
                )
              )
                void call("", "DELETE", undefined, "Interakt disconnected");
            }}
          >
            Disconnect
          </button>
        )}
      </div>

      {state.connected && (
        <>
          <h3 style={{ margin: "14px 0 4px" }}>Messages</h3>
          <p className="sub2" style={{ margin: "0 0 8px", fontSize: 12.5 }}>
            For each message: the template&apos;s name exactly as approved in
            Interakt, its language, and what fills each blank in order (
            {"{{1}}"}, {"{{2}}"} …).
          </p>
          {Object.entries(state.purposes).map(([p, label]) => {
            const t = tpl[p];
            return (
              <div
                key={p}
                className="card"
                style={{ marginBottom: 8, padding: 10 }}
              >
                <label
                  style={{
                    display: "flex",
                    gap: 6,
                    alignItems: "center",
                    fontWeight: 600,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={t.on && !!t.name}
                    onChange={(e) => put(p, { on: e.target.checked })}
                  />
                  {label}
                </label>
                <div
                  style={{
                    display: "flex",
                    gap: 8,
                    flexWrap: "wrap",
                    marginTop: 6,
                  }}
                >
                  <input
                    className="f"
                    style={{ flex: 2, minWidth: 180 }}
                    placeholder="Template name in Interakt"
                    maxLength={120}
                    value={t.name}
                    onChange={(e) => put(p, { name: e.target.value })}
                  />
                  <input
                    className="f"
                    style={{ width: 80 }}
                    placeholder="en"
                    maxLength={5}
                    value={t.language}
                    onChange={(e) => put(p, { language: e.target.value })}
                  />
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: 6,
                    flexWrap: "wrap",
                    marginTop: 6,
                    alignItems: "center",
                  }}
                >
                  {t.values.map((v, i) => (
                    <span
                      key={i}
                      style={{ display: "flex", gap: 2, alignItems: "center" }}
                    >
                      <span className="sub2">{`{{${i + 1}}}`}</span>
                      <select
                        className="sel"
                        value={v}
                        onChange={(e) =>
                          put(p, {
                            values: t.values.map((x, k) =>
                              k === i ? e.target.value : x,
                            ),
                          })
                        }
                      >
                        {Object.entries(state.values).map(([k, l]) => (
                          <option key={k} value={k}>
                            {l}
                          </option>
                        ))}
                      </select>
                      <button
                        aria-label="Remove"
                        onClick={() =>
                          put(p, { values: t.values.filter((_, k) => k !== i) })
                        }
                      >
                        ✕
                      </button>
                    </span>
                  ))}
                  {t.values.length < 10 && (
                    <button
                      className="pill"
                      onClick={() => put(p, { values: [...t.values, "name"] })}
                    >
                      + Blank
                    </button>
                  )}
                </div>
              </div>
            );
          })}
          {draft && (
            <button
              className="btn"
              disabled={busy}
              onClick={() => call("/templates", "PUT", draft, "Messages saved")}
            >
              Save messages
            </button>
          )}

          <h3 style={{ margin: "14px 0 4px" }}>Send a test</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select
              className="sel"
              value={test.purpose}
              onChange={(e) => setTest({ ...test, purpose: e.target.value })}
            >
              {Object.entries(state.purposes).map(([p, l]) => (
                <option key={p} value={p}>
                  {l.split(" (")[0]}
                </option>
              ))}
            </select>
            <input
              className="f"
              placeholder="+91 98765 43210"
              maxLength={20}
              value={test.phone}
              onChange={(e) => setTest({ ...test, phone: e.target.value })}
            />
            <button
              className="btn g"
              disabled={
                busy || !!draft || test.phone.replace(/\D/g, "").length < 10
              }
              title={draft ? "Save the messages first" : ""}
              onClick={() =>
                call("/test", "POST", test, "Test sent: check that phone")
              }
            >
              Send test
            </button>
          </div>

          <h3 style={{ margin: "14px 0 4px" }}>Last messages</h3>
          {state.log.length ? (
            state.log.map((x, i) => (
              <p key={i} style={{ margin: "2px 0", fontSize: 12.5 }}>
                <span className={`badge ${x.ok ? "b-vi" : "b-in"}`}>
                  {x.ok ? "Sent" : "Not sent"}
                </span>{" "}
                {new Date(x.at).toLocaleString("en-IN")} ·{" "}
                {state.purposes[x.purpose]?.split(" (")[0] ?? x.purpose} ·{" "}
                {x.to_phone}
                {x.error ? ` · ${x.error.slice(0, 100)}` : ""}
              </p>
            ))
          ) : (
            <p className="sub2">Nothing sent yet.</p>
          )}
        </>
      )}
      {error && (
        <p className="warnbox" style={{ marginTop: 6 }}>
          {error}
        </p>
      )}
    </div>
  );
}
