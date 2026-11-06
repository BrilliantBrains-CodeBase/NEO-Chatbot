"use client";

import { level } from "@/lib/access";
import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError, type LeadDetail, type StaffOption } from "@/lib/api";

const STAGES: [string, string][] = [
  ["new", "New"],
  ["follow_up", "Follow Up"],
  ["booked", "Booked"],
  ["visited", "Visited"],
  ["lost", "Lost"],
  ["invalid", "Invalid"],
];
// The reasons the database accepts for Lost and Invalid.
const REASONS: Record<string, [string, string][]> = {
  lost: [
    ["not_reachable", "Not reachable"],
    ["not_interested", "Not interested"],
    ["price", "Price"],
    ["chose_another_clinic", "Chose another clinic"],
    ["other", "Other"],
  ],
  invalid: [
    ["wrong_number", "Wrong number"],
    ["spam", "Spam"],
    ["duplicate", "Duplicate"],
    ["test", "Test"],
    ["booking_rejected", "Booking rejected"],
  ],
};
const CALLS: [string, string][] = [
  ["answered", "Answered"],
  ["no_answer", "No answer"],
  ["busy", "Busy"],
  ["wrong_number", "Wrong number"],
];

/** Stage, owner, note and call log for one lead. Doctors see the lead but not these controls. */
export default function LeadActions({
  lead,
  clinicId,
  onChange,
}: {
  lead: LeadDetail;
  clinicId: string | undefined;
  onChange: (d: LeadDetail) => void;
}) {
  const { me } = useCrm();
  const role = me?.clinics.find((c) => c.id === clinicId)?.role;
  const [staff, setStaff] = useState<StaffOption[]>([]);
  const [stage, setStage] = useState(lead.stage);
  const [reason, setReason] = useState(lead.stage_reason ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!clinicId) return;
    api<StaffOption[]>(`/v1/crm/staff?clinic=${clinicId}`).then(setStaff, () => setStaff([]));
  }, [clinicId]);

  if (!role || !clinicId || level(me, clinicId, "leads") !== "edit") return null; // Who sees what

  async function send(path: string, method: string, body: object) {
    setBusy(true);
    setError("");
    try {
      onChange(await api<LeadDetail>(`/v1/crm/leads/${encodeURIComponent(lead.code)}${path}`, { method, body: JSON.stringify(body) }));
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save. Please try again.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  const reasons = REASONS[stage];
  const stageChanged = stage !== lead.stage || (reasons && reason !== (lead.stage_reason ?? ""));

  return (
    <div className="sec">
      <h4>ACTIONS</h4>
      {error && <div className="warnbox">{error}</div>}
      <div className="row" style={{ marginBottom: 8 }}>
        <select
          className="sel"
          aria-label="Stage"
          value={stage}
          onChange={(e) => {
            setStage(e.target.value);
            setReason("");
          }}
        >
          {STAGES.map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        {reasons && (
          <select className="sel" aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="">Choose a reason</option>
            {reasons.map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        )}
        <button
          className="btn"
          disabled={busy || !stageChanged || (!!reasons && !reason)}
          onClick={() => send("", "PATCH", { stage, stage_reason: reasons ? reason : null })}
        >
          Save stage
        </button>
      </div>
      <div className="row" style={{ marginBottom: 8 }}>
        <select
          className="sel"
          aria-label="Assigned to"
          value={lead.assigned_id ?? ""}
          disabled={busy}
          onChange={(e) => send("", "PATCH", { assigned_to: e.target.value })}
        >
          <option value="">Unassigned</option>
          {staff.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} ({s.role_label})
            </option>
          ))}
        </select>
      </div>
      <div className="row" style={{ marginBottom: 8 }}>
        <span className="sub2">Log a call:</span>
        {CALLS.map(([k, v]) => (
          <button key={k} className="pill" disabled={busy} onClick={() => send("/calls", "POST", { outcome: k })}>
            {v}
          </button>
        ))}
      </div>
      <div className="row">
        <textarea
          aria-label="Note"
          rows={2}
          maxLength={2000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Add a note"
          style={{ flex: 1, font: "inherit", border: "1px solid var(--line)", borderRadius: 9, padding: 8 }}
        />
        <button
          className="btn"
          disabled={busy || !note.trim()}
          onClick={async () => {
            if (await send("/notes", "POST", { text: note })) setNote("");
          }}
        >
          Add note
        </button>
      </div>
    </div>
  );
}
