"use client";

import Loading from "@/components/crm/Loading";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import Icon from "@/components/crm/Icon";
import Pager from "@/components/crm/Pager";
import { api, apiBlob, ApiError, INBOX_TABS, REFRESH_MS, saveFile, type LeadList } from "@/lib/api";
import ImportLeadsForm from "./ImportLeadsForm";
import LeadDrawer from "./LeadDrawer";
import { SOURCE, STAGE_LABEL, useDebounced, when } from "./labels";

export { SOURCE, STAGE_LABEL, useDebounced };

const PAGE_SIZE = 30;
const REQUESTS = ["any", ...INBOX_TABS.map(([k]) => k)];

const ymd = (d: Date) => d.toLocaleDateString("en-CA"); // YYYY-MM-DD, the browser's day
const errorText = (e: unknown) => (e instanceof ApiError ? e.message : "Could not load leads.");

export default function LeadsView() {
  const { clinic, me, toast, openModal } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  // The stage tab and the open lead live in the address (?stage=booked&open=NFHT-00003), so the menu
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
  // "Needs action": leads with a request waiting for their owner (any, or one type). In the address, so the
  // Dashboard's "Callbacks waiting" opens it.
  const askedRequest = params.get("request");
  const [request, setRequest] = useState(askedRequest && REQUESTS.includes(askedRequest) ? askedRequest : "");
  const [seenRequest, setSeenRequest] = useState(askedRequest);
  if (askedRequest !== seenRequest) {
    setSeenRequest(askedRequest);
    if (askedRequest && REQUESTS.includes(askedRequest)) setRequest(askedRequest);
  }
  // Leads shows assigned leads; an Admin can also look at those still waiting in the Inbox.
  const [unassigned, setUnassigned] = useState(false);
  const [page, setPage] = useState(1);
  // The leads ticked for Export (across pages), or every lead matching the filters.
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [pickedAll, setPickedAll] = useState(false);
  const clearPicked = () => {
    setPicked(new Set());
    setPickedAll(false);
  };
  const filters = `${clinicId}|${stage}|${source}|${treatment}|${q}|${from}|${to}|${request}|${unassigned}`;
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
  if (request) shown.set("request", request);
  if (unassigned) shown.set("owner", "unassigned");
  const filterQuery = shown.toString();
  const listUrl = `/v1/crm/leads?clinic=${clinicId}&limit=${PAGE_SIZE}&offset=${(page - 1) * PAGE_SIZE}&${filterQuery}`;
  const [list, setList] = useState<{ key: string; d?: LeadList; error?: string }>({ key: "" });

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

  const show = (code: string) => go(stage, code);
  const close = () => go(stage, null);

  const d = list.key === key ? list.d : undefined;
  const error = list.key === key ? list.error : undefined;
  const all = d?.stages.reduce((n, s) => n + s.count, 0);
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
    setRequest("");
    setPage(1);
    setVersion((v) => v + 1);
    // Imported leads have no owner yet: they wait in the Inbox.
    setUnassigned(true);
    go("", null);
  }

  return (
    <>
      <div className="ph">
        <div>
          <h1>Leads</h1>
          <p>Assigned leads: confirm their bookings, call back and move them through the stages.</p>
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
        <select className="sel" value={request} onChange={(e) => setRequest(e.target.value)} aria-label="Needs action">
          <option value="">All leads</option>
          <option value="any">Needs action (any request)</option>
          {INBOX_TABS.map(([k, label]) => (
            <option key={k} value={k}>
              Needs action: {label}
            </option>
          ))}
        </select>
        {canBulk && (
          <label className="sub2" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
            <input type="checkbox" checked={unassigned} onChange={(e) => setUnassigned(e.target.checked)} />
            Waiting in Inbox (unassigned)
          </label>
        )}
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
                <td colSpan={8}>
                  <Loading />
                </td>
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
                  <div className="nm">
                    {l.name}
                    {l.pending > 0 && (
                      <span className="badge b-fu" style={{ marginLeft: 6 }} title="Requests waiting for the owner">
                        {l.pending} to handle
                      </span>
                    )}
                  </div>
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
      {d && d.total > 0 && <Pager page={page} size={PAGE_SIZE} shown={d.items.length} total={d.total} onPage={goPage} />}

      <div className={`ov${openCode ? " on" : ""}`} onClick={close} />
      <aside className={`dr${openCode ? " on" : ""}`} aria-hidden={!openCode}>
        {openCode && (
          <LeadDrawer code={openCode} clinicId={clinicId} onClose={close} onChanged={() => setVersion((v) => v + 1)} />
        )}
      </aside>
    </>
  );
}
