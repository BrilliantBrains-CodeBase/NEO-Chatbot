"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";

// Integrations → Lead & Booking API: endpoints an outside system POSTs JSON to (key in the X-API-Key header).
// Paste a sample of that JSON, match its fields to ours, test, turn it on.

type Call = { at: string; ok: boolean; status_code: number; result: string; lead_code: string | null };
type Endpoint = {
  id: string;
  name: string;
  creates: "lead" | "booking";
  active: boolean;
  url: string;
  key: string;
  sample: unknown;
  paths: string[];
  mapping: Record<string, string>;
  keep_extra: boolean;
  calls_7d: number;
  log: Call[];
};
type Preview = {
  lead: Record<string, string>;
  booking: Record<string, string>;
  extra: Record<string, string>;
  problems: string[];
  makes: string;
};

// Ours, as the backend has them (crm_api.LEAD_FIELDS / BOOKING_FIELDS), each with words its path may contain.
const LEAD: [string, string, RegExp][] = [
  ["name", "Name *", /(^|\.)(full_?name|name|patient_?name|first_?name)$/i],
  ["phone", "Phone *", /phone|mobile|contact_?no|whatsapp|tel/i],
  ["email", "Email", /e-?mail/i],
  ["treatment", "Treatment", /treatment|service|procedure|concern|speciality/i],
  ["campaign", "Campaign", /campaign|utm_?campaign|ad_?set/i],
  ["source", "Source", /(^|\.)source$/i],
  ["city", "City", /city|location/i],
  ["notes", "Notes", /note|message|comment|query|remarks/i],
  ["external_id", "External id (no duplicates)", /(^|\.)(id|ref|reference|external_?id|lead_?id|order_?id)$/i],
];
const BOOKING: [string, string, RegExp][] = [
  ["date", "Appointment date", /date|day/i],
  ["time", "Appointment time", /time|slot|hour/i],
  ["doctor", "Doctor", /doctor|physician|consultant/i],
  ["type", "In-clinic or online", /type|mode|channel|visit/i],
  ["reason", "Reason / message", /reason|message|note|complaint/i],
];

/** First guesses: each of our fields to the first path that fits and is not taken yet. */
function guess(paths: string[], fields: [string, string, RegExp][], current: Record<string, string>) {
  const out = { ...current };
  const used = new Set(Object.values(out));
  for (const [f, , re] of fields) {
    if (out[f]) continue;
    const p = paths.find((x) => !used.has(x) && re.test(x));
    if (p) {
      out[f] = p;
      used.add(p);
    }
  }
  return out;
}

export default function ApiPanel({ clinicId }: { clinicId: string }) {
  const { toast } = useCrm();
  const url = `/v1/crm/console/${clinicId}/integrations/api`;
  const [list, setList] = useState<Endpoint[] | null>(null);
  const [name, setName] = useState("");
  const [creates, setCreates] = useState<"lead" | "booking">("booking");
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    api<Endpoint[]>(url).then(
      (l) => {
        if (!live) return;
        setList(l);
        if (l.length === 1) setOpen(l[0].id);
      },
      (e) => live && setError(e instanceof ApiError ? e.message : "Could not load the endpoints."),
    );
    return () => {
      live = false;
    };
  }, [url]);

  async function run(path: string, method: string, body?: object, done?: string) {
    setBusy(true);
    setError("");
    try {
      const l = await api<Endpoint[]>(`${url}${path}`, { method, body: body ? JSON.stringify(body) : undefined });
      setList(l);
      if (done) toast(done);
      return l;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save. Please try again.");
      return null;
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ig-block">
      {error && <div className="warnbox">{error}</div>}
      <form
        className="row"
        onSubmit={async (e) => {
          e.preventDefault();
          const l = await run("", "POST", { name, creates }, "Endpoint added: paste a sample payload next");
          if (l) {
            setName("");
            setOpen(l[l.length - 1]?.id ?? null);
          }
        }}
      >
        <input
          className="f"
          style={{ flex: 1, minWidth: 180 }}
          placeholder="Name, e.g. Practo, Landing page"
          value={name}
          maxLength={80}
          onChange={(e) => setName(e.target.value)}
        />
        <select className="f" aria-label="Each call makes" value={creates} onChange={(e) => setCreates(e.target.value as "lead" | "booking")}>
          <option value="booking">Lead + booking request</option>
          <option value="lead">Lead only</option>
        </select>
        <button className="btn" disabled={busy || !name.trim()}>
          Add endpoint
        </button>
      </form>
      {list?.length === 0 && <p className="sub2">No endpoints yet. Add one for each system that sends you data.</p>}
      {list?.map((e) => (
        <EndpointCard
          key={e.id}
          e={e}
          open={open === e.id}
          busy={busy}
          onToggle={() => setOpen(open === e.id ? null : e.id)}
          run={(path, method, body, done) => run(`/${e.id}${path}`, method, body, done)}
          testUrl={`${url}/${e.id}/test`}
        />
      ))}
    </div>
  );
}

function EndpointCard({
  e,
  open,
  busy,
  onToggle,
  run,
  testUrl,
}: {
  e: Endpoint;
  open: boolean;
  busy: boolean;
  onToggle: () => void;
  run: (path: string, method: string, body?: object, done?: string) => Promise<Endpoint[] | null>;
  testUrl: string;
}) {
  const { toast } = useCrm();
  const [showKey, setShowKey] = useState(false);
  const [text, setText] = useState(e.sample ? JSON.stringify(e.sample, null, 2) : "");
  const [creates, setCreates] = useState(e.creates);
  const [mapping, setMapping] = useState<Record<string, string>>(e.mapping);
  const [keep, setKeep] = useState(e.keep_extra);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [problem, setProblem] = useState("");
  const fields = creates === "booking" ? [...LEAD, ...BOOKING] : LEAD;
  // Compared by content: the saved matching comes back with its keys in another order.
  const same = (a: Record<string, string>, b: Record<string, string>) =>
    Object.keys(a).length === Object.keys(b).length && Object.entries(a).every(([k, v]) => b[k] === v);
  const changed = creates !== e.creates || keep !== e.keep_extra || !same(mapping, e.mapping);
  const copy = (v: string, what: string) =>
    navigator.clipboard.writeText(v).then(
      () => toast(`${what} copied`),
      () => toast("Select it and copy it"),
    );
  const sample = e.sample ? JSON.stringify(e.sample) : '{"name":"Asha Rao","phone":"9800000001"}';
  const curl = `curl -X POST "${e.url}" \\\n  -H "Content-Type: application/json" \\\n  -H "X-API-Key: ${showKey ? e.key : "YOUR_API_KEY"}" \\\n  -d '${sample}'`;

  async function readSample() {
    setProblem("");
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      setProblem("That is not valid JSON. Paste the exact body the other system sends.");
      return;
    }
    const l = await run("", "PUT", { sample: parsed }, "Sample saved: match its fields below");
    const now = l?.find((x) => x.id === e.id);
    if (now) setMapping(guess(now.paths, creates === "booking" ? [...LEAD, ...BOOKING] : LEAD, mapping));
  }

  async function test() {
    setProblem("");
    try {
      setPreview(await api<Preview>(testUrl, { method: "POST", body: JSON.stringify({}) }));
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : "Could not test.");
    }
  }

  return (
    <article className={`card wi-site${e.active ? "" : " pending"}`}>
      <div className="wi-site-h">
        <span className="wi-avatar" aria-hidden="true">
          {e.name.charAt(0).toUpperCase()}
        </span>
        <div className="wi-site-t">
          <b>{e.name}</b>
          <span className="sub2">
            {e.creates === "booking" ? "Lead + booking request" : "Lead only"} · {e.calls_7d} calls in 7 days
          </span>
        </div>
        <span className={`wi-pill ${e.active ? "live" : "off"}`}>
          <i />
          {e.active ? "On" : "Off"}
        </span>
        <button className="btn g sm" onClick={onToggle} aria-expanded={open}>
          {open ? "Close" : "Open"}
        </button>
      </div>
      {open && (
        <div className="ig-ep">
          <section>
            <h4>1. Address and key</h4>
            <div className="ig-kv">
              <span>POST</span>
              <code>{e.url}</code>
              <button className="lnk" onClick={() => copy(e.url, "Address")}>
                Copy
              </button>
              <span>X-API-Key</span>
              <code>{showKey ? e.key : "••••••••••••••••"}</code>
              <span className="row" style={{ gap: 8 }}>
                <button className="lnk" onClick={() => setShowKey(!showKey)}>
                  {showKey ? "Hide" : "Show"}
                </button>
                <button className="lnk" onClick={() => copy(e.key, "API key")}>
                  Copy
                </button>
              </span>
            </div>
            <button
              className="lnk"
              style={{ alignSelf: "flex-start" }}
              disabled={busy}
              onClick={() => {
                if (window.confirm(`Make a new key for ${e.name}? The old key stops working at once.`))
                  void run("/key", "POST", undefined, "New key made: update it in the other system");
              }}
            >
              Make a new key
            </button>
          </section>

          <section>
            <h4>2. Paste a sample payload</h4>
            <p className="sub2">The exact JSON the other system sends (their docs or a test call). Nested fields are fine.</p>
            <textarea
              className="f ig-json"
              rows={7}
              spellCheck={false}
              placeholder={'{\n  "name": "Asha Rao",\n  "phone": "9800000001",\n  "service": "PRP",\n  "date": "2026-11-10",\n  "time": "10:30"\n}'}
              value={text}
              onChange={(ev) => setText(ev.target.value)}
            />
            {problem && <div className="warnbox">{problem}</div>}
            <button className="btn g sm" style={{ alignSelf: "flex-start" }} disabled={busy || !text.trim()} onClick={readSample}>
              Read its fields
            </button>
          </section>

          {e.paths.length > 0 && (
            <section>
              <h4>3. Match its fields to ours</h4>
              <div className="row">
                <span className="sub2">Each call makes</span>
                <div className="seg" style={{ marginLeft: 0 }}>
                  <button type="button" className={creates === "booking" ? "on" : ""} onClick={() => setCreates("booking")}>
                    Lead + booking request
                  </button>
                  <button type="button" className={creates === "lead" ? "on" : ""} onClick={() => setCreates("lead")}>
                    Lead only
                  </button>
                </div>
              </div>
              <div className="ig-map">
                {fields.map(([f, label]) => (
                  <label key={f}>
                    <span>{label}</span>
                    <select
                      className="f"
                      value={mapping[f] ?? ""}
                      onChange={(ev) => {
                        const next = { ...mapping };
                        if (ev.target.value) next[f] = ev.target.value;
                        else delete next[f];
                        setMapping(next);
                      }}
                    >
                      <option value="">— not used —</option>
                      {e.paths.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              <label className="wi-switch">
                <input type="checkbox" checked={keep} onChange={(ev) => setKeep(ev.target.checked)} />
                <span />
                Keep the other fields on the lead as More information
              </label>
              <div className="row">
                <button
                  className="btn sm"
                  disabled={busy || !changed}
                  onClick={() =>
                    run("", "PUT", { creates, mapping, keep_extra: keep }, "Matching saved").then(() => setPreview(null))
                  }
                >
                  Save matching
                </button>
                <button className="btn g sm" disabled={busy || changed} onClick={test} title={changed ? "Save first" : ""}>
                  Test with the sample
                </button>
              </div>
              {preview && <PreviewBox p={preview} />}
            </section>
          )}

          <section>
            <h4>4. Turn it on</h4>
            <div className="row">
              <label className="wi-switch">
                <input
                  type="checkbox"
                  checked={e.active}
                  disabled={busy}
                  onChange={(ev) =>
                    run("", "PUT", { active: ev.target.checked }, ev.target.checked ? "Endpoint on: calls are taken" : "Endpoint off")
                  }
                />
                <span />
                {e.active ? "On: calls are taken" : "Off: calls are refused (403)"}
              </label>
              <button
                className="lnk"
                style={{ marginLeft: "auto", color: "var(--err)" }}
                disabled={busy}
                onClick={() => {
                  if (window.confirm(`Delete ${e.name}? Its address stops working at once.`))
                    void run("", "DELETE", undefined, "Endpoint deleted");
                }}
              >
                Delete endpoint
              </button>
            </div>
          </section>

          <section>
            <h4>Example call</h4>
            <pre className="wi-pre" title="Click to copy" onClick={() => copy(curl, "Example")}>
              <code>{curl}</code>
            </pre>
          </section>

          <section>
            <h4>Last calls</h4>
            {e.log.length ? (
              <ul className="ig-log">
                {e.log.map((c, k) => (
                  <li key={k}>
                    <span className={`badge ${c.ok ? "b-vi" : "b-in"}`}>{c.status_code}</span>
                    <span>{new Date(c.at).toLocaleString("en-IN")}</span>
                    <span className="sub2">{c.result}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="sub2">No calls yet.</p>
            )}
          </section>
        </div>
      )}
    </article>
  );
}

function PreviewBox({ p }: { p: Preview }) {
  const rows = (o: Record<string, string>) =>
    Object.entries(o).map(([k, v]) => (
      <div key={k}>
        <span>{k}</span>
        <b>{v || "—"}</b>
      </div>
    ));
  return (
    <div className="ig-preview">
      <b>{p.makes}</b>
      {p.problems.map((x) => (
        <div key={x} className="warnbox">
          {x}
        </div>
      ))}
      <div className="kv">{rows(p.lead)}</div>
      {Object.keys(p.booking).length > 0 && <div className="kv">{rows(p.booking)}</div>}
      {Object.keys(p.extra).length > 0 && (
        <>
          <span className="sub2">More information</span>
          <div className="kv">{rows(p.extra)}</div>
        </>
      )}
    </div>
  );
}
