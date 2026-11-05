"use client";

import Loading from "@/components/crm/Loading";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";

// Integrations → WhatsApp (Interakt). WhatsApp lets a business write first only with a template approved in the
// clinic's Interakt: for each message, its name, language and what fills each blank ({{1}}, {{2}} ...).

type Template = {
  name: string;
  language: string;
  values: string[];
  buttons: string[]; // what each "Visit website" button opens (not used for now)
  text: string; // the approved text, pasted for the preview
  on: boolean;
};
type State = {
  connected: boolean;
  templates: Record<string, Template>;
  purposes: Record<string, string>;
  values: Record<string, string>;
  sample: Record<string, string>; // what each blank would be
  links: Record<string, string>; // what a template button can open
  link_base: string; // the URL for each "Visit website" button in Interakt
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
      <Loading inline />
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
        fontSize: "var(--fs-sec)",
      }}
    >
      <p className="sub2" style={{ margin: "0 0 6px", fontSize: "var(--fs-small)" }}>
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
          <p className="sub2" style={{ margin: "0 0 8px", fontSize: "var(--fs-small)" }}>
            For each message: the template&apos;s <b>name</b> as approved in
            Interakt (e.g. request_received_v1, not its text), its language, and
            what fills each blank in order. The preview shows what each blank
            will be: compare it with the template&apos;s text in Interakt.
          </p>
          <div
            style={{
              display: "flex",
              gap: 8,
              alignItems: "center",
              marginBottom: 8,
            }}
          >
            Test phone
            <input
              className="f"
              placeholder="+91 98765 43210"
              maxLength={20}
              value={test.phone}
              onChange={(e) => setTest({ ...test, phone: e.target.value })}
            />
          </div>
          {Object.entries(state.purposes).map(([p, label]) => {
            const t = tpl[p];
            const ticked = (k: string) => t.values.indexOf(k);
            // The template's blanks ({{1}} … {{n}}) in the pasted text: the ticks must be exactly that many.
            const blanks = new Set((t.text || "").match(/\{\{\d+\}\}/g) ?? [])
              .size;
            const preview = (t.text || "").replace(
              /\{\{(\d+)\}\}/g,
              (all, n) => {
                const v = t.values[Number(n) - 1];
                return v ? state.sample[v] || "—" : all;
              },
            );
            return (
              <div
                key={p}
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
                  <b style={{ flex: 1 }}>{label}</b>
                  <div className="wf-seg">
                    <button
                      className={t.on ? "on" : ""}
                      onClick={() => put(p, { on: true })}
                    >
                      On
                    </button>
                    <button
                      className={!t.on ? "on" : ""}
                      onClick={() => put(p, { on: false })}
                    >
                      Off
                    </button>
                  </div>
                  <button
                    className="btn g"
                    disabled={
                      busy ||
                      !!draft ||
                      !t.name ||
                      !t.on ||
                      test.phone.replace(/\D/g, "").length < 10
                    }
                    title={
                      draft
                        ? "Save first"
                        : !test.phone
                          ? "Type the test phone above"
                          : "Send this one now"
                    }
                    onClick={() =>
                      call(
                        "/test",
                        "POST",
                        { purpose: p, phone: test.phone },
                        "Test sent: check that phone",
                      )
                    }
                  >
                    Send test
                  </button>
                </div>
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
                    placeholder="Template name, exactly as approved in Meta / Interakt"
                    maxLength={120}
                    value={t.name}
                    onChange={(e) => put(p, { name: e.target.value.trim() })}
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
                <p
                  className="sub2"
                  style={{ margin: "8px 0 4px", fontSize: "var(--fs-small)" }}
                >
                  Tick what to send, in the template&apos;s order: the first
                  tick is {"{{1}}"}, the next {"{{2}}"} …
                </p>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {Object.entries(state.values).map(([k, l]) => {
                    const n = ticked(k);
                    return (
                      <label
                        key={k}
                        className="pill"
                        style={{
                          display: "flex",
                          gap: 4,
                          alignItems: "center",
                          cursor: "pointer",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={n >= 0}
                          onChange={(e) =>
                            put(p, {
                              values: e.target.checked
                                ? [...t.values, k]
                                : t.values.filter((x) => x !== k),
                            })
                          }
                        />
                        {n >= 0 && <b>{`{{${n + 1}}}`}</b>}
                        {l}
                      </label>
                    );
                  })}
                </div>
                <textarea
                  rows={3}
                  maxLength={1024}
                  style={{ width: "100%", marginTop: 8, fontSize: "var(--fs-small)" }}
                  placeholder="Optional: paste the approved text (with {{1}}, {{2}} …) to see the message filled in"
                  value={t.text}
                  onChange={(e) => put(p, { text: e.target.value })}
                />
                {t.text && blanks !== t.values.length && (
                  <p className="warnbox" style={{ marginTop: 6 }}>
                    The template has {blanks} blank(s) but {t.values.length} are
                    ticked: WhatsApp refuses it. Tick exactly
                    {blanks}.
                  </p>
                )}
                {t.text ? (
                  <div
                    style={{
                      marginTop: 6,
                      padding: 8,
                      borderRadius: 8,
                      background: "#E7FCE3",
                      whiteSpace: "pre-wrap",
                      fontSize: "var(--fs-small)",
                    }}
                  >
                    {preview}
                  </div>
                ) : (
                  t.values.length > 0 && (
                    <p
                      className="sub2"
                      style={{ margin: "6px 0 0", fontSize: "var(--fs-small)" }}
                    >
                      {t.values
                        .map(
                          (v, i) => `{{${i + 1}}} = ${state.sample[v] || "—"}`,
                        )
                        .join("  ·  ")}
                    </p>
                  )
                )}
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

          <SendMessage
            clinicId={clinicId}
            purposes={state.purposes}
            ready={Object.fromEntries(
              Object.entries(state.templates).map(([k, t]) => [
                k,
                !!t.name && t.on,
              ]),
            )}
            disabled={busy || !!draft}
            onSent={(s) => {
              setState(s);
              toast("Message sent: see Last messages");
            }}
          />
          <h3 style={{ margin: "14px 0 4px" }}>Last messages</h3>
          {state.log.length ? (
            state.log.map((x, i) => (
              <p key={i} style={{ margin: "2px 0", fontSize: "var(--fs-small)" }}>
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

type Lead = { code: string; name: string; phone: string | null };

/** One message now, to a CRM contact (their real details fill the template) or to a typed number (sample
 * values). One at a time, never in bulk. */
function SendMessage({
  clinicId,
  purposes,
  ready,
  disabled,
  onSent,
}: {
  clinicId: string;
  purposes: Record<string, string>;
  ready: Record<string, boolean>;
  disabled: boolean;
  onSent: (s: State) => void;
}) {
  const [purpose, setPurpose] = useState("inclinic_confirmed");
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Lead[]>([]);
  const [lead, setLead] = useState<Lead | null>(null);
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (q.trim().length < 2) return;
    let live = true;
    const t = setTimeout(() => {
      api<{ items: Lead[] }>(
        `/v1/crm/leads?clinic=${clinicId}&q=${encodeURIComponent(q.trim())}&limit=8`,
      ).then(
        (r) => live && setFound(r.items),
        () => live && setFound([]),
      );
    }, 300);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [q, clinicId]);

  const number = lead ? lead.phone : phone;
  return (
    <div className="card" style={{ marginTop: 14, padding: 10 }}>
      <h3 style={{ margin: "0 0 4px" }}>Send a message</h3>
      <p className="sub2" style={{ margin: "0 0 8px", fontSize: "var(--fs-small)" }}>
        To one CRM contact (their name, latest appointment and booking ID fill
        the template) or to a typed number (sample values). One at a time.
      </p>
      <div
        style={{
          display: "flex",
          gap: 8,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <select
          className="sel"
          value={purpose}
          onChange={(e) => setPurpose(e.target.value)}
        >
          {Object.entries(purposes).map(([k, l]) => (
            <option key={k} value={k} disabled={!ready[k]}>
              {l.split(" (")[0]}
              {ready[k] ? "" : " (not set / off)"}
            </option>
          ))}
        </select>
        {lead ? (
          <span
            className="pill"
            style={{ display: "flex", gap: 6, alignItems: "center" }}
          >
            <b>{lead.name}</b> {lead.phone ?? "no phone"} · {lead.code}
            <button aria-label="Choose another" onClick={() => setLead(null)}>
              ✕
            </button>
          </span>
        ) : (
          <div style={{ position: "relative", flex: 1, minWidth: 220 }}>
            <input
              className="f"
              style={{ width: "100%" }}
              placeholder="Search a contact: name, phone or lead code"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            {q.trim().length >= 2 && found.length > 0 && (
              <div
                className="card"
                style={{
                  position: "absolute",
                  zIndex: 5,
                  left: 0,
                  right: 0,
                  padding: 4,
                }}
              >
                {found.map((l) => (
                  <button
                    key={l.code}
                    className="pill"
                    style={{
                      display: "block",
                      width: "100%",
                      textAlign: "left",
                      marginBottom: 2,
                    }}
                    onClick={() => {
                      setLead(l);
                      setQ("");
                      setFound([]);
                    }}
                  >
                    {l.name} · {l.phone ?? "no phone"} · {l.code}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {!lead && (
          <input
            className="f"
            style={{ width: 170 }}
            placeholder="or a number: +91 98765 43210"
            maxLength={20}
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        )}
        <button
          className="btn"
          disabled={
            disabled ||
            busy ||
            !ready[purpose] ||
            !number ||
            number.replace(/\D/g, "").length < 10
          }
          onClick={async () => {
            if (
              !window.confirm(
                `Send "${purposes[purpose].split(" (")[0]}" to ${lead ? lead.name : ""} ${number}?`,
              )
            )
              return;
            setBusy(true);
            setError("");
            try {
              onSent(
                await api<State>(
                  `/v1/crm/console/${clinicId}/integrations/whatsapp/send`,
                  {
                    method: "POST",
                    body: JSON.stringify({
                      purpose,
                      lead_code: lead?.code ?? null,
                      phone: lead ? null : phone,
                    }),
                  },
                ),
              );
            } catch (e) {
              setError(e instanceof ApiError ? e.message : "Could not send.");
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Sending…" : "Send"}
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
