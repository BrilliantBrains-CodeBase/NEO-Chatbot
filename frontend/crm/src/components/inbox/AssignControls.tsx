"use client";

import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { level } from "@/lib/access";
import { api, ApiError, type Assigned, type StaffOption } from "@/lib/api";

/** Who may assign Inbox leads: Front Desk takes them for themselves; an Admin assigns them to anyone. */
export function useAssignRights(clinicId: string | undefined) {
  const { me, clinic } = useCrm();
  const role = me?.clinics.find((c) => c.id === clinicId)?.role;
  const canAssign = !!role && role !== "doctor" && level(me, clinic, "inbox") === "edit";
  const anyone = canAssign && (me?.bb_admin || role === "clinic_manager");
  // A Super Admin is not on a clinic's team, so they assign to others rather than take leads.
  const canTake = canAssign && role !== "bb_admin";
  return { canAssign, anyone, canTake };
}

/** "Assign to me", and for an Admin a picker of everyone who can take leads. */
export default function AssignControls({
  clinicId,
  codes,
  onAssigned,
  compact = false,
}: {
  clinicId: string | undefined;
  codes: string[];
  onAssigned: (r: Assigned) => void;
  compact?: boolean;
}) {
  const { toast, refreshInbox } = useCrm();
  const { canAssign, anyone, canTake } = useAssignRights(clinicId);
  const [staff, setStaff] = useState<StaffOption[]>([]);
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!clinicId || !anyone) return;
    let live = true;
    api<StaffOption[]>(`/v1/crm/staff?clinic=${clinicId}`).then(
      (s) => live && setStaff(s),
      () => live && setStaff([]),
    );
    return () => {
      live = false;
    };
  }, [clinicId, anyone]);

  if (!canAssign) return null;

  async function assign(person: string | null) {
    setBusy(true);
    setError("");
    try {
      const r = await api<Assigned>("/v1/crm/inbox/assign", {
        method: "POST",
        body: JSON.stringify({ clinic: clinicId, codes, ...(person ? { to: person } : {}) }),
      });
      const n = r.assigned.length;
      toast(
        n === 0
          ? "Already assigned by someone else"
          : `${n === 1 ? "Lead" : `${n} leads`} assigned to ${r.to}${r.taken.length ? ` (${r.taken.length} already taken)` : ""}`,
      );
      setTo("");
      refreshInbox();
      onAssigned(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not assign. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const none = codes.length === 0;
  return (
    <div className={`assign${compact ? " compact" : ""}`}>
      {error && <div className="warnbox">{error}</div>}
      <div className="row">
        {canTake && (
          <button className="btn" disabled={busy || none} onClick={() => assign(null)}>
            Assign to me
          </button>
        )}
        {anyone && (
          <>
            <select
              className="sel"
              aria-label="Assign to"
              value={to}
              disabled={busy}
              onChange={(e) => setTo(e.target.value)}
            >
              <option value="">{canTake ? "Or choose someone" : "Choose someone"}</option>
              {staff.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.role_label})
                </option>
              ))}
            </select>
            <button className="btn g" disabled={busy || none || !to} onClick={() => assign(to)}>
              Assign
            </button>
          </>
        )}
      </div>
    </div>
  );
}
