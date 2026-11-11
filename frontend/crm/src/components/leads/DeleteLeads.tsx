"use client";

import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError } from "@/lib/api";
import { STAGE_LABEL, when } from "./labels";

// Deleting leads: Clinic Managers and Super Admin only (the backend refuses everyone else too). A deleted
// lead is hidden everywhere and can be restored for 30 days; its upcoming appointments are cancelled.

type Done = { done: string[]; problems: string[] };
type Deleted = {
  code: string;
  name: string;
  phone: string | null;
  stage: string;
  deleted_at: string;
  removed_on: string;
};

const RED = { background: "var(--err)" };

/** The confirm box: "Delete 3 leads?" with what happens, then Delete. */
export function ConfirmDelete({
  clinicId,
  codes,
  label,
  onDone,
}: {
  clinicId: string;
  codes: string[];
  label: string; // "NFHT-00044 Asha Rao" or "3 leads"
  onDone: (deleted: string[]) => void;
}) {
  const { toast, closeModal } = useCrm();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function go() {
    setBusy(true);
    setError("");
    try {
      const r = await api<Done>("/v1/crm/leads/delete", {
        method: "POST",
        body: JSON.stringify({ clinic: clinicId, codes }),
      });
      closeModal();
      toast(
        r.problems.length
          ? `Deleted ${r.done.length}; ${r.problems.length} skipped`
          : `Deleted ${label}`,
      );
      onDone(r.done);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete.");
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      {error && <div className="warnbox">{error}</div>}
      <p style={{ margin: 0 }}>
        Delete <b>{label}</b>?
      </p>
      <ul className="sub2" style={{ margin: 0, paddingLeft: 18 }}>
        <li>
          Hidden at once from Leads, Inbox, Patients, Appointments and the
          Dashboard.
        </li>
        <li>
          Upcoming appointments are cancelled, so the doctor&apos;s time is free
          again.
        </li>
        <li>
          Open requests and tasks are closed. Past visits stay in its history.
        </li>
        <li>
          You can restore it from Recently deleted for 30 days; after that it is
          removed for good.
        </li>
      </ul>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button
          type="button"
          className="btn g"
          disabled={busy}
          onClick={closeModal}
        >
          Cancel
        </button>
        <button
          type="button"
          className="btn"
          style={RED}
          disabled={busy}
          onClick={go}
        >
          {busy ? "Deleting…" : "Delete"}
        </button>
      </div>
    </div>
  );
}

/** Recently deleted (30 days): each with Restore. */
export function RecentlyDeleted({
  clinicId,
  onRestored,
}: {
  clinicId: string;
  onRestored: () => void;
}) {
  const { toast } = useCrm();
  const [items, setItems] = useState<Deleted[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    let live = true;
    api<Deleted[]>(`/v1/crm/deleted-leads?clinic=${clinicId}`).then(
      (d) => live && setItems(d),
      (e) =>
        live &&
        setError(
          e instanceof ApiError ? e.message : "Could not load deleted leads.",
        ),
    );
    return () => {
      live = false;
    };
  }, [clinicId]);

  async function restore(code: string) {
    setBusy(code);
    setError("");
    try {
      const r = await api<Done>("/v1/crm/leads/restore", {
        method: "POST",
        body: JSON.stringify({ clinic: clinicId, codes: [code] }),
      });
      if (r.problems.length) {
        setError(r.problems.join(" "));
      } else {
        setItems((now) => (now ?? []).filter((d) => d.code !== code));
        toast(`Restored ${code}`);
        onRestored();
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not restore.");
    }
    setBusy("");
  }

  return (
    <div style={{ display: "grid", gap: 10 }}>
      <p className="sub2" style={{ margin: 0 }}>
        Leads deleted in the last 30 days. Restoring brings a lead back as it
        was; its cancelled appointments stay cancelled.
      </p>
      {error && <div className="warnbox">{error}</div>}
      {items === null && !error && <p className="sub2">Loading…</p>}
      {items?.length === 0 && (
        <p className="sub2">Nothing deleted in the last 30 days.</p>
      )}
      {!!items?.length && (
        <div
          style={{ maxHeight: 360, overflowY: "auto", display: "grid", gap: 6 }}
        >
          {items.map((d) => (
            <div
              key={d.code}
              className="card"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "8px 12px",
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <b>{d.name}</b> <span className="sub2">{d.code}</span>{" "}
                <span className={`badge ${STAGE_LABEL[d.stage]?.[1] ?? ""}`}>
                  {STAGE_LABEL[d.stage]?.[0] ?? d.stage}
                </span>
                <div className="sub2">
                  {d.phone ?? "No phone"} · deleted {when(d.deleted_at)} ·
                  removed for good on {d.removed_on}
                </div>
              </div>
              <button
                type="button"
                className="btn g sm"
                disabled={!!busy}
                onClick={() => restore(d.code)}
              >
                {busy === d.code ? "Restoring…" : "Restore"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
