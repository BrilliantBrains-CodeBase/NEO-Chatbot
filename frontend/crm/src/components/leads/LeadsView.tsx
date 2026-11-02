"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import Icon from "@/components/crm/Icon";
import { api, apiBlob, ApiError, saveFile, type LeadDetail, type LeadList } from "@/lib/api";
import ImportLeadsForm from "./ImportLeadsForm";
import LeadActions from "./LeadActions";

const PAGE_SIZE = 30;
const REFRESH_MS = 30_000; // new leads from the chatbot and forms appear by themselves

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
  const { clinic, me, toast, openModal } = useCrm();
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
  const askedQ = params.get("q"); // the top bar's search
  const [treatment, setTreatment] = useState("");
  const [search, setSearch] = useState(askedQ ?? "");
  const [seenQ, setSeenQ] = useState(askedQ);
  if (askedQ !== seenQ) {
    setSeenQ(askedQ);
    if (askedQ !== null) setSearch(askedQ);
  }
  const q = useDebounced(search.trim());
  const [page, setPage] = useState(1);
  // The leads ticked for Export (across pages), or every lead matching the filters.
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [pickedAll, setPickedAll] = useState(false);
  const clearPicked = () => {
    setPicked(new Set());
    setPickedAll(false);
  };
  const filters = `${clinicId}|${stage}|${source}|${treatment}|${q}|${from}|${to}`;
  const [seenFilters, setSeenFilters] = useState(filters);
  if (filters !== seenFilters) {
    setSeenFilters(filters);
    setPage(1);
    clearPicked(); // what is ticked always belongs to the list on screen
  }
  // A newly added lead is opened by its code: the list loads again to include it.
  const key = `${filters}|${page}|${version}|${openCode}`;
  const shown = new URLSearchParams();
  if (stage) shown.set("stage", stage);
  if (source) shown.set("source", source);
  if (treatment) shown.set("treatment", treatment);
  if (q) shown.set("q", q);
  if (from) shown.set("from", from);
  if (to) shown.set("to", to);
  const filterQuery = shown.toString();
  const listUrl = `/v1/crm/leads?clinic=${clinicId}&limit=${PAGE_SIZE}&offset=${(page - 1) * PAGE_SIZE}&${filterQuery}`;
  const [list, setList] = useState<{ key: string; d?: LeadList; error?: string }>({ key: "" });
  const [detail, setDetail] = useState<{ code: string; d?: LeadDetail; error?: string }>({ code: "" });

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<LeadList>(listUrl).then(
      (d) => live && setList({ key, d }),
      (e) => live && setList({ key, error: errorText(e) }),
    );
    return () => {
      live = false;
    };
  }, [clinicId, listUrl, key]);

  // Quietly, without "Loading…": the same list again while the tab is in view.
  useEffect(() => {
    if (!clinicId) return;
    const timer = setInterval(() => {
      if (document.hidden) return;
      api<LeadList>(listUrl).then(
        (d) => setList((now) => (now.key === key ? { key, d } : now)),
        () => {},
      );
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [clinicId, listUrl, key]);

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
  const pages = d ? Math.max(1, Math.ceil(d.total / PAGE_SIZE)) : 1;
  if (d && page > pages) setPage(pages); // the last page emptied (e.g. leads moved to another stage)
  // A lead opened from outside the page shown (just added): the newest are on the first page.
  if (d && openCode && page > 1 && !d.items.some((l) => l.code === openCode)) setPage(1);
  const clinicRole = me?.clinics.find((c) => c.id === clinicId)?.role;
  const canBulk = !!clinicId && (me?.bb_admin || clinicRole === "clinic_manager");
  const [exporting, setExporting] = useState(false);

  function goPage(n: number) {
    setPage(n);
    document.querySelector(".crm .page")?.scrollTo(0, 0);
  }

  const onPage = d?.items.map((l) => l.code) ?? [];
  const pageTicked = onPage.length > 0 && onPage.every((c) => picked.has(c));
  const pickedCount = pickedAll ? (d?.total ?? 0) : picked.size;

  function tick(code: string, on: boolean) {
    // Unticking one out of "all": everything else on this screen stays ticked.
    const next = new Set(pickedAll ? onPage : picked);
    if (on) next.add(code);
    else next.delete(code);
    setPickedAll(false);
    setPicked(next);
  }

  function tickPage(on: boolean) {
    if (!on) return clearPicked();
    setPicked(new Set([...picked, ...onPage]));
  }

  async function exportLeads() {
    setExporting(true);
    try {
      const file = await (picked.size && !pickedAll
        ? apiBlob("/v1/crm/leads/export", {
            method: "POST",
            body: JSON.stringify({ clinic: clinicId, codes: [...picked] }),
          })
        : apiBlob(`/v1/crm/leads/export?clinic=${clinicId}&${filterQuery}`));
      saveFile(file, `leads-${clinicId}-${ymd(new Date())}.csv`);
      toast("Leads exported");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not export the leads.");
    } finally {
      setExporting(false);
    }
  }

  // After an import: every filter off, so the new leads are right there on the first page.
  function imported() {
    clearPicked();
    setSearch("");
    setTreatment("");
    setSource("");
    setFrom("");
    setTo("");
    setPage(1);
    setVersion((v) => v + 1);
    go("", null);
  }

  return (
    <>
      <div className="ph">
        <div>
          <h1>Leads</h1>
          <p>Every lead from chatbot, ads, calls and walk-ins.</p>
        </div>
        {canBulk && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn g" disabled={exporting} onClick={exportLeads}>
              <Icon name="download" />
              {exporting ? "Exporting…" : pickedCount ? `Export (${pickedCount})` : "Export all"}
            </button>
            <button
              className="btn g"
              onClick={() =>
                openModal({
                  title: "Import leads",
                  body: <ImportLeadsForm clinicId={clinicId!} onDone={imported} />,
                })
              }
            >
              <Icon name="upload" />
              Import
            </button>
          </div>
        )}
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
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name, phone, treatment, email or code" />
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
        <select className="sel" value={treatment} onChange={(e) => setTreatment(e.target.value)} aria-label="Treatment">
          <option value="">All treatments</option>
          {d?.treatments?.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
          {treatment && d && !d.treatments?.includes(treatment) && <option value={treatment}>{treatment}</option>}
        </select>
      </div>
      {error && <div className="warnbox">{error}</div>}
      {canBulk && pickedCount > 0 && d && (
        <p className="sub2" style={{ margin: "0 0 8px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <span>
            {pickedAll ? `All ${d.total} leads selected.` : `${picked.size} lead${picked.size === 1 ? "" : "s"} selected.`}
          </span>
          {!pickedAll && pageTicked && d.total > picked.size && (
            <button type="button" className="btn g sm" onClick={() => setPickedAll(true)}>
              Select all {d.total}
            </button>
          )}
          <button type="button" className="btn g sm" onClick={clearPicked}>
            Clear
          </button>
        </p>
      )}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              {canBulk && (
                <th style={{ width: 36 }}>
                  <input
                    type="checkbox"
                    aria-label="Select all leads on this page"
                    checked={pickedAll || pageTicked}
                    onChange={(e) => tickPage(e.target.checked)}
                  />
                </th>
              )}
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
                <td colSpan={8}>Loading…</td>
              </tr>
            )}
            {d && !d.items.length && (
              <tr>
                <td colSpan={8}>No leads match.</td>
              </tr>
            )}
            {d?.items.map((l) => (
              <tr key={l.code} onClick={() => show(l.code)} style={{ cursor: "pointer" }}>
                {canBulk && (
                  <td style={{ cursor: "default" }} onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label={`Select ${l.name}`}
                      checked={pickedAll || picked.has(l.code)}
                      onChange={(e) => tick(l.code, e.target.checked)}
                    />
                  </td>
                )}
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
      {d && d.total > 0 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
          <span className="sub2">
            Showing {(page - 1) * PAGE_SIZE + 1}–{(page - 1) * PAGE_SIZE + d.items.length} of {d.total}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="sub2">
              Page {page} of {pages}
            </span>
            {(
              [
                ["Previous page", "‹", page - 1, page <= 1],
                ["Next page", "›", page + 1, page >= pages],
              ] as [string, string, number, boolean][]
            ).map(([label, mark, to, off]) => (
              <button
                key={label}
                type="button"
                className="btn g sm"
                aria-label={label}
                title={label}
                disabled={off}
                style={{ width: 34, height: 34, padding: 0, justifyContent: "center", fontSize: 20, lineHeight: 1, opacity: off ? 0.45 : 1, cursor: off ? "not-allowed" : "pointer" }}
                onClick={() => goPage(to)}
              >
                {mark}
              </button>
            ))}
          </div>
        </div>
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
