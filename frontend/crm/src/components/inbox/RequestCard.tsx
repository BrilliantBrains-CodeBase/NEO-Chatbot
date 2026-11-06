"use client";

import { useState } from "react";
import { api, ApiError, INBOX_TABS, type InboxItem } from "@/lib/api";
import SlotPicker, { type Pick } from "./SlotPicker";

// The box under the treatment: for Other it is the treatment itself (required); for every other choice it
// is an optional note on the lead's timeline, so the next person who calls knows what the patient said.
const placeholder = (choice: string) =>
  choice === "Other"
    ? "Write the treatment"
    : "Note for the team: what the patient said (optional)";

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

export const requestLabel = (type: string) =>
  INBOX_TABS.find(([k]) => k === type)?.[1].replace(/s$/, "") ?? type;

const clockOf = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
export const day = (iso: string | null) =>
  iso
    ? new Date(iso.length === 10 ? iso + "T00:00:00" : iso).toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "";
export const at = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
/** The day and time the patient asked for: "12 Nov 2026 at 10:30 AM" or "12 Nov 2026, any time". */
export function asked(i: { date: string | null; time: string | null }) {
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

/** One request waiting on a lead: what the patient asked, and (for the lead's owner) the decision on it. */
export default function RequestCard({
  item,
  clinicId,
  treatments,
  canAct,
  onDone,
}: {
  item: InboxItem;
  clinicId: string | undefined;
  treatments: string[];
  canAct: boolean;
  onDone: (message: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  // Changes agreed with the patient on the phone, applied when approving.
  const [changing, setChanging] = useState(false);
  const [pick, setPick] = useState<Pick | null>(null); // doctor, day and free time chosen
  const [otherTreatment, setOtherTreatment] = useState("");
  const [newTreatment, setNewTreatment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // An online consult needs an exact time for Cal.com: a request for "Any time" (new booking or reschedule)
  // opens the time picker.
  const needsTime =
    (item.type === "online" && !!item.appointment && !item.appointment.start) ||
    (item.type === "reschedule" &&
      item.appointment?.type === "online" &&
      (!item.time || item.time === "any"));

  async function act(path: string, body: object | undefined, done: string) {
    setBusy(true);
    setError("");
    try {
      await api<InboxItem>(`/v1/crm/requests/${item.id}/${path}`, {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      });
      onDone(done);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const facts = (
    [
      ["Treatment", item.treatment],
      ["Asked for", asked(item)],
      ["Booked on", day(item.booked_date)],
      ["Reason", item.reason],
      ["Doctor", item.appointment?.doctor ?? null],
      ["Date", item.appointment ? day(item.appointment.start ?? item.appointment.day) : null],
      [
        "Time",
        item.appointment ? (item.appointment.start ? clockOf(item.appointment.start) : "Any time") : null,
      ],
      ["Type", item.appointment ? (item.appointment.type === "online" ? "Online" : "In-clinic") : null],
      ["Status", item.appointment?.status ?? null],
      ["Appointment", item.appointment ? null : apptText(item) || null],
      ["Meet link", item.appointment?.meet_link ?? null],
      ["Received", at(item.created_at)],
    ] as [string, string | null][]
  ).filter(([, v]) => v);

  return (
    <div className="rq">
      <div className="rq-h">
        <b>{requestLabel(item.type)}</b>
        {item.urgent && <span className="urgent-tag">Emergency</span>}
        {item.appointment?.status === "missed" && <span className="passed-tag">Time passed</span>}
        {/* One lead per phone: someone else on the same phone (family) asked this one. */}
        {item.name.includes(" · existing lead ") && (
          <span className="sub2">Asked by {item.name.split(" · ")[0]}</span>
        )}
      </div>
      {error && <div className="warnbox">{error}</div>}
      <div className="kv">
        {facts.map(([k, v]) => (
          <div key={k}>
            <span>{k}</span>
            <b>
              {k === "Meet link" && v ? (
                <a className="lnk" href={v} target="_blank" rel="noreferrer">
                  {v}
                </a>
              ) : (
                v
              )}
            </b>
          </div>
        ))}
      </div>

      {canAct && (item.type === "callback" || item.type === "question") && (
        <div className="rq-act">
          <textarea
            className="f"
            rows={2}
            maxLength={2000}
            placeholder="Note (optional)"
            aria-label="Call note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="row">
            <span className="sub2">Call outcome:</span>
            {OUTCOMES.map(([k, v]) => (
              <button
                key={k}
                className="pill"
                disabled={busy}
                onClick={() => act("done", { outcome: k, note }, "Call back done")}
              >
                {v}
              </button>
            ))}
          </div>
        </div>
      )}

      {canAct && APPROVE[item.type] && (
        <div className="rq-act">
          {item.type === "online" && (
            <p className="sub2" style={{ margin: 0 }}>
              Approving books the consult in Cal.com: the patient gets the Google Meet link by email.
            </p>
          )}
          {item.type !== "cancel" && (
            <button className="lnk" style={{ alignSelf: "flex-start" }} onClick={() => setChanging(!changing)}>
              {changing ? "Keep as asked" : "Change date, time or treatment"}
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
            <div className="row">
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
                {!treatments.includes("Other") && <option>Other</option>}
              </select>
              <input
                className="f"
                style={{ flex: 1, minWidth: 0 }}
                aria-label={newTreatment === "Other" ? "Other treatment" : "Note for the team"}
                placeholder={placeholder(newTreatment)}
                maxLength={newTreatment === "Other" ? 100 : 500}
                value={otherTreatment}
                onChange={(e) => setOtherTreatment(e.target.value)}
              />
            </div>
          )}
          <div className="row">
            <button
              className="btn"
              disabled={
                busy ||
                (needsTime && !pick) ||
                (changing && newTreatment === "Other" && otherTreatment.trim().length < 2)
              }
              onClick={() =>
                act(
                  "approve",
                  {
                    date: pick?.date ?? null,
                    time: pick?.time ?? null,
                    doctor_id: pick?.doctorId || null,
                    treatment: changing
                      ? (newTreatment === "Other" ? otherTreatment.trim() : newTreatment) || null
                      : null,
                    note: changing && newTreatment !== "Other" ? otherTreatment.trim() : "",
                  },
                  item.type === "online" ? "Approved, Meet link sent" : "Approved",
                )
              }
            >
              {busy && item.type === "online" ? "Booking in Cal.com…" : APPROVE[item.type]}
            </button>
          </div>
          <div className="row">
            <input
              className="f"
              style={{ flex: 1, minWidth: 0 }}
              placeholder="Reason to reject (the patient is told by phone)"
              aria-label="Reason to reject"
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
  );
}
