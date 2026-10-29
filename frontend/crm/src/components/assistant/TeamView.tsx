"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";

// Team & access. Dashboard (manage): access requests (approve as a role, or reject), members (role, access
// on/off, password reset) and invites; only BB Admin approves, invites or changes Clinic Managers.
// CRM → Team (view): each person sees their own profile; Clinic Managers and BB Admin see everyone.

type Member = {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  role: string;
  role_label: string;
  active: boolean;
  last_seen_at: string | null;
  me: boolean;
};
type Request = {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  role: string;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
};
type Team = { members: Member[]; requests: Request[]; can_manage: boolean };

const ROLES: [string, string][] = [
  ["front_desk", "Front Desk"],
  ["doctor", "Doctor"],
  ["clinic_manager", "Clinic Manager"],
];
const label = (role: string) =>
  ROLES.find(([k]) => k === role)?.[1] ?? "BB Admin";
const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-IN") : "Never";

export default function TeamView({ manage }: { manage: boolean }) {
  const { clinic, me, toast } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const bb = !!me?.bb_admin;
  const [team, setTeam] = useState<{ clinic: string; t: Team } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [asRole, setAsRole] = useState<Record<string, string>>({});
  const [invite, setInvite] = useState({
    name: "",
    email: "",
    role: "front_desk",
  });
  const url = `/v1/crm/team/${clinicId}`;

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Team>(`/v1/crm/team/${clinicId}`).then(
      (t) => live && setTeam({ clinic: clinicId, t }),
      (e) =>
        live &&
        setError(
          e instanceof ApiError ? e.message : "Could not load the team.",
        ),
    );
    return () => {
      live = false;
    };
  }, [clinicId]);

  async function call(
    path: string,
    body: object | undefined,
    done: string,
    method = "POST",
  ) {
    if (!clinicId) return false;
    setBusy(true);
    setError("");
    try {
      const t = await api<Team>(url + path, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      });
      setTeam({ clinic: clinicId, t });
      toast(done);
      return true;
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
      return false;
    } finally {
      setBusy(false);
    }
  }

  const t = team && team.clinic === clinicId ? team.t : null;
  const managing = manage && !!t?.can_manage;
  const pending = t?.requests.filter((r) => r.status === "pending") ?? [];
  const decided = t?.requests.filter((r) => r.status !== "pending") ?? [];
  // A Clinic Manager role (asked for, or given) is BB Admin's to decide.
  const roles = ROLES.filter(([k]) => bb || k !== "clinic_manager");

  return (
    <div className="page" style={{ maxWidth: 900 }}>
      <h2 style={{ margin: "0 0 4px" }}>{manage ? "Team & access" : "Team"}</h2>
      <p className="sub2" style={{ margin: "0 0 14px" }}>
        {managing
          ? `Who can sign in to ${clinic}, their roles, and requests to join. Only BB Admin approves or changes Clinic Managers.`
          : t?.can_manage
            ? `Everyone who can sign in to ${clinic}.`
            : "Your profile. Your clinic manager manages access."}
      </p>
      {error && <div className="warnbox">{error}</div>}
      {!t && !error && <p className="sub2">Loading…</p>}

      {managing && (
        <section className="card" style={{ marginBottom: 14 }}>
          <h3 style={{ margin: "0 0 8px" }}>
            Requests to join{" "}
            {pending.length > 0 && (
              <span className="badge b-fu">{pending.length} waiting</span>
            )}
          </h3>
          {pending.length === 0 && (
            <p className="sub2" style={{ margin: 0 }}>
              No requests waiting. People ask from &quot;Create an account&quot;
              on the sign-in page with the clinic code <b>{clinicId}</b>.
            </p>
          )}
          {pending.map((r) => {
            const mine = bb || r.role !== "clinic_manager";
            return (
              <div
                key={r.id}
                className="row"
                style={{
                  gap: 8,
                  flexWrap: "wrap",
                  padding: "8px 0",
                  borderTop: "1px solid var(--line)",
                }}
              >
                <div style={{ flex: 1, minWidth: 200 }}>
                  <b>{r.name}</b> · {r.email}
                  {r.phone ? ` · ${r.phone}` : ""}
                  <div className="sub2" style={{ fontSize: 12 }}>
                    Asked to join as {label(r.role)} on {when(r.created_at)}
                  </div>
                </div>
                {mine ? (
                  <>
                    <select
                      className="sel"
                      value={asRole[r.id] ?? r.role}
                      onChange={(e) =>
                        setAsRole({ ...asRole, [r.id]: e.target.value })
                      }
                    >
                      {roles.map(([k, v]) => (
                        <option key={k} value={k}>
                          as {v}
                        </option>
                      ))}
                    </select>
                    <button
                      className="btn"
                      disabled={busy}
                      onClick={() =>
                        void call(
                          `/requests/${r.id}`,
                          { status: "approved", role: asRole[r.id] ?? r.role },
                          `${r.name} can now sign in`,
                        )
                      }
                    >
                      Approve
                    </button>
                    <button
                      className="btn g"
                      disabled={busy}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Reject ${r.name}'s request? Their login is removed.`,
                          )
                        )
                          void call(
                            `/requests/${r.id}`,
                            { status: "rejected" },
                            "Request rejected",
                          );
                      }}
                    >
                      Reject
                    </button>
                  </>
                ) : (
                  <span className="sub2">
                    Waiting for BB Admin (Clinic Manager request)
                  </span>
                )}
              </div>
            );
          })}
          {decided.length > 0 && (
            <details style={{ marginTop: 8 }}>
              <summary className="sub2" style={{ cursor: "pointer" }}>
                Decided requests ({decided.length})
              </summary>
              {decided.map((r) => (
                <p key={r.id} style={{ margin: "4px 0", fontSize: 12.5 }}>
                  <span
                    className={`badge ${r.status === "approved" ? "b-vi" : "b-in"}`}
                  >
                    {r.status === "approved" ? "Approved" : "Rejected"}
                  </span>{" "}
                  {r.name} · {r.email} · {label(r.role)} · by{" "}
                  {r.decided_by ?? "—"} on {when(r.decided_at)}
                </p>
              ))}
            </details>
          )}
        </section>
      )}

      {t && (
        <section className="card" style={{ marginBottom: 14 }}>
          <h3 style={{ margin: "0 0 8px" }}>
            {t.can_manage ? `Members (${t.members.length})` : "My profile"}
          </h3>
          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: 13,
              }}
            >
              <thead>
                <tr className="sub2" style={{ textAlign: "left" }}>
                  <th style={{ padding: "4px 6px 4px 0" }}>Name</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Last sign-in</th>
                  {managing && <th />}
                </tr>
              </thead>
              <tbody>
                {t.members.map((m) => {
                  const locked =
                    m.me ||
                    m.role === "bb_admin" ||
                    (m.role === "clinic_manager" && !bb);
                  return (
                    <tr
                      key={m.id}
                      style={{ borderTop: "1px solid var(--line)" }}
                    >
                      <td style={{ padding: "6px 6px 6px 0" }}>
                        <b>{m.name}</b>
                        {m.me && <span className="sub2"> (you)</span>}
                        <div className="sub2" style={{ fontSize: 12 }}>
                          {m.email}
                          {m.phone ? ` · ${m.phone}` : ""}
                        </div>
                      </td>
                      <td>
                        {managing && !locked ? (
                          <select
                            className="sel"
                            disabled={busy}
                            value={m.role}
                            onChange={(e) =>
                              void call(
                                `/members/${m.id}`,
                                { role: e.target.value },
                                "Role changed",
                                "PUT",
                              )
                            }
                          >
                            {roles.map(([k, v]) => (
                              <option key={k} value={k}>
                                {v}
                              </option>
                            ))}
                          </select>
                        ) : (
                          m.role_label
                        )}
                      </td>
                      <td>
                        <span className={`badge ${m.active ? "b-vi" : "b-in"}`}>
                          {m.active ? "Active" : "Disabled"}
                        </span>
                      </td>
                      <td className="sub2">{when(m.last_seen_at)}</td>
                      {managing && (
                        <td
                          style={{ whiteSpace: "nowrap", textAlign: "right" }}
                        >
                          {!locked && (
                            <>
                              <button
                                className="btn g"
                                disabled={busy}
                                onClick={() =>
                                  void call(
                                    `/members/${m.id}/reset`,
                                    undefined,
                                    `Password reset email sent to ${m.email}`,
                                  )
                                }
                              >
                                Reset password
                              </button>{" "}
                              <button
                                className="btn g"
                                disabled={busy}
                                onClick={() => {
                                  if (
                                    m.active &&
                                    !window.confirm(
                                      `Disable ${m.name}? They can no longer sign in to ${clinic}.`,
                                    )
                                  )
                                    return;
                                  void call(
                                    `/members/${m.id}`,
                                    { active: !m.active },
                                    m.active
                                      ? "Access disabled"
                                      : "Access enabled",
                                    "PUT",
                                  );
                                }}
                              >
                                {m.active ? "Disable" : "Enable"}
                              </button>
                            </>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {managing && (
        <section className="card">
          <h3 style={{ margin: "0 0 8px" }}>Invite someone</h3>
          <p className="sub2" style={{ margin: "0 0 8px" }}>
            They get an email to set their password, then sign in with this
            role. Someone who already has a login gets the role straight away.
          </p>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <input
              className="f"
              style={{ flex: 1, minWidth: 160 }}
              placeholder="Full name"
              maxLength={100}
              value={invite.name}
              onChange={(e) => setInvite({ ...invite, name: e.target.value })}
            />
            <input
              className="f"
              style={{ flex: 1, minWidth: 200 }}
              type="email"
              placeholder="name@clinic.com"
              maxLength={120}
              value={invite.email}
              onChange={(e) => setInvite({ ...invite, email: e.target.value })}
            />
            <select
              className="sel"
              value={invite.role}
              onChange={(e) => setInvite({ ...invite, role: e.target.value })}
            >
              {roles.map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
            <button
              className="btn"
              disabled={
                busy ||
                invite.name.trim().length < 2 ||
                !invite.email.includes("@")
              }
              onClick={async () => {
                const body = {
                  full_name: invite.name.trim(),
                  email: invite.email.trim(),
                  role: invite.role,
                };
                if (await call("/invite", body, `Invite sent to ${body.email}`))
                  setInvite({ name: "", email: "", role: "front_desk" });
              }}
            >
              Send invite
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
