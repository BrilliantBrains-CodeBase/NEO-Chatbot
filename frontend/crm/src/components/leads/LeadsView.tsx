"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError, type LeadDetail, type LeadList } from "@/lib/api";
import LeadActions from "./LeadActions";

export const STAGE_LABEL: Record<string, [string, string]> = {
  new: ["New", "b-new"],
  follow_up: ["Follow Up", "b-fu"],
  booked: ["Booked", "b-bk"],
  visited: ["Visited", "b-vi"],
  lost: ["Lost", "b-lo"],
  invalid: ["Invalid", "b-in"],
};
const SOURCE: Record<string, string> = { chatbot: "Chatbot", meta_ads: "Meta Ads", google_ads: "Google Ads", manual: "Manual", whatsapp: "WhatsApp", website_form: "Website form" };
const EVENT: Record<string, string> = { contact: "Contacted", stage_change: "Stage changed", assigned: "Assigned", call: "Call", note: "Note", request: "Request", appointment: "Appointment" };

const ymd = (d: Date) => d.toLocaleDateString("en-CA"); // YYYY-MM-DD, the browser's day
const when = (iso: string) => new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
const errorText = (e: unknown) => (e instanceof ApiError ? e.message : "Could not load leads.");

function useDebounced(value: string, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function LeadsView() {
  const { clinic, me } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  // The stage tab and the open lead live in the address (?stage=booked&open=CL01-00003), so the menu
  // links and Add lead can open them.
  const router = useRouter();
  const params = useSearchParams();
  const asked = params.get("stage") ?? "";
  const stage = STAGE_LABEL[asked] ? asked : "";
  const openCode = params.get("open");
  const go = (s: string, code: string | null) => {
    const p = new URLSearchParams();
    if (s) p.set("stage", s);
    if (code) p.set("open", code);
    router.replace(p.size ? `/leads?${p}` : "/leads", { scroll: false });
  };
  const setStage = (s: string) => go(s, openCode);
  const [version, setVersion] = useState(0); // bumped after a change, to load the list again
  const [source, setSource] = useState("");
  // Leads created in this range (days, both included); empty = all time.
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  // A newly added lead is opened by its code: the list loads again to include it.
  const key = `${clinicId}|${stage}|${source}|${q}|${from}|${to}|${version}|${openCode}`;
  const [list, setList] = useState<{ key: string; d?: LeadList; error?: string }>({ key: "" });
  const [detail, setDetail] = useState<{ code: string; d?: LeadDetail; error?: string }>({ code: "" });

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    const p = new URLSearchParams({ clinic: clinicId, limit: "100" });
    if (stage) p.set("stage", stage);
    if (source) p.set("source", source);
    if (q) p.set("q", q);
    if (from) p.set("from", from);
    if (to) p.set("to", to);
    api<LeadList>(`/v1/crm/leads?${p}`).then(
      (d) => live && setList({ key, d }),
      (e) => live && setList({ key, error: errorText(e) }),
    );
    return () => {
      live = false;
    };
  }, [clinicId, stage, source, q, from, to, key]);

  function range(days: number | null) {
    if (days === null) {
      setFrom("");
      setTo("");
      return;
    }
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - (days - 1));
    setFrom(ymd(start));
    setTo(ymd(end));
  }
  const preset = (days: number | null) => {
    if (days === null) return !from && !to;
    const start = new Date();
    start.setDate(start.getDate() - (days - 1));
    return from === ymd(start) && to === ymd(new Date());
  };

  useEffect(() => {
    if (!openCode) return;
    let live = true;
    api<LeadDetail>(`/v1/crm/leads/${encodeURIComponent(openCode)}`).then(
      (d) => live && setDetail({ code: openCode, d }),
      (e) => live && setDetail({ code: openCode, error: errorText(e) }),
    );
    return () => {
      live = false;
    };
  }, [openCode]);

  function changed(d: LeadDetail) {
    setDetail({ code: d.code, d });
    setVersion((v) => v + 1);
  }

  const show = (code: string) => go(stage, code);
  const close = () => go(stage, null);
  const open: typeof detail | null = openCode ? (detail.code === openCode ? detail : { code: openCode }) : null;

  const d = list.key === key ? list.d : undefined;
  const error = list.key === key ? list.error : undefined;
  const all = d?.stages.reduce((n, s) => n + s.count, 0);
  const lead = open?.d;

  return (
    <>
      <div className="ph">
        <div>
          <h1>Leads</h1>
          <p>Every lead from chatbot, ads, calls and walk-ins.</p>
        </div>
      </div>
      <div className="tabs">
        <button className={stage ? "" : "on"} onClick={() => setStage("")}>
          All<span className="c">{all ?? "…"}</span>
        </button>
        {Object.entries(STAGE_LABEL).map(([k, [label]]) => (
          <button key={k} className={stage === k ? "on" : ""} onClick={() => setStage(k)}>
            {label}
            <span className="c">{d?.stages.find((s) => s.key === k)?.count ?? "…"}</span>
          </button>
        ))}
      </div>
      <div className="tools">
        <label className="search">
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name, phone, email or code" />
        </label>
        <div className="pills" style={{ margin: 0 }} aria-label="Created">
          {(
            [
              ["Today", 1],
              ["All time", null],
            ] as [string, number | null][]
          ).map(([label, days]) => (
            <button key={label} type="button" className={`pill${preset(days) ? " on" : ""}`} onClick={() => range(days)}>
              {label}
            </button>
          ))}
        </div>
        <input className="sel" type="date" aria-label="From" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} />
        <span className="sub2">to</span>
        <input className="sel" type="date" aria-label="To" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} />
        <select className="sel" value={source} onChange={(e) => setSource(e.target.value)} aria-label="Source">
          <option value="">All sources</option>
          {Object.entries(SOURCE).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </div>
      {error && <div className="warnbox">{error}</div>}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Lead</th>
              <th>Source</th>
              <th>Treatment</th>
              <th>Doctor</th>
              <th>Stage</th>
              <th>Assigned</th>
              <th>Last contact</th>
            </tr>
          </thead>
          <tbody>
            {!d && !error && (
              <tr>
                <td colSpan={7}>Loading…</td>
              </tr>
            )}
            {d && !d.items.length && (
              <tr>
                <td colSpan={7}>No leads match.</td>
              </tr>
            )}
            {d?.items.map((l) => (
              <tr key={l.code} onClick={() => show(l.code)} style={{ cursor: "pointer" }}>
                <td>
                  <div className="nm">{l.name}</div>
                  <div className="pn">
                    {l.code} · {l.phone ?? l.email}
                  </div>
                </td>
                <td>
                  {SOURCE[l.source] ?? l.source}
                  {l.campaign && <div className="pn">{l.campaign}</div>}
                </td>
                <td>{l.treatment ?? "—"}</td>
                <td>{l.doctor ?? "—"}</td>
                <td>
                  <span className={`badge ${STAGE_LABEL[l.stage]?.[1]}`}>{STAGE_LABEL[l.stage]?.[0] ?? l.stage}</span>
                </td>
                <td>{l.assigned ?? "Unassigned"}</td>
                <td>{when(l.last_contact_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {d && d.total > d.items.length && (
        <p className="sub2">
          Showing the latest {d.items.length} of {d.total}. Search to find others.
        </p>
      )}

      <div className={`ov${open ? " on" : ""}`} onClick={close} />
      <aside className={`dr${open ? " on" : ""}`} aria-hidden={!open}>
        {open && (
          <>
            <div className="dh">
              <div>
                <h2>{lead?.name ?? "…"}</h2>
                <p>
                  {open.code}
                  {lead && <span className={`badge ${STAGE_LABEL[lead.stage]?.[1]}`}>{STAGE_LABEL[lead.stage]?.[0]}</span>}
                </p>
              </div>
              <button className="x" onClick={close} aria-label="Close">
                ✕
              </button>
            </div>
            <div className="db">
              {open.error && <div className="warnbox">{open.error}</div>}
              {lead && (
                <>
                  <div className="kv">
                    {(
                      [
                        ["Phone", lead.phone],
                        ["Email", lead.email],
                        ["Source", `${SOURCE[lead.source] ?? lead.source}${lead.campaign ? " · " + lead.campaign : ""}`],
                        ["Treatment", lead.treatment],
                        ["Doctor", lead.doctor],
                        ["Type", lead.type === "online" ? "Online" : lead.type ? "In-clinic" : null],
                        ["Assigned", lead.assigned ?? "Unassigned"],
                        ["Contacts", String(lead.contacts)],
                        ["First contact", when(lead.created_at)],
                        ["Verified", lead.verified ? "Yes" : "No"],
                      ] as [string, string | null][]
                    ).map(([k, v]) => (
                      <div key={k}>
                        <span>{k}</span>
                        <b>{v || "—"}</b>
                      </div>
                    ))}
                  </div>
                  <LeadActions key={lead.code} lead={lead} clinicId={clinicId} onChange={changed} />
                  {lead.notes && (
                    <div className="sec">
                      <h4>NOTES</h4>
                      <p>{lead.notes}</p>
                    </div>
                  )}
                  <div className="sec">
                    <h4>TIMELINE</h4>
                    {lead.events.length ? (
                      <div className="tl">
                        {lead.events.map((e, i) => (
                          <div key={i}>
                            {EVENT[e.kind] ?? e.kind}
                            {typeof e.data.outcome === "string" && `: ${e.data.outcome.replace("_", " ")}`}
                            {typeof e.data.text === "string" && e.data.text && `: ${e.data.text}`}
                            {typeof e.data.to === "string" && ` to ${STAGE_LABEL[e.data.to]?.[0] ?? e.data.to}`}
                            <small>
                              {when(e.at)}
                              {e.by ? " · " + e.by : ""}
                            </small>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="sub2">Nothing yet.</p>
                    )}
                  </div>
                  <div className="sec">
                    <h4>LATEST CHAT</h4>
                    {lead.chat.length ? (
                      <div className="list">
                        {lead.chat.map((m, i) => (
                          <div className="li" key={i}>
                            <div className="x">
                              <b>{m.role === "bot" ? "Bot" : "Patient"}</b>
                              <span style={{ whiteSpace: "pre-wrap" }}>{m.text}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="sub2">No chat with this lead.</p>
                    )}
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </aside>
    </>
  );
}
