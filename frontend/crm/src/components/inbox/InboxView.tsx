"use client";

import Loading from "@/components/crm/Loading";
import { level } from "@/lib/access";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import Icon from "@/components/crm/Icon";
import Pager from "@/components/crm/Pager";
import { SOURCE, useDebounced } from "@/components/leads/LeadsView";
import {
  api,
  apiBlob,
  ApiError,
  INBOX_TABS,
  REFRESH_MS,
  saveFile,
  type Inbox,
  type InboxItem,
  type LeadOptions,
} from "@/lib/api";
import SlotPicker, { type Pick } from "./SlotPicker";

// The box under the treatment: for Other it is the treatment itself (required); for every other choice it
// is an optional note on the lead's timeline, so the next person who calls knows what the patient said.
const placeholder = (choice: string) =>
  choice === "Other"
    ? "Write the treatment"
    : "Note for the team: what the patient said (optional)";

const PAGE_SIZE = 30;
const ymd = (d: Date) => d.toLocaleDateString("en-CA"); // YYYY-MM-DD, the browser's day
const OUTCOMES: [string, string][] = [
  ["answered", "Answered"],
  ["no_answer", "No answer"],
  ["busy", "Busy"],
  ["wrong_number", "Wrong number"],
];
const APPROVE: Record<string, string> = {
  book: "Approve booking",
  online: "Approve consult",
  cancel: "Confirm cancellation",
  reschedule: "Confirm new time",
};

const clockOf = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-IN", {
    hour: "numeric",
    minute: "2-digit",
  });
const day = (iso: string | null) =>
  iso
    ? new Date(iso.length === 10 ? iso + "T00:00:00" : iso).toLocaleDateString(
        "en-IN",
        { day: "numeric", month: "short", year: "numeric" },
      )
    : "";
const at = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
function asked(i: InboxItem) {
  if (!i.date) return "";
  if (!i.time || i.time === "any") return `${day(i.date)}, any time`;
  const [h, m] = i.time.split(":").map(Number);
  return `${day(i.date)} at ${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}
function apptText(i: InboxItem) {
  const a = i.appointment;
  if (!a)
    return i.type === "cancel" || i.type === "reschedule"
      ? "No matching appointment found"
      : "";
  const when = a.start ? at(a.start) : `${day(a.day)}, any time`;
  return [
    when,
    a.doctor,
    a.type === "online" ? "Online" : "In-clinic",
    a.status,
  ]
    .filter(Boolean)
    .join(" · ");
}

export default function InboxView() {
  const { clinic, me, refreshInbox, toast } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const role = me?.clinics.find((c) => c.id === clinicId)?.role;
  const router = useRouter();
  const params = useSearchParams();
  const asked_tab = params.get("tab") ?? "book";
  const tab = INBOX_TABS.some(([k]) => k === asked_tab) ? asked_tab : "book";
  const [handled, setHandled] = useState(false);
  const [version, setVersion] = useState(0);
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [treatment, setTreatment] = useState("");
  const [source, setSource] = useState("");
  const [page, setPage] = useState(1);
  const filter = new URLSearchParams();
  if (q) filter.set("q", q);
  if (from) filter.set("from", from);
  if (to) filter.set("to", to);
  if (treatment) filter.set("treatment", treatment);
  if (source) filter.set("source", source);
  const filterQuery = filter.toString();
  // The requests ticked for Export (across pages), or every request matching the filters.
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [pickedAll, setPickedAll] = useState(false);
  const clearPicked = () => {
    setPicked(new Set());
    setPickedAll(false);
  };
  const filters = `${clinicId}|${tab}|${handled}|${filterQuery}`;
  const [seenFilters, setSeenFilters] = useState(filters);
  if (filters !== seenFilters) {
    setSeenFilters(filters);
    setPage(1);
    clearPicked(); // what is ticked always belongs to the list on screen
  }
  const shownQuery = `clinic=${clinicId}&type=${tab}${handled ? "&done=true" : ""}&${filterQuery}`;
  const listUrl = `/v1/crm/inbox?${shownQuery}&limit=${PAGE_SIZE}&offset=${(page - 1) * PAGE_SIZE}`;
  const [exporting, setExporting] = useState(false);
  const canExport = !!clinicId && (me?.bb_admin || role === "clinic_manager");
  const key = `${filters}|${page}|${version}`;
  const [list, setList] = useState<{ key: string; d?: Inbox; error?: string }>({
    key: "",
  });
  // The open request is in the address (?open=id), so a notification opens it.
  const openId = params.get("open");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  // Changes agreed with the patient on the phone, applied when approving.
  const [changing, setChanging] = useState(false);
  const [pick, setPick] = useState<Pick | null>(null); // doctor, day and free time chosen
  const [otherTreatment, setOtherTreatment] = useState("");
  const [newTreatment, setNewTreatment] = useState("");
  const [treatments, setTreatments] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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

  // Quietly, without "Loading…": the same list again while the tab is in view (CrmProvider keeps the counts fresh).
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

  useEffect(() => {
    if (!clinicId) return;
    api<LeadOptions>(`/v1/crm/lead-options?clinic=${clinicId}`).then(
      (o) => setTreatments(o.treatments),
      () => {},
    );
  }, [clinicId]);

  const d = list.key === key ? list.d : undefined;
  const onPage = d?.items.find((i) => i.id === openId);
  // Opened from a notification or the calendar, it may be on another page or hidden by a search: read by itself.
  const [fetched, setFetched] = useState<InboxItem | null>(null);
  useEffect(() => {
    if (!openId || !d || onPage) return;
    let live = true;
    api<InboxItem>(`/v1/crm/requests/${encodeURIComponent(openId)}`).then(
      (i) => live && setFetched(i),
      () => {},
    );
    return () => {
      live = false;
    };
  }, [openId, d, onPage]);
  const item = onPage ?? (fetched?.id === openId ? fetched : undefined);

  const total = d?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (d && page > pages) setPage(pages); // the last page emptied (e.g. its requests were handled)
  const rowIds = d?.items.map((i) => i.id) ?? [];
  const pageTicked = rowIds.length > 0 && rowIds.every((c) => picked.has(c));
  const pickedCount = pickedAll ? total : picked.size;

  function tick(id: string, on: boolean) {
    // Unticking one out of "all": everything else on this screen stays ticked.
    const next = new Set(pickedAll ? rowIds : picked);
    if (on) next.add(id);
    else next.delete(id);
    setPickedAll(false);
    setPicked(next);
  }

  function tickPage(on: boolean) {
    if (!on) return clearPicked();
    setPicked(new Set([...picked, ...rowIds]));
  }

  function goPage(n: number) {
    setPage(n);
    document.querySelector(".crm .page")?.scrollTo(0, 0);
  }

  function range(days: number | null) {
    const today = ymd(new Date());
    setFrom(days === null ? "" : today);
    setTo(days === null ? "" : today);
  }
  const isToday = !!from && from === to && from === ymd(new Date());

  async function exportInbox() {
    setExporting(true);
    try {
      const file = await (picked.size && !pickedAll
        ? apiBlob("/v1/crm/inbox/export", {
            method: "POST",
            body: JSON.stringify({ clinic: clinicId, ids: [...picked] }),
          })
        : apiBlob(`/v1/crm/inbox/export?${shownQuery}`));
      saveFile(
        file,
        `inbox-${clinicId}-${tab}-${new Date().toLocaleDateString("en-CA")}.csv`,
      );
      toast("Inbox exported");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not export the Inbox.");
    } finally {
      setExporting(false);
    }
  }
  const canAct =
    !!role &&
    level(me, clinic, "inbox") === "edit" &&
    item?.status === "pending";
  // An online consult for "Any time" needs the time agreed with the patient before Cal.com can book it.
  // An online consult needs an exact time for Cal.com: a request for "Any time" (new booking or reschedule)
  // opens the time picker.
  const needsTime =
    (item?.type === "online" &&
      !!item.appointment &&
      !item.appointment.start) ||
    (item?.type === "reschedule" &&
      item.appointment?.type === "online" &&
      (!item.time || item.time === "any"));

  function open(id: string | null) {
    router.replace(`/inbox?tab=${tab}${id ? `&open=${id}` : ""}`, {
      scroll: false,
    });
    setReason("");
    setNote("");
    setPick(null);
    setOtherTreatment("");
    setChanging(false);
    setNewTreatment("");
    setError("");
  }

  async function act(path: string, body: object | undefined, done: string) {
    if (!item) return;
    setBusy(true);
    setError("");
    try {
      await api<InboxItem>(`/v1/crm/requests/${item.id}/${path}`, {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      });
      open(null);
      setVersion((v) => v + 1);
      refreshInbox();
      toast(done);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="ph">
        <div>
          <h1>Inbox</h1>
          <p>
            Approve bookings, handle cancellations and reschedules, and call
            back patients.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {canExport && (
            <button
              className="btn g"
              disabled={exporting}
              onClick={exportInbox}
            >
              <Icon name="download" />
              {exporting
                ? "Exporting…"
                : pickedCount
                  ? `Export (${pickedCount})`
                  : "Export all"}
            </button>
          )}
          <div className="seg">
            <button
              className={handled ? "" : "on"}
              onClick={() => setHandled(false)}
            >
              Pending
            </button>
            <button
              className={handled ? "on" : ""}
              onClick={() => setHandled(true)}
            >
              Handled
            </button>
          </div>
        </div>
      </div>
      <div className="tabs">
        {INBOX_TABS.map(([k, label]) => (
          <button
            key={k}
            className={tab === k ? "on" : ""}
            onClick={() => router.replace(`/inbox?tab=${k}`, { scroll: false })}
          >
            {label}
            <span className="c">
              {d?.pending.find((c) => c.key === k)?.count ?? "…"}
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
        <div
          className="pills"
          style={{ margin: 0 }}
          aria-label="Date asked for"
        >
          <button
            type="button"
            className={`pill${isToday ? " on" : ""}`}
            onClick={() => range(1)}
          >
            Today
          </button>
          <button
            type="button"
            className={`pill${!from && !to ? " on" : ""}`}
            onClick={() => range(null)}
          >
            All time
          </button>
        </div>
        <input
          className="sel"
          type="date"
          aria-label="From"
          title="Date asked for"
          value={from}
          max={to || undefined}
          onChange={(e) => setFrom(e.target.value)}
        />
        <span className="sub2">to</span>
        <input
          className="sel"
          type="date"
          aria-label="To"
          title="Date asked for"
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
      {canExport && pickedCount > 0 && d && (
        <p
          className="sub2"
          style={{
            margin: "0 0 8px",
            display: "flex",
            gap: 10,
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <span>
            {pickedAll
              ? `All ${total} requests selected.`
              : `${picked.size} request${picked.size === 1 ? "" : "s"} selected.`}
          </span>
          {!pickedAll && pageTicked && total > picked.size && (
            <button
              type="button"
              className="btn g sm"
              onClick={() => setPickedAll(true)}
            >
              Select all {total}
            </button>
          )}
          <button type="button" className="btn g sm" onClick={clearPicked}>
            Clear
          </button>
        </p>
      )}
      {list.key === key && list.error && (
        <div className="warnbox">{list.error}</div>
      )}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              {canExport && (
                <th style={{ width: 36 }}>
                  <input
                    type="checkbox"
                    aria-label="Select all requests on this page"
                    checked={pickedAll || pageTicked}
                    onChange={(e) => tickPage(e.target.checked)}
                  />
                </th>
              )}
              <th>Patient</th>
              <th>Treatment</th>
              <th>
                {tab === "callback" || tab === "question"
                  ? "Reason"
                  : "Asked for"}
              </th>
              <th>Appointment</th>
              <th>Received</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {!d && !(list.key === key && list.error) && (
              <tr>
                <td colSpan={7}>
                  <Loading />
                </td>
              </tr>
            )}
            {d && !d.items.length && (
              <tr>
                <td colSpan={7}>
                  {filterQuery
                    ? "No requests match."
                    : handled
                      ? "Nothing handled yet."
                      : "Nothing waiting. All done."}
                </td>
              </tr>
            )}
            {d?.items.map((i) => (
              <tr
                key={i.id}
                onClick={() => open(i.id)}
                style={{ cursor: "pointer" }}
              >
                {canExport && (
                  <td
                    style={{ cursor: "default" }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      aria-label={`Select ${i.name}`}
                      checked={pickedAll || picked.has(i.id)}
                      onChange={(e) => tick(i.id, e.target.checked)}
                    />
                  </td>
                )}
                <td>
                  <div className="nm">
                    {i.urgent && <span className="urgent-tag">Emergency</span>}
                    {i.appointment?.status === "missed" && !handled && (
                      <span className="passed-tag">Time passed</span>
                    )}
                    {i.name}
                  </div>
                  <div className="pn">
                    {i.lead_code} · {i.phone ?? i.email}
                  </div>
                </td>
                <td>{i.treatment ?? "—"}</td>
                <td>
                  {i.reason ??
                    (asked(i) ||
                      (i.booked_date
                        ? `Booked on ${day(i.booked_date)}`
                        : "—"))}
                </td>
                <td>{apptText(i) || "—"}</td>
                <td>{at(i.created_at)}</td>
                <td>
                  <span
                    className={`badge ${i.status === "pending" ? "b-fu" : i.status === "done" ? "b-vi" : "b-lo"}`}
                  >
                    {i.status === "pending"
                      ? "Pending"
                      : i.status === "done"
                        ? "Done"
                        : "Rejected"}
                  </span>
                </td>
              </tr>
            ))}
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

      <div className={`ov${item ? " on" : ""}`} onClick={() => open(null)} />
      <aside className={`dr${item ? " on" : ""}`} aria-hidden={!item}>
        {item && (
          <>
            <div className="dh">
              <div>
                <h2>{item.name}</h2>
                <p>
                  <Link className="lnk" href={`/leads?open=${item.lead_code}`}>
                    {item.lead_code}
                  </Link>
                  {INBOX_TABS.find(([k]) => k === item.type)?.[1]}
                </p>
              </div>
              <button
                className="x"
                onClick={() => open(null)}
                aria-label="Close"
              >
                ✕
              </button>
            </div>
            <div className="db">
              {error && <div className="warnbox">{error}</div>}
              <div className="kv">
                {(
                  [
                    ["Phone", item.phone],
                    ["Email", item.email],
                    ["Treatment", item.treatment],
                    ["Asked for", asked(item)],
                    ["Booked on", day(item.booked_date)],
                    ["Reason", item.reason],
                    ["Doctor", item.appointment?.doctor ?? null],
                    [
                      "Date",
                      item.appointment
                        ? day(item.appointment.start ?? item.appointment.day)
                        : null,
                    ],
                    [
                      "Time",
                      item.appointment
                        ? item.appointment.start
                          ? clockOf(item.appointment.start)
                          : "Any time"
                        : null,
                    ],
                    [
                      "Type",
                      item.appointment
                        ? item.appointment.type === "online"
                          ? "Online"
                          : "In-clinic"
                        : null,
                    ],
                    ["Status", item.appointment?.status ?? null],
                    [
                      "Appointment",
                      item.appointment ? null : apptText(item) || null,
                    ],
                    ["Meet link", item.appointment?.meet_link ?? null],
                    ["Received", at(item.created_at)],
                  ] as [string, string | null][]
                )
                  .filter(([, v]) => v)
                  .map(([k, v]) => (
                    <div key={k}>
                      <span>{k}</span>
                      <b>
                        {k === "Meet link" && v ? (
                          <a
                            className="lnk"
                            href={v}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {v}
                          </a>
                        ) : (
                          v
                        )}
                      </b>
                    </div>
                  ))}
              </div>
              {canAct &&
                (item.type === "callback" || item.type === "question") && (
                  <div className="sec">
                    <h4>CALL OUTCOME</h4>
                    <textarea
                      className="f"
                      rows={2}
                      maxLength={2000}
                      placeholder="Note (optional)"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      style={{ width: "100%", marginBottom: 8 }}
                    />
                    <div className="row">
                      {OUTCOMES.map(([k, v]) => (
                        <button
                          key={k}
                          className="pill"
                          disabled={busy}
                          onClick={() =>
                            act("done", { outcome: k, note }, "Callback done")
                          }
                        >
                          {v}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              {canAct && APPROVE[item.type] && (
                <div className="sec">
                  <h4>DECISION</h4>
                  {item.type === "online" && (
                    <p className="sub2" style={{ marginTop: 0 }}>
                      Approving books the consult in Cal.com: the patient gets
                      the Google Meet link by email.
                    </p>
                  )}
                  {item.type !== "cancel" && (
                    <button
                      className="lnk"
                      style={{
                        border: 0,
                        background: "none",
                        padding: 0,
                        marginBottom: 8,
                        cursor: "pointer",
                      }}
                      onClick={() => setChanging(!changing)}
                    >
                      {changing
                        ? "Keep as asked"
                        : "Change date, time or treatment"}
                    </button>
                  )}
                  {(changing || needsTime) && clinicId && item.appointment && (
                    <SlotPicker
                      key={item.id}
                      clinicId={clinicId}
                      mode={item.appointment.type}
                      doctorId={item.appointment.doctor_id}
                      value={pick}
                      onChange={setPick}
                    />
                  )}
                  {changing && (
                    <div className="row" style={{ marginBottom: 8 }}>
                      <select
                        className="f"
                        aria-label="Treatment"
                        value={newTreatment}
                        onChange={(e) => setNewTreatment(e.target.value)}
                      >
                        <option value="">Same treatment</option>
                        {treatments.map((t) => (
                          <option key={t}>{t}</option>
                        ))}
                        {!treatments.includes("Other") && (
                          <option>Other</option>
                        )}
                      </select>
                      {
                        <input
                          className="f"
                          style={{ flex: 1 }}
                          aria-label={
                            newTreatment === "Other"
                              ? "Other treatment"
                              : "Note for the team"
                          }
                          placeholder={placeholder(newTreatment)}
                          maxLength={newTreatment === "Other" ? 100 : 500}
                          value={otherTreatment}
                          onChange={(e) => setOtherTreatment(e.target.value)}
                        />
                      }
                    </div>
                  )}
                  <div className="row" style={{ marginBottom: 8 }}>
                    <button
                      className="btn"
                      disabled={
                        busy ||
                        (needsTime && !pick) ||
                        (changing &&
                          newTreatment === "Other" &&
                          otherTreatment.trim().length < 2)
                      }
                      onClick={() =>
                        act(
                          "approve",
                          {
                            date: pick?.date ?? null,
                            time: pick?.time ?? null,
                            doctor_id: pick?.doctorId || null,
                            treatment: changing
                              ? (newTreatment === "Other"
                                  ? otherTreatment.trim()
                                  : newTreatment) || null
                              : null,
                            note:
                              changing && newTreatment !== "Other"
                                ? otherTreatment.trim()
                                : "",
                          },
                          item.type === "online"
                            ? "Approved, Meet link sent"
                            : "Approved",
                        )
                      }
                    >
                      {busy && item.type === "online"
                        ? "Booking in Cal.com…"
                        : APPROVE[item.type]}
                    </button>
                  </div>
                  <div className="row">
                    <input
                      className="f"
                      style={{ flex: 1 }}
                      placeholder="Reason to reject (the patient is told by phone)"
                      maxLength={500}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                    <button
                      className="pill"
                      disabled={busy || reason.trim().length < 3}
                      onClick={() => act("reject", { reason }, "Rejected")}
                    >
                      Reject
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </aside>
    </>
  );
}
