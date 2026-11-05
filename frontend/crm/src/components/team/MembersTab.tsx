"use client";

import { useMemo, useState } from "react";
import Icon from "@/components/crm/Icon";
import { useCrm } from "@/components/crm/CrmProvider";
import { EditForm } from "./MemberForms";
import {
  Confirm,
  lastSeen,
  Person,
  ROLES,
  roleLabel,
  RowMenu,
  type Member,
  type MenuItem,
  type Team,
} from "./shared";

// Everyone who can sign in to this clinic. Each row's changes are behind its ⋯, so nothing changes by a stray click.

type Change = (path: string, method: string, body?: object) => Promise<void>;

export default function MembersTab({
  team,
  clinic,
  clinicId,
  superAdmin,
  change,
}: {
  team: Team;
  clinic: string;
  clinicId: string;
  superAdmin: boolean;
  change: Change;
}) {
  const { openModal, closeModal, toast } = useCrm();
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return team.members.filter(
      (m) =>
        (!q || m.name.toLowerCase().includes(q) || m.email.toLowerCase().includes(q)) &&
        (!role || m.role === role) &&
        (!status || (status === "active") === m.active),
    );
  }, [team.members, search, role, status]);
  const present = [...new Set(team.members.map((m) => m.role))];
  // From before Front Desk was limited to one clinic: shown so it can be put right, never removed by itself.
  const overLimit = team.members.filter((m) => m.role === "front_desk" && m.clinics.length > 1);

  const canChange = (m: Member) =>
    !m.me &&
    (m.role === "bb_admin"
      ? team.can_add_admins
      : m.role !== "clinic_manager" || superAdmin);

  const ask = (title: string, text: string, action: string, run: () => Promise<void>, danger = false) =>
    openModal({
      title,
      body: (
        <Confirm text={text} action={action} danger={danger} onConfirm={run} onClose={closeModal} />
      ),
    });

  const menu = (m: Member): MenuItem[] => [
    {
      label: "Edit role and access",
      onClick: () =>
        openModal({
          title: "Edit member",
          body: (
            <EditForm
              member={m}
              team={team}
              clinic={clinic}
              clinicId={clinicId}
              superAdmin={superAdmin}
              change={change}
              onClose={closeModal}
            />
          ),
        }),
    },
    {
      label: "Send password reset",
      onClick: () =>
        ask(
          "Send password reset",
          `Email ${m.email} a link to set a new password?`,
          "Send link",
          async () => {
            await change(`/members/${m.id}/reset`, "POST");
            toast(`Password reset email sent to ${m.email}`);
          },
        ),
    },
    {
      label: m.active ? "Disable access" : "Enable access",
      onClick: () =>
        m.active
          ? ask(
              "Disable access",
              `${m.name} can no longer sign in to ${clinic}. Their details stay, and you can enable them again.`,
              "Disable",
              async () => {
                await change(`/members/${m.id}`, "PUT", { active: false });
                toast("Access disabled");
              },
              true,
            )
          : void change(`/members/${m.id}`, "PUT", { active: true }).then(
              () => toast("Access enabled"),
              () => toast("Could not enable access"),
            ),
    },
    {
      label: `Remove from ${clinic}`,
      danger: true,
      onClick: () =>
        ask(
          `Remove ${m.name}`,
          `Remove ${m.name} from ${clinic}? With no other clinic left, their login is deleted too.`,
          "Remove",
          async () => {
            await change(`/members/${m.id}`, "DELETE");
            toast(`${m.name} removed`);
          },
          true,
        ),
    },
  ];

  const filtered = !!(search.trim() || role || status);
  return (
    <>
      {overLimit.length > 0 && (
        <div className="warnbox" style={{ marginBottom: 12 }}>
          {overLimit.map((m) => m.name).join(", ")}{" "}
          {overLimit.length === 1 ? "is" : "are"} Front Desk in more than one clinic. Front Desk should work in one
          clinic only: open Edit role and access to keep one.
        </div>
      )}
      <div className="tm-filters">
        <label className="search">
          <Icon name="search" />
          <input
            placeholder="Search name or email"
            aria-label="Search members by name or email"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <select
          className="sel"
          aria-label="Filter by role"
          value={role}
          onChange={(e) => setRole(e.target.value)}
        >
          <option value="">All roles</option>
          {present.map((r) => (
            <option key={r} value={r}>
              {roleLabel(r)}
            </option>
          ))}
        </select>
        <select
          className="sel"
          aria-label="Filter by status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="disabled">Disabled</option>
        </select>
      </div>

      <div className="tw">
        <table className="tm-table">
          <thead>
            <tr>
              <th>Member</th>
              <th>Role</th>
              <th>Clinics</th>
              <th>Status</th>
              <th>Last sign-in</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="tm-none">
                  {filtered ? "No one matches these filters." : `No one can sign in to ${clinic} yet. Invite your first member.`}
                </td>
              </tr>
            )}
            {rows.map((m) => (
              <tr key={m.id}>
                <td>
                  <Person name={m.name} sub={m.phone ? `${m.email} · ${m.phone}` : m.email} you={m.me} />
                </td>
                <td>
                  <span className={`badge ${ROLES[m.role]?.badge ?? "b-cl"}`}>{m.role_label}</span>
                  {m.role === "doctor" && !m.doctor_id && (
                    <div className="tm-sub tm-warn">Not linked to a doctor record</div>
                  )}
                </td>
                <td>
                  {m.role === "bb_admin" ? (
                    <span className="tm-sub">All clinics</span>
                  ) : (
                    <div className="tm-chips">
                      {m.clinics.map((c) => (
                        <span key={c} className="tm-chip">
                          {team.managed[c] ?? c}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                <td>
                  <span className={`tm-status${m.active ? " on" : ""}`}>
                    {m.active ? "Active" : "Disabled"}
                  </span>
                </td>
                <td className="tm-sub">{lastSeen(m.last_seen_at)}</td>
                <td className="tm-end">
                  {canChange(m) && <RowMenu label={`Actions for ${m.name}`} items={menu(m)} />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > 0 && (
        <p className="tm-count">
          Showing {rows.length} of {team.members.length}
        </p>
      )}
    </>
  );
}
