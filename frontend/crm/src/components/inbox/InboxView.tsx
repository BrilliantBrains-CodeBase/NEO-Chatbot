"use client";

import Loading from "@/components/crm/Loading";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import Pager from "@/components/crm/Pager";
import LeadDrawer from "@/components/leads/LeadDrawer";
import { SOURCE, useDebounced, when } from "@/components/leads/labels";
import {
  api,
  ApiError,
  INBOX_TABS,
  REFRESH_MS,
  type Assigned,
  type Inbox,
  type InboxRequest,
} from "@/lib/api";
import AssignControls, { useAssignRights } from "./AssignControls";
import { asked, day, requestLabel } from "./RequestCard";

const PAGE_SIZE = 30;
const ymd = (d: Date) => d.toLocaleDateString("en-CA"); // YYYY-MM-DD, the browser's day
// The type chips: every request type, then leads that came without one (a website form, an import...).
const CHIPS: [string, string][] = [...INBOX_TABS, ["none", "No request"]];

function askedText(r: InboxRequest) {
  return (
    r.reason ??
    (asked(r) || (r.booked_date ? `Booked on ${day(r.booked_date)}` : ""))
  );
}

/** The Inbox: new leads from every source wait here without an owner. Front Desk takes them; an Admin
 * assigns them to anyone. Assigned leads move to Leads, where their owner handles the requests. */
export default function InboxView() {
  const { clinic, me, toast, refreshInbox } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const { canAssign, canTake } = useAssignRights(clinicId);
  const router = useRouter();
  const params = useSearchParams();
  const openCode = params.get("open");
  const askedType = params.get("type") ?? "";
  const [type, setType] = useState(
    CHIPS.some(([k]) => k === askedType) ? askedType : "",
  );
  const [version, setVersion] = useState(0);
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [treatment, setTreatment] = useState("");
  const [source, setSource] = useState("");
  const [page, setPage] = useState(1);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [taking, setTaking] = useState("");

  const filter = new URLSearchParams();
  if (type) filter.set("type", type);
  if (q) filter.set("q", q);
  if (from) filter.set("from", from);
  if (to) filter.set("to", to);
  if (treatment) filter.set("treatment", treatment);
  if (source) filter.set("source", source);
  const filterQuery = filter.toString();
  const filters = `${clinicId}|${filterQuery}`;
  const [seenFilters, setSeenFilters] = useState(filters);
  if (filters !== seenFilters) {
    setSeenFilters(filters);
    setPage(1);
    setPicked(new Set()); // what is ticked always belongs to the list on screen
  }
  const listUrl = `/v1/crm/inbox?clinic=${clinicId}&${filterQuery}&limit=${PAGE_SIZE}&offset=${(page - 1) * PAGE_SIZE}`;
  const key = `${filters}|${page}|${version}`;
  const [list, setList] = useState<{ key: string; d?: Inbox; error?: string }>({
    key: "",
  });

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Inbox>(listUrl).then(
      (d) => live && setList({ key, d }),
      (e) =>
        live &&
        setList({
          key,
          error:
            e instanceof ApiError ? e.message : "Could not load the Inbox.",
        }),
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
      api<Inbox>(listUrl).then(
        (d) => setList((now) => (now.key === key ? { key, d } : now)),
        () => {},
      );
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [clinicId, listUrl, key]);

  const d = list.key === key ? list.d : undefined;
  const error = list.key === key ? list.error : undefined;
  const total = d?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (d && page > pages) setPage(pages); // the last page emptied (its leads were assigned)
  // Only new leads (no owner yet) are ticked to assign; a patient who has an owner is here for a request.
  const rows = d?.items.filter((l) => !l.assigned).map((l) => l.code) ?? [];
  const pageTicked = rows.length > 0 && rows.every((c) => picked.has(c));

  function tick(code: string, on: boolean) {
    const next = new Set(picked);
    if (on) next.add(code);
    else next.delete(code);
    setPicked(next);
  }

  function open(code: string | null) {
    router.replace(
      code ? `/inbox?open=${encodeURIComponent(code)}` : "/inbox",
      { scroll: false },
    );
  }

  function goPage(n: number) {
    setPage(n);
    document.querySelector(".crm .page")?.scrollTo(0, 0);
  }

  function range(today: boolean) {
    const t = today ? ymd(new Date()) : "";
    setFrom(t);
    setTo(t);
  }
  const isToday = !!from && from === to && from === ymd(new Date());

  function assigned(r: Assigned) {
    setPicked(new Set([...picked].filter((c) => !r.assigned.includes(c))));
    setVersion((v) => v + 1);
  }

  // One lead, taken from its row.
  async function take(code: string) {
    setTaking(code);
    try {
      const r = await api<Assigned>("/v1/crm/inbox/assign", {
        method: "POST",
        body: JSON.stringify({ clinic: clinicId, codes: [code] }),
      });
      toast(
        r.assigned.length
          ? `${code} is yours: it is in Leads now`
          : "Already assigned by someone else",
      );
      refreshInbox();
      assigned(r);
    } catch (e) {
      toast(
        e instanceof ApiError
          ? e.message
          : "Could not assign. Please try again.",
      );
    } finally {
      setTaking("");
    }
  }

  const cols = 6 + (canAssign ? 1 : 0) + (canTake ? 1 : 0);
  return (
    <>
      <div className="ph">
        <div>
          <h1>Inbox</h1>
          <p>
            New leads from every source wait here, and every request still
            waiting from existing patients (a cancellation, a reschedule, a call
            back). Assign a new lead to move it to Leads.
          </p>
        </div>
      </div>
      <div className="tabs" aria-label="What the lead asked for">
        <button className={type ? "" : "on"} onClick={() => setType("")}>
          All<span className="c">{d?.all ?? "…"}</span>
        </button>
        {CHIPS.map(([k, label]) => (
          <button
            key={k}
            className={type === k ? "on" : ""}
            onClick={() => setType(k)}
          >
            {label}
            <span className="c">
              {d?.types.find((c) => c.key === k)?.count ?? "…"}
            </span>
          </button>
        ))}
      </div>
      <div className="tools">
        <label className="search">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, phone, treatment, email or code"
          />
        </label>
        <div className="pills" style={{ margin: 0 }} aria-label="Came in">
          <button
            type="button"
            className={`pill${isToday ? " on" : ""}`}
            onClick={() => range(true)}
          >
            Today
          </button>
          <button
            type="button"
            className={`pill${!from && !to ? " on" : ""}`}
            onClick={() => range(false)}
          >
            All time
          </button>
        </div>
        <input
          className="sel"
          type="date"
          aria-label="From"
          title="Came in from"
          value={from}
          max={to || undefined}
          onChange={(e) => setFrom(e.target.value)}
        />
        <span className="sub2">to</span>
        <input
          className="sel"
          type="date"
          aria-label="To"
          title="Came in to"
          value={to}
          min={from || undefined}
          onChange={(e) => setTo(e.target.value)}
        />
        <select
          className="sel"
          value={source}
          onChange={(e) => setSource(e.target.value)}
          aria-label="Source"
        >
          <option value="">All sources</option>
          {Object.entries(SOURCE).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select
          className="sel"
          value={treatment}
          onChange={(e) => setTreatment(e.target.value)}
          aria-label="Treatment"
        >
          <option value="">All treatments</option>
          {d?.treatments?.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
          {treatment && d && !d.treatments?.includes(treatment) && (
            <option value={treatment}>{treatment}</option>
          )}
        </select>
      </div>
      {canAssign && picked.size > 0 && (
        <div className="bulkbar">
          <span>
            {picked.size} lead{picked.size === 1 ? "" : "s"} selected
          </span>
          <AssignControls
            clinicId={clinicId}
            codes={[...picked]}
            onAssigned={assigned}
            compact
          />
          <button
            type="button"
            className="btn g sm"
            onClick={() => setPicked(new Set())}
          >
            Clear
          </button>
        </div>
      )}
      {error && <div className="warnbox">{error}</div>}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              {canAssign && (
                <th style={{ width: 36 }}>
                  <input
                    type="checkbox"
                    aria-label="Select all leads on this page"
                    checked={pageTicked}
                    onChange={(e) =>
                      setPicked(
                        e.target.checked
                          ? new Set([...picked, ...rows])
                          : new Set(),
                      )
                    }
                  />
                </th>
              )}
              <th>Lead</th>
              <th>Asked for</th>
              <th>Source</th>
              <th>Treatment</th>
              <th>Came in</th>
              <th>Last contact</th>
              {canTake && <th aria-label="Assign" />}
            </tr>
          </thead>
          <tbody>
            {!d && !error && (
              <tr>
                <td colSpan={cols}>
                  <Loading />
                </td>
              </tr>
            )}
            {d && !d.items.length && (
              <tr>
                <td colSpan={cols}>
                  {filterQuery
                    ? "No leads match."
                    : "Nothing waiting. Every lead has an owner."}
                </td>
              </tr>
            )}
            {d?.items.map((l) => {
              const first = l.requests[0];
              return (
                <tr
                  key={l.code}
                  onClick={() => open(l.code)}
                  style={{ cursor: "pointer" }}
                >
                  {canAssign && (
                    <td
                      style={{ cursor: "default" }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {!l.assigned && (
                        <input
                          type="checkbox"
                          aria-label={`Select ${l.name}`}
                          checked={picked.has(l.code)}
                          onChange={(e) => tick(l.code, e.target.checked)}
                        />
                      )}
                    </td>
                  )}
                  <td>
                    <div className="nm">
                      {l.requests.some((r) => r.urgent) && (
                        <span className="urgent-tag">Emergency</span>
                      )}
                      {l.name}
                    </div>
                    <div className="pn">
                      {l.code} · {l.phone ?? l.email}
                    </div>
                    {l.assigned && (
                      <div className="pn">Owner: {l.assigned}</div>
                    )}
                  </td>
                  <td>
                    {l.requests.length ? (
                      <>
                        <div className="rq-tags">
                          {[...new Set(l.requests.map((r) => r.type))].map(
                            (t) => (
                              <span key={t} className="badge b-new">
                                {requestLabel(t)}
                              </span>
                            ),
                          )}
                        </div>
                        {first && askedText(first) && (
                          <div className="pn">{askedText(first)}</div>
                        )}
                      </>
                    ) : (
                      <span className="sub2">No request</span>
                    )}
                  </td>
                  <td>
                    {SOURCE[l.source] ?? l.source}
                    {l.campaign && <div className="pn">{l.campaign}</div>}
                  </td>
                  <td>{l.treatment ?? first?.treatment ?? "—"}</td>
                  <td>{when(l.created_at)}</td>
                  <td>{when(l.last_contact_at)}</td>
                  {canTake && (
                    <td
                      style={{ cursor: "default" }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        className="btn sm"
                        disabled={!!taking}
                        onClick={() => take(l.code)}
                      >
                        {taking === l.code ? "Assigning…" : "Assign to me"}
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {d && total > 0 && (
        <Pager
          page={page}
          size={PAGE_SIZE}
          shown={d.items.length}
          total={total}
          onPage={goPage}
        />
      )}

      <div
        className={`ov${openCode ? " on" : ""}`}
        onClick={() => open(null)}
      />
      <aside className={`dr${openCode ? " on" : ""}`} aria-hidden={!openCode}>
        {openCode && (
          <LeadDrawer
            code={openCode}
            clinicId={clinicId}
            onClose={() => open(null)}
            onChanged={() => setVersion((v) => v + 1)}
          />
        )}
      </aside>
    </>
  );
}
