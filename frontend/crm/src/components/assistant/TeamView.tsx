"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";
import PermissionsCard from "./PermissionsCard";

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
  clinics: string[];
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
type Team = {
  members: Member[];
  requests: Request[];
  can_manage: boolean;
  managed: Record<string, string>; // clinics you give access to: id -> name
};

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
  const [showMembers, setShowMembers] = useState(true);
  const [asRole, setAsRole] = useState<Record<string, string>>({});
  const [invite, setInvite] = useState({
    name: "",
    email: "",
    role: "front_desk",
  });
  const [inviteClinics, setInviteClinics] = useState<string[] | null>(null); // null: this clinic
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

      {managing && pending.length > 0 && (
        <section className="card" style={{ marginBottom: 14 }}>
          <h3 style={{ margin: "0 0 8px" }}>
            Requests to join{" "}
            {pending.length > 0 && (
              <span className="badge b-fu">{pending.length} waiting</span>
            )}
          </h3>
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
          <div className="row" style={{ gap: 10, alignItems: "center" }}>
            <h3 style={{ margin: 0, flex: 1 }}>
              {t.can_manage ? `Members (${t.members.length})` : "My profile"}
            </h3>
            <button
              className="btn g"
              onClick={() => setShowMembers(!showMembers)}
            >
              {showMembers ? "Close" : "Open"}
            </button>
          </div>
          {showMembers &&
            t.members.map((m) => {
              const locked =
                m.me ||
                m.role === "bb_admin" ||
                (m.role === "clinic_manager" && !bb);
              const can = managing && !locked;
              return (
                <div
                  key={m.id}
                  style={{
                    borderTop: "1px solid var(--line)",
                    padding: "12px 0",
                    display: "grid",
                    gap: 8,
                  }}
                >
                  <div
                    className="row"
                    style={{ gap: 12, flexWrap: "wrap", alignItems: "center" }}
                  >
                    <span
                      aria-hidden="true"
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: "50%",
                        background: "#EEF2F8",
                        display: "grid",
                        placeItems: "center",
                        fontWeight: 700,
                        fontSize: 13,
                        flex: "0 0 auto",
                      }}
                    >
                      {m.name
                        .split(" ")
                        .map((w) => w[0])
                        .slice(0, 2)
                        .join("")
                        .toUpperCase()}
                    </span>
                    <div style={{ flex: "1 1 220px", minWidth: 0 }}>
                      <b>{m.name}</b>
                      {m.me && <span className="sub2"> (you)</span>}
                      <div
                        className="sub2"
                        style={{ fontSize: 12.5, overflowWrap: "anywhere" }}
                      >
                        {m.email}
                        {m.phone ? ` · ${m.phone}` : ""}
                      </div>
                    </div>
                    {can ? (
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
                      <span style={{ fontWeight: 600 }}>{m.role_label}</span>
                    )}
                    <span className={`badge ${m.active ? "b-vi" : "b-in"}`}>
                      {m.active ? "Active" : "Disabled"}
                    </span>
                  </div>
                  <div
                    className="row"
                    style={{
                      gap: 16,
                      flexWrap: "wrap",
                      alignItems: "center",
                      paddingLeft: 48,
                      fontSize: 13,
                    }}
                  >
                    <div
                      className="row"
                      style={{ gap: 6, alignItems: "center" }}
                    >
                      <span className="sub2">Clinics</span>
                      {can ? (
                        <ClinicsPicker
                          managed={t.managed}
                          value={m.clinics}
                          busy={busy}
                          onChange={(clinics) =>
                            void call(
                              `/members/${m.id}/clinics`,
                              { clinics },
                              "Clinics saved",
                              "PUT",
                            )
                          }
                        />
                      ) : (
                        m.clinics.map((c) => (
                          <span key={c} className="badge b-bk">
                            {t.managed[c] ?? c}
                          </span>
                        ))
                      )}
                    </div>
                    <span className="sub2">
                      Last sign-in: {when(m.last_seen_at)}
                    </span>
                    {can && (
                      <span
                        className="row"
                        style={{ gap: 6, marginLeft: "auto", flexWrap: "wrap" }}
                      >
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
                        </button>
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
                              m.active ? "Access disabled" : "Access enabled",
                              "PUT",
                            );
                          }}
                        >
                          {m.active ? "Disable" : "Enable"}
                        </button>
                        <button
                          className="btn g"
                          disabled={busy}
                          onClick={() => {
                            if (
                              window.confirm(
                                `Remove ${m.name} from ${clinic}? With no other clinic, their login is deleted too.`,
                              )
                            )
                              void call(
                                `/members/${m.id}`,
                                undefined,
                                `${m.name} removed`,
                                "DELETE",
                              );
                          }}
                        >
                          Remove
                        </button>
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
        </section>
      )}

      {managing && clinicId && (
        <PermissionsCard
          clinicId={clinicId}
          clinic={clinic}
          people={t?.members ?? []}
        />
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
                !invite.email.includes("@") ||
                inviteClinics?.length === 0
              }
              onClick={async () => {
                const body = {
                  full_name: invite.name.trim(),
                  email: invite.email.trim(),
                  role: invite.role,
                  clinics: inviteClinics ?? (clinicId ? [clinicId] : []),
                };
                if (
                  await call("/invite", body, `Invite sent to ${body.email}`)
                ) {
                  setInvite({ name: "", email: "", role: "front_desk" });
                  setInviteClinics(null);
                }
              }}
            >
              Send invite
            </button>
          </div>
          {t && Object.keys(t.managed).length > 1 && (
            <div
              className="row"
              style={{ gap: 12, flexWrap: "wrap", marginTop: 8, fontSize: 13 }}
            >
              <b>Clinics:</b>
              {Object.entries(t.managed).map(([id, name]) => {
                const chosen = inviteClinics ?? (clinicId ? [clinicId] : []);
                return (
                  <label key={id} className="row" style={{ gap: 4 }}>
                    <input
                      type="checkbox"
                      checked={chosen.includes(id)}
                      onChange={(e) =>
                        setInviteClinics(
                          e.target.checked
                            ? [...chosen, id]
                            : chosen.filter((c) => c !== id),
                        )
                      }
                    />
                    {name} ({id})
                  </label>
                );
              })}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

/** The clinics a member can open: a chip for each (× takes it away; the last one stays, use Remove), and a
 * drop-down like Role to add one. Only the clinics you manage are listed. Each change is saved at once. */
function ClinicsPicker({
  managed,
  value,
  busy,
  onChange,
}: {
  managed: Record<string, string>;
  value: string[];
  busy: boolean;
  onChange: (clinics: string[]) => void;
}) {
  const more = Object.entries(managed).filter(([id]) => !value.includes(id));
  return (
    <div
      className="row"
      style={{ gap: 4, flexWrap: "wrap", alignItems: "center" }}
    >
      {value.map((c) => (
        <span key={c} className="badge b-bk" style={{ whiteSpace: "nowrap" }}>
          {managed[c] ?? c}
          {value.length > 1 && (
            <button
              type="button"
              aria-label={`Take away ${managed[c] ?? c}`}
              disabled={busy}
              onClick={() => onChange(value.filter((x) => x !== c))}
              style={{
                border: 0,
                background: "none",
                cursor: "pointer",
                marginLeft: 4,
                padding: 0,
                color: "inherit",
              }}
            >
              ×
            </button>
          )}
        </span>
      ))}
      {more.length > 0 && (
        <select
          className="sel"
          disabled={busy}
          value=""
          onChange={(e) =>
            e.target.value && onChange([...value, e.target.value])
          }
        >
          <option value="">+ Add clinic</option>
          {more.map(([id, name]) => (
            <option key={id} value={id}>
              {name} ({id})
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
