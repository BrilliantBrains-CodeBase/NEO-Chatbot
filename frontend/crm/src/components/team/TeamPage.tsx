"use client";

import { useCallback, useEffect, useState } from "react";
import Icon from "@/components/crm/Icon";
import Loading from "@/components/crm/Loading";
import { useCrm } from "@/components/crm/CrmProvider";
import { api } from "@/lib/api";
import ClinicsTab from "./ClinicsTab";
import { InviteForm } from "./MemberForms";
import MembersTab from "./MembersTab";
import RequestsTab from "./RequestsTab";
import RolesTab from "./RolesTab";
import { message, type Team } from "./shared";

// Team: one page for who can sign in, whichever side of the CRM / Dashboard switch you are on. Admins manage
// their clinic; Super Admins any clinic, and the clinics themselves.

type Tab = "members" | "requests" | "roles" | "clinics";

export default function TeamPage() {
  const { clinic, me, openModal, closeModal } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const superAdmin = !!me?.bb_admin;
  const [loaded, setLoaded] = useState<{ clinic: string; team: Team } | null>(null);
  const [failed, setFailed] = useState<{ clinic: string; text: string } | null>(null);
  const [tab, setTab] = useState<Tab>("members");

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Team>(`/v1/crm/team/${clinicId}`).then(
      (team) => live && setLoaded({ clinic: clinicId, team }),
      (e) => live && setFailed({ clinic: clinicId, text: message(e, "Could not load the team.") }),
    );
    return () => {
      live = false;
    };
  }, [clinicId]);

  const team = loaded && loaded.clinic === clinicId ? loaded.team : null;
  const error = failed && failed.clinic === clinicId && !team ? failed.text : "";
  const saved = useCallback(
    (t: Team) => {
      if (clinicId) setLoaded({ clinic: clinicId, team: t });
    },
    [clinicId],
  );
  /** One change to the team; the answer is the team as it is now. */
  const change = useCallback(
    async (path: string, method: string, body?: object, at?: string) => {
      const answer = await api<Team>(`/v1/crm/team/${at ?? clinicId}${path}`, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      });
      // Addressed through another clinic (they moved there): this clinic's list is read again.
      saved(at && at !== clinicId ? await api<Team>(`/v1/crm/team/${clinicId}`) : answer);
    },
    [clinicId, saved],
  );

  if (team && !team.can_manage)
    return (
      <div className="empty">
        <h2>No access</h2>
        Team is for Admins and Super Admins. Your details are in My profile.
      </div>
    );

  const waiting = team?.requests.filter((r) => r.status === "pending").length ?? 0;
  const tabs: [Tab, string, number | null][] = [
    ["members", "Members", team ? team.members.length : null],
    ["requests", "Requests", waiting || null],
    ["roles", "Roles & permissions", null],
    ...(superAdmin ? ([["clinics", "Clinics", null]] as [Tab, string, null][]) : []),
  ];

  return (
    <div className="tm">
      <div className="ph">
        <div>
          <h1>Team</h1>
          <p>Who can sign in to {clinic}, and what each person can do.</p>
        </div>
        {team && (
          <button
            type="button"
            className="btn"
            onClick={() =>
              openModal({
                title: "Invite a member",
                body: (
                  <InviteForm
                    team={team}
                    clinicId={clinicId ?? ""}
                    superAdmin={superAdmin}
                    change={change}
                    onClose={closeModal}
                  />
                ),
              })
            }
          >
            <Icon name="plus" />
            Invite member
          </button>
        )}
      </div>

      <div className="tabs" role="tablist" aria-label="Team">
        {tabs.map(([key, label, count]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            className={tab === key ? "on" : ""}
            onClick={() => setTab(key)}
          >
            {label}
            {count != null && <span className="c">{count}</span>}
          </button>
        ))}
      </div>

      {error && <div className="warnbox">{error}</div>}
      {!team && !error && <Loading />}
      {team && clinicId && (
        <>
          {tab === "members" && (
            <MembersTab
              team={team}
              clinic={clinic}
              clinicId={clinicId}
              superAdmin={superAdmin}
              change={change}
            />
          )}
          {tab === "requests" && (
            <RequestsTab team={team} superAdmin={superAdmin} change={change} />
          )}
          {tab === "roles" && (
            <RolesTab key={clinicId} clinicId={clinicId} clinic={clinic} people={team.members} />
          )}
          {tab === "clinics" && superAdmin && <ClinicsTab onOpen={() => setTab("members")} />}
        </>
      )}
    </div>
  );
}
