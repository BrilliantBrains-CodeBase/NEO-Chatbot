"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";

// A Gmail sender: a clinic's (Integrations → Email) or the BB Gmail (Login & security). Gmail address + a Google
// App password (kept encrypted in Supabase Vault, never shown again), a test email, and the last emails sent.

type Sent = {
  to: string;
  kind: string;
  ok: boolean;
  error: string | null;
  at: string;
};
type Sender = {
  connected: boolean;
  address: string | null;
  from_name: string;
  log: Sent[];
};

export default function GmailPanel({
  url,
  fallbackNote,
}: {
  url: string;
  fallbackNote?: string;
}) {
  const { me, toast } = useCrm();
  const [s, setS] = useState<Sender | null>(null);
  const [form, setForm] = useState({
    address: "",
    app_password: "",
    from_name: "",
  });
  const [testTo, setTestTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    api<Sender>(url).then(
      (x) => live && setS(x),
      (e) =>
        live && setError(e instanceof ApiError ? e.message : "Could not load."),
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
      setS(
        await api<Sender>(url + path, {
          method,
          body: body ? JSON.stringify(body) : undefined,
        }),
      );
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

  return (
    <div
      style={{
        marginTop: 10,
        borderTop: "1px solid var(--line)",
        paddingTop: 10,
        fontSize: "var(--fs-sec)",
      }}
    >
      {s?.connected ? (
        <p style={{ margin: "0 0 8px" }}>
          Sending from <b>{s.address}</b>
          {s.from_name ? ` as "${s.from_name}"` : ""}.{" "}
          <button
            className="btn g"
            disabled={busy}
            onClick={() => {
              if (
                window.confirm(
                  "Disconnect this Gmail? Emails then come from the fallback, or are not sent.",
                )
              )
                void call("", "DELETE", undefined, "Gmail disconnected");
            }}
          >
            Disconnect
          </button>
        </p>
      ) : (
        <p className="sub2" style={{ margin: "0 0 8px" }}>
          Not connected.{fallbackNote ? ` ${fallbackNote}` : ""}
        </p>
      )}
      <p className="sub2" style={{ margin: "0 0 6px" }}>
        {s?.connected ? "Connect again to change it. " : ""}Use the Gmail&apos;s{" "}
        <b>App password</b>: in that Google account turn on 2-Step Verification,
        then Google Account → Security → App passwords → create one (16
        letters). Your normal Gmail password will not work.
      </p>
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <input
          className="f"
          style={{ flex: 1, minWidth: 200 }}
          type="email"
          placeholder="clinic@gmail.com"
          value={form.address}
          onChange={(e) => setForm({ ...form, address: e.target.value })}
        />
        <input
          className="f"
          style={{ flex: 1, minWidth: 180 }}
          type="password"
          autoComplete="new-password"
          placeholder="App password (16 letters)"
          value={form.app_password}
          onChange={(e) => setForm({ ...form, app_password: e.target.value })}
        />
        <input
          className="f"
          style={{ flex: 1, minWidth: 140 }}
          placeholder="Sender name, e.g. Neo Follicle Hair Transplant"
          maxLength={80}
          value={form.from_name}
          onChange={(e) => setForm({ ...form, from_name: e.target.value })}
        />
        <button
          className="btn"
          disabled={
            busy ||
            !form.address.includes("@") ||
            form.app_password.replace(/\s/g, "").length < 16
          }
          onClick={async () => {
            if (await call("", "PUT", form, "Gmail connected"))
              setForm({ address: "", app_password: "", from_name: "" });
          }}
        >
          {s?.connected ? "Connect again" : "Connect Gmail"}
        </button>
      </div>
      {s?.connected && (
        <div className="row" style={{ gap: 8, flexWrap: "wrap", marginTop: 8 }}>
          <input
            className="f"
            style={{ flex: 1, minWidth: 200 }}
            type="email"
            placeholder={me?.email ?? "send a test to…"}
            value={testTo}
            onChange={(e) => setTestTo(e.target.value)}
          />
          <button
            className="btn g"
            disabled={busy}
            onClick={() =>
              void call(
                "/test",
                "POST",
                { to: testTo.trim() || me?.email },
                "Test email sent",
              )
            }
          >
            Send test
          </button>
        </div>
      )}
      {error && (
        <p className="warnbox" style={{ marginTop: 6 }}>
          {error}
        </p>
      )}
      {s && s.log.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <b>Last emails</b>
          {s.log.map((x, i) => (
            <p key={i} style={{ margin: "2px 0" }}>
              <span className={`badge ${x.ok ? "b-vi" : "b-in"}`}>
                {x.ok ? "Sent" : "Failed"}
              </span>{" "}
              {new Date(x.at).toLocaleString("en-IN")} · {x.kind} · {x.to}
              {x.error ? ` · ${x.error}` : ""}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
