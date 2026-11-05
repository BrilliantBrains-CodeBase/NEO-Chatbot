"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";

// Integrations → Webhooks. Send: CRM events as JSON to another system (signed X-Neo-Signature, retried, logged).
// Receive: a private address another system POSTs leads to as JSON.

type LogLine = {
  event: string;
  attempt: number;
  ok: boolean;
  status_code: number | null;
  error: string | null;
  at: string;
};
type Hook = {
  id: string;
  direction: "send" | "receive";
  name: string;
  url: string | null;
  events: string[];
  active: boolean;
  log: LogLine[];
};

const EVENTS: [string, string][] = [
  ["lead_new", "New lead"],
  ["booking_request", "Booking request"],
  ["callback_request", "Call back request"],
  ["appointment_confirmed", "Appointment confirmed"],
];

export default function WebhooksPanel({ clinicId }: { clinicId: string }) {
  const { toast } = useCrm();
  const [hooks, setHooks] = useState<Hook[] | null>(null);
  const [kind, setKind] = useState<"send" | "receive">("send");
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [events, setEvents] = useState<string[]>(["lead_new"]);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const url = `/v1/crm/console/${clinicId}/integrations/webhooks`;

  useEffect(() => {
    let live = true;
    api<Hook[]>(url).then(
      (h) => live && setHooks(h),
      (e) =>
        live &&
        setError(
          e instanceof ApiError ? e.message : "Could not load the webhooks.",
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
      setHooks(
        await api<Hook[]>(url + path, {
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
      {hooks?.map((h) => (
        <div
          key={h.id}
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
            <span
              className={`badge ${h.direction === "send" ? "b-on" : "b-bk"}`}
            >
              {h.direction === "send" ? "Send" : "Receive"}
            </span>
            <b style={{ flex: 1 }}>{h.name}</b>
            {h.direction === "send" && (
              <button
                className="btn g"
                disabled={busy}
                onClick={() =>
                  call(`/${h.id}/test`, "POST", undefined, "Test sent")
                }
              >
                Send test
              </button>
            )}
            <button
              className="btn g"
              onClick={() => setOpen(open === h.id ? null : h.id)}
            >
              {open === h.id ? "Close" : "Open"}
            </button>
            <button
              className="btn g"
              disabled={busy}
              onClick={() => {
                if (window.confirm(`Remove "${h.name}"?`))
                  void call(`/${h.id}`, "DELETE", undefined, "Webhook removed");
              }}
            >
              Remove
            </button>
          </div>
          {open === h.id && (
            <div style={{ marginTop: 8, fontSize: "var(--fs-small)" }}>
              {h.direction === "send" ? (
                <>
                  <p style={{ margin: "0 0 4px", wordBreak: "break-all" }}>
                    To: {h.url}
                  </p>
                  <p className="sub2" style={{ margin: "0 0 6px" }}>
                    Events:{" "}
                    {h.events
                      .map((e) => EVENTS.find(([k]) => k === e)?.[1] ?? e)
                      .join(", ")}
                    . Each POST is JSON, signed in the X-Neo-Signature header
                    (sha256), and retried up to 3 times.
                  </p>
                  {h.log.length ? (
                    h.log.map((x, i) => (
                      <p key={i} style={{ margin: "2px 0" }}>
                        <span className={`badge ${x.ok ? "b-vi" : "b-in"}`}>
                          {x.ok ? "Sent" : "Failed"}
                        </span>{" "}
                        {new Date(x.at).toLocaleString("en-IN")} · {x.event} ·
                        try {x.attempt}
                        {x.status_code ? ` · ${x.status_code}` : ""}
                        {x.error ? ` · ${x.error.slice(0, 80)}` : ""}
                      </p>
                    ))
                  ) : (
                    <p className="sub2">Nothing sent yet.</p>
                  )}
                </>
              ) : (
                <>
                  <p className="sub2" style={{ margin: "0 0 4px" }}>
                    POST a lead as JSON to this private address, e.g.{" "}
                    <code>
                      {
                        '{"name": "…", "phone": "…", "email": "…", "treatment": "…", "campaign": "…", "notes": "…"}'
                      }
                    </code>
                    . Other keys are kept in the lead&apos;s notes. Keep it
                    private.
                  </p>
                  <textarea
                    readOnly
                    rows={2}
                    value={h.url ?? ""}
                    style={{
                      width: "100%",
                      fontFamily: "ui-monospace, monospace",
                      fontSize: "var(--fs-small)",
                    }}
                    onFocus={(e) => e.target.select()}
                  />
                  <button
                    className="btn"
                    style={{ marginTop: 4 }}
                    onClick={() =>
                      navigator.clipboard.writeText(h.url ?? "").then(
                        () => toast("Address copied"),
                        () => toast("Select the address and copy it"),
                      )
                    }
                  >
                    Copy address
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      ))}
      <div className="card" style={{ padding: 10 }}>
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
            value={kind}
            onChange={(e) => setKind(e.target.value as "send" | "receive")}
          >
            <option value="send">Send events</option>
            <option value="receive">Receive leads</option>
          </select>
          <input
            className="f"
            style={{ flex: 1, minWidth: 160 }}
            placeholder="Name, e.g. Zapier"
            maxLength={80}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          {kind === "send" && (
            <input
              className="f"
              style={{ flex: 2, minWidth: 220 }}
              placeholder="https://their-address"
              maxLength={600}
              value={address}
              onChange={(e) => setAddress(e.target.value)}
            />
          )}
        </div>
        {kind === "send" && (
          <div
            style={{
              display: "flex",
              gap: 12,
              flexWrap: "wrap",
              marginTop: 6,
              fontSize: "var(--fs-sec)",
            }}
          >
            {EVENTS.map(([k, label]) => (
              <label
                key={k}
                style={{ display: "flex", gap: 4, alignItems: "center" }}
              >
                <input
                  type="checkbox"
                  checked={events.includes(k)}
                  onChange={(e) =>
                    setEvents(
                      e.target.checked
                        ? [...events, k]
                        : events.filter((x) => x !== k),
                    )
                  }
                />
                {label}
              </label>
            ))}
          </div>
        )}
        <button
          className="btn"
          style={{ marginTop: 8 }}
          disabled={
            busy ||
            !name.trim() ||
            (kind === "send" && (!address.trim() || !events.length))
          }
          onClick={async () => {
            const body = {
              direction: kind,
              name: name.trim(),
              url: kind === "send" ? address.trim() : null,
              events,
            };
            if (await call("", "POST", body, "Webhook added")) {
              setName("");
              setAddress("");
            }
          }}
        >
          Add webhook
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
