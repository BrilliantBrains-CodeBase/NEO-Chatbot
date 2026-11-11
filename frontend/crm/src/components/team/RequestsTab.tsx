"use client";

import { useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import {
  Confirm,
  dateTime,
  givableRoles,
  message,
  Person,
  roleLabel,
  type AccessRequest,
  type Team,
} from "./shared";

// People who used "Create an account" and wait for a decision, and the last decisions taken.

type Change = (path: string, method: string, body?: object) => Promise<void>;

export default function RequestsTab({
  team,
  superAdmin,
  change,
}: {
  team: Team;
  superAdmin: boolean;
  change: Change;
}) {
  const { openModal, closeModal, toast } = useCrm();
  const [view, setView] = useState<"waiting" | "decided">("waiting");
  const [asRole, setAsRole] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const waiting = team.requests.filter((r) => r.status === "pending");
  const decided = team.requests.filter((r) => r.status !== "pending");
  const roles = givableRoles(team, superAdmin).filter((r) => r !== "bb_admin");

  async function approve(r: AccessRequest) {
    setBusy(r.id);
    setError("");
    try {
      await change(`/requests/${r.id}`, "POST", {
        status: "approved",
        role: asRole[r.id] ?? r.role,
      });
      toast(`${r.name} can now sign in`);
    } catch (e) {
      setError(message(e, "Could not approve. Please try again."));
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <div className="tm-filters">
        <div className="seg" style={{ marginLeft: 0 }}>
          <button
            type="button"
            className={view === "waiting" ? "on" : ""}
            onClick={() => setView("waiting")}
          >
            Waiting ({waiting.length})
          </button>
          <button
            type="button"
            className={view === "decided" ? "on" : ""}
            onClick={() => setView("decided")}
          >
            Decided ({decided.length})
          </button>
        </div>
      </div>
      {error && (
        <div className="warnbox" role="alert" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}

      {view === "waiting" ? (
        <div className="tw">
          <table className="tm-table">
            <thead>
              <tr>
                <th>Person</th>
                <th>Asked to join as</th>
                <th>Asked on</th>
                <th>Approve as</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {waiting.length === 0 && (
                <tr>
                  <td colSpan={5} className="tm-none">
                    No one is waiting. New requests from Create an account
                    appear here.
                  </td>
                </tr>
              )}
              {waiting.map((r) => {
                const mine = superAdmin || r.role !== "clinic_manager";
                return (
                  <tr key={r.id}>
                    <td>
                      <Person
                        name={r.name}
                        sub={r.phone ? `${r.email} · ${r.phone}` : r.email}
                      />
                    </td>
                    <td>{roleLabel(r.role)}</td>
                    <td className="tm-sub">{dateTime(r.created_at)}</td>
                    <td>
                      {mine ? (
                        <select
                          className="sel"
                          aria-label={`Approve ${r.name} as`}
                          value={asRole[r.id] ?? r.role}
                          onChange={(e) =>
                            setAsRole({ ...asRole, [r.id]: e.target.value })
                          }
                        >
                          {roles.map((k) => (
                            <option key={k} value={k}>
                              {roleLabel(k)}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="tm-sub">
                          Waiting for a Super Admin
                        </span>
                      )}
                    </td>
                    <td className="tm-end">
                      {mine && (
                        <div className="tm-rowbtns">
                          <button
                            type="button"
                            className="btn g sm"
                            disabled={!!busy}
                            onClick={() =>
                              openModal({
                                title: `Reject ${r.name}`,
                                body: (
                                  <Confirm
                                    text={`Reject this request? ${r.name}'s login is removed unless they have access to another clinic.`}
                                    action="Reject"
                                    danger
                                    onConfirm={async () => {
                                      await change(
                                        `/requests/${r.id}`,
                                        "POST",
                                        { status: "rejected" },
                                      );
                                      toast("Request rejected");
                                    }}
                                    onClose={closeModal}
                                  />
                                ),
                              })
                            }
                          >
                            Reject
                          </button>
                          <button
                            type="button"
                            className="btn sm"
                            disabled={!!busy}
                            onClick={() => void approve(r)}
                          >
                            {busy === r.id ? "Approving…" : "Approve"}
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="tw">
          <table className="tm-table">
            <thead>
              <tr>
                <th>Person</th>
                <th>Role</th>
                <th>Decision</th>
                <th>Decided by</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {decided.length === 0 && (
                <tr>
                  <td colSpan={5} className="tm-none">
                    No decisions yet.
                  </td>
                </tr>
              )}
              {decided.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Person name={r.name} sub={r.email} />
                  </td>
                  <td>{roleLabel(r.role)}</td>
                  <td>
                    <span
                      className={`badge ${r.status === "approved" ? "b-vi" : "b-in"}`}
                    >
                      {r.status === "approved" ? "Approved" : "Rejected"}
                    </span>
                  </td>
                  <td className="tm-sub">{r.decided_by ?? "—"}</td>
                  <td className="tm-sub">{dateTime(r.decided_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
