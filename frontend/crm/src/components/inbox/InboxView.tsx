"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError, INBOX_TABS, type Inbox, type InboxItem } from "@/lib/api";

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

const day = (iso: string | null) =>
  iso ? new Date(iso.length === 10 ? iso + "T00:00:00" : iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "";
const at = (iso: string) => new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
function asked(i: InboxItem) {
  if (!i.date) return "";
  if (!i.time || i.time === "any") return `${day(i.date)}, any time`;
  const [h, m] = i.time.split(":").map(Number);
  return `${day(i.date)} at ${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}
function apptText(i: InboxItem) {
  const a = i.appointment;
  if (!a) return i.type === "cancel" || i.type === "reschedule" ? "No matching appointment found" : "";
  const when = a.start ? at(a.start) : `${day(a.day)}, any time`;
  return [when, a.doctor, a.type === "online" ? "Online" : "In-clinic", a.status].filter(Boolean).join(" · ");
}

export default function InboxView() {
  const { clinic, me, refreshInbox, toast } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const role = me?.clinics.find((c) => c.id === clinicId)?.role;
  const router = useRouter();
  const asked_tab = useSearchParams().get("tab") ?? "book";
  const tab = INBOX_TABS.some(([k]) => k === asked_tab) ? asked_tab : "book";
  const [handled, setHandled] = useState(false);
  const [version, setVersion] = useState(0);
  const key = `${clinicId}|${tab}|${handled}|${version}`;
  const [list, setList] = useState<{ key: string; d?: Inbox; error?: string }>({ key: "" });
  const [openId, setOpenId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Inbox>(`/v1/crm/inbox?clinic=${clinicId}&type=${tab}${handled ? "&done=true" : ""}`).then(
      (d) => live && setList({ key, d }),
      (e) => live && setList({ key, error: e instanceof ApiError ? e.message : "Could not load the Inbox." }),
    );
    return () => {
      live = false;
    };
  }, [clinicId, tab, handled, key]);

  const d = list.key === key ? list.d : undefined;
  const item = d?.items.find((i) => i.id === openId);
  const canAct = !!role && role !== "doctor" && item?.status === "pending";

  function open(id: string | null) {
    setOpenId(id);
    setReason("");
    setNote("");
    setError("");
  }

  async function act(path: string, body: object | undefined, done: string) {
    if (!item) return;
    setBusy(true);
    setError("");
    try {
      await api<InboxItem>(`/v1/crm/requests/${item.id}/${path}`, { method: "POST", body: body ? JSON.stringify(body) : undefined });
      open(null);
      setVersion((v) => v + 1);
      refreshInbox();
      toast(done);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="ph">
        <div>
          <h1>Inbox</h1>
          <p>Approve bookings, handle cancellations and reschedules, and call back patients.</p>
        </div>
        <div className="seg">
          <button className={handled ? "" : "on"} onClick={() => setHandled(false)}>
            Pending
          </button>
          <button className={handled ? "on" : ""} onClick={() => setHandled(true)}>
            Handled
          </button>
        </div>
      </div>
      <div className="tabs">
        {INBOX_TABS.map(([k, label]) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => router.replace(`/inbox?tab=${k}`, { scroll: false })}>
            {label}
            <span className="c">{d?.pending.find((c) => c.key === k)?.count ?? "…"}</span>
          </button>
        ))}
      </div>
      {list.key === key && list.error && <div className="warnbox">{list.error}</div>}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>Patient</th>
              <th>Treatment</th>
              <th>{tab === "callback" || tab === "question" ? "Reason" : "Asked for"}</th>
              <th>Appointment</th>
              <th>Received</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {!d && !(list.key === key && list.error) && (
              <tr>
                <td colSpan={6}>Loading…</td>
              </tr>
            )}
            {d && !d.items.length && (
              <tr>
                <td colSpan={6}>{handled ? "Nothing handled yet." : "Nothing waiting. All done."}</td>
              </tr>
            )}
            {d?.items.map((i) => (
              <tr key={i.id} onClick={() => open(i.id)} style={{ cursor: "pointer" }}>
                <td>
                  <div className="nm">{i.name}</div>
                  <div className="pn">
                    {i.lead_code} · {i.phone ?? i.email}
                  </div>
                </td>
                <td>{i.treatment ?? "—"}</td>
                <td>{i.reason ?? (asked(i) || (i.booked_date ? `Booked on ${day(i.booked_date)}` : "—"))}</td>
                <td>{apptText(i) || "—"}</td>
                <td>{at(i.created_at)}</td>
                <td>
                  <span className={`badge ${i.status === "pending" ? "b-fu" : i.status === "done" ? "b-vi" : "b-lo"}`}>
                    {i.status === "pending" ? "Pending" : i.status === "done" ? "Done" : "Rejected"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

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
              <button className="x" onClick={() => open(null)} aria-label="Close">
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
                    ["Appointment", apptText(item)],
                    ["Received", at(item.created_at)],
                  ] as [string, string | null][]
                )
                  .filter(([, v]) => v)
                  .map(([k, v]) => (
                    <div key={k}>
                      <span>{k}</span>
                      <b>{v}</b>
                    </div>
                  ))}
              </div>
              {canAct && (item.type === "callback" || item.type === "question") && (
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
                      <button key={k} className="pill" disabled={busy} onClick={() => act("done", { outcome: k, note }, "Callback done")}>
                        {v}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {canAct && APPROVE[item.type] && (
                <div className="sec">
                  <h4>DECISION</h4>
                  <div className="row" style={{ marginBottom: 8 }}>
                    <button className="btn" disabled={busy} onClick={() => act("approve", undefined, "Approved")}>
                      {APPROVE[item.type]}
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
                    <button className="pill" disabled={busy || reason.trim().length < 3} onClick={() => act("reject", { reason }, "Rejected")}>
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
