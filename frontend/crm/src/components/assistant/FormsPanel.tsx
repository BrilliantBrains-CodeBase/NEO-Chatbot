"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";

// Integrations → Website forms: the clinic's own forms on its website and landing pages send each submission
// to the form's private address (one line for the site's developer, or the address for a form builder). The
// first submission shows the form's fields; staff map them to ours and turn the form on.

type Submission = { at: string; ok: boolean; result: string };
type Form = {
  id: string;
  name: string;
  active: boolean;
  fields: string[];
  sample: string[];
  mapping: Record<string, string>;
  last_seen_at: string | null;
  log: Submission[];
};

/** The line the site's developer adds next to the code that already sends the form. */
const line = (link: string) =>
  `fetch("${link}", {\n  method: "POST", headers: { "Content-Type": "text/plain;charset=utf-8" }, body: JSON.stringify(data)\n});`;

export default function FormsPanel({ clinicId }: { clinicId: string }) {
  const { toast } = useCrm();
  const [forms, setForms] = useState<Form[] | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [name, setName] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [link, setLink] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const url = `/v1/crm/console/${clinicId}/integrations/forms`;

  useEffect(() => {
    let live = true;
    Promise.all([
      api<Form[]>(url),
      api<Record<string, string>>("/v1/crm/console/integrations/sheet-fields"),
    ]).then(
      ([f, ours]) => {
        if (!live) return;
        setForms(f);
        setFields(ours);
      },
      (e) =>
        live &&
        setError(
          e instanceof ApiError ? e.message : "Could not load the forms.",
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
      setForms(
        await api<Form[]>(url + path, {
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

  async function show(f: Form) {
    if (open === f.id) return setOpen(null);
    setOpen(f.id);
    setDraft(f.mapping);
    if (!link[f.id]) {
      try {
        const got = await api<{ link: string }>(`${url}/${f.id}/link`);
        setLink((l) => ({ ...l, [f.id]: got.link }));
      } catch {
        setError("Could not load the form's address.");
      }
    }
  }

  const copy = (text: string, what: string) =>
    navigator.clipboard.writeText(text).then(
      () => toast(`${what} copied`),
      () => toast(`Select the ${what.toLowerCase()} and copy it`),
    );

  const code = {
    width: "100%",
    fontFamily: "ui-monospace, monospace",
    fontSize: "var(--fs-small)",
  };

  return (
    <div
      style={{
        marginTop: 10,
        borderTop: "1px solid var(--line)",
        paddingTop: 10,
      }}
    >
      {forms?.map((f) => (
        <div
          key={f.id}
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
            <span className={`badge ${f.active ? "b-vi" : "b-in"}`}>
              {f.active ? "On" : "Off"}
            </span>
            <b style={{ flex: 1 }}>{f.name}</b>
            <button className="btn g" onClick={() => void show(f)}>
              {open === f.id ? "Close" : "Open"}
            </button>
            <button
              className="btn g"
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    `Remove "${f.name}"? Its address stops working at once.`,
                  )
                )
                  void call(`/${f.id}`, "DELETE", undefined, "Form removed");
              }}
            >
              Remove
            </button>
          </div>
          {open === f.id && (
            <div style={{ marginTop: 8, fontSize: "var(--fs-small)" }}>
              <p style={{ margin: "0 0 4px" }}>
                <b>1. Send the form here.</b>{" "}
                <span className="sub2">
                  The website&apos;s developer adds this line next to the code
                  that already sends the form (<code>data</code> = the
                  form&apos;s values). Keep it private.
                </span>
              </p>
              <textarea
                readOnly
                rows={4}
                value={link[f.id] ? line(link[f.id]) : "Loading…"}
                style={code}
                onFocus={(e) => e.target.select()}
              />
              <div className="row" style={{ gap: 6, margin: "4px 0 10px" }}>
                <button
                  className="btn"
                  disabled={!link[f.id]}
                  onClick={() => void copy(line(link[f.id]), "Code")}
                >
                  Copy code
                </button>
                <button
                  className="btn g"
                  disabled={!link[f.id]}
                  onClick={() => void copy(link[f.id], "Address")}
                >
                  Copy address only
                </button>
                <span className="sub2">
                  Form builders (Elementor, WPForms, Unbounce…): paste the
                  address in their &quot;send to URL / webhook&quot; setting.
                </span>
              </div>

              <p style={{ margin: "0 0 4px" }}>
                <b>2. Match its fields to ours.</b>{" "}
                <span className="sub2">
                  Send one test from the form first: its fields appear here.
                </span>
              </p>
              {f.fields.length === 0 ? (
                <p className="sub2">No submission yet.</p>
              ) : (
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <tbody>
                    {f.fields.map((k, i) => (
                      <tr key={k}>
                        <td style={{ padding: "3px 6px 3px 0" }}>
                          <b>{k}</b>
                          <div className="sub2" style={{ fontSize: "var(--fs-small)" }}>
                            e.g. {f.sample[i] || "(empty)"}
                          </div>
                        </td>
                        <td style={{ padding: "3px 0", width: 200 }}>
                          <select
                            className="sel"
                            value={draft[k] ?? "skip"}
                            onChange={(e) =>
                              setDraft({ ...draft, [k]: e.target.value })
                            }
                          >
                            <option value="skip">
                              Not used (goes in notes)
                            </option>
                            {Object.entries(fields).map(([v, label]) => (
                              <option key={v} value={v}>
                                {label}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <div className="row" style={{ gap: 6, margin: "8px 0 10px" }}>
                <button
                  className="btn"
                  disabled={busy || !f.fields.length}
                  onClick={() =>
                    void call(
                      `/${f.id}`,
                      "PUT",
                      { active: true, mapping: draft },
                      "Saved: submissions now become leads",
                    )
                  }
                >
                  Save and turn on
                </button>
                {f.active && (
                  <button
                    className="btn g"
                    disabled={busy}
                    onClick={() =>
                      void call(
                        `/${f.id}`,
                        "PUT",
                        { active: false, mapping: draft },
                        "Turned off",
                      )
                    }
                  >
                    Turn off
                  </button>
                )}
              </div>

              <p style={{ margin: "0 0 4px" }}>
                <b>Recent submissions</b>
              </p>
              {f.log.length ? (
                f.log.map((x, i) => (
                  <p key={i} style={{ margin: "2px 0" }}>
                    <span className={`badge ${x.ok ? "b-vi" : "b-in"}`}>
                      {x.ok ? "Lead" : "Not a lead"}
                    </span>{" "}
                    {new Date(x.at).toLocaleString("en-IN")} · {x.result}
                  </p>
                ))
              ) : (
                <p className="sub2">Nothing received yet.</p>
              )}
            </div>
          )}
        </div>
      ))}
      <div className="card" style={{ padding: 10 }}>
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          <input
            className="f"
            style={{ flex: 1, minWidth: 200 }}
            placeholder="Form name, e.g. Book appointment page"
            maxLength={80}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button
            className="btn"
            disabled={busy || !name.trim()}
            onClick={async () => {
              if (await call("", "POST", { name: name.trim() }, "Form added"))
                setName("");
            }}
          >
            Add form
          </button>
        </div>
      </div>
      {error && (
        <p className="warnbox" style={{ marginTop: 6 }}>
          {error}
        </p>
      )}
    </div>
  );
}
