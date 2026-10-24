"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import { CLINIC_CONTENT, REQUEST_TABS, STAGES } from "@/lib/sample-data";
import { useCrm } from "./CrmProvider";
import Icon, { type IconName } from "./Icon";

type Group = "leads" | "inbox" | "doctors";

export default function Sidebar({ open, onNavigate }: { open: boolean; onNavigate: () => void }) {
  const crm = useCrm();
  const path = usePathname();
  const params = useSearchParams();
  // Leads starts open, as in the design.
  const [expanded, setExpanded] = useState<Record<Group, boolean>>({ leads: true, inbox: false, doctors: false });
  const toggle = (g: Group) => setExpanded((e) => ({ ...e, [g]: !e[g] }));

  // Counts show once the data has loaded.
  const n = (x: number) => (crm.ready ? x : undefined);
  const stage = params.get("stage") ?? "new";
  const tab = params.get("tab") ?? "appt";
  const doc = params.get("doc") ?? "";

  const item = (href: string, icon: IconName, label: string, on: boolean, count?: number) => (
    <Link href={href} className={on ? "on" : ""} onClick={onNavigate}>
      <Icon name={icon} />
      <span>{label}</span>
      {count != null && <span className="c">{count}</span>}
    </Link>
  );
  const group = (g: Group, icon: IconName, label: string, count: number | undefined, sub: ReactNode) => (
    <>
      <a
        className={expanded[g] ? "open" : ""}
        role="button"
        aria-expanded={expanded[g]}
        tabIndex={0}
        onClick={() => toggle(g)}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && toggle(g)}
      >
        <Icon name={icon} />
        <span>{label}</span>
        {count != null && <span className="c">{count}</span>}
        <Icon name="chev" className="chev" />
      </a>
      {expanded[g] && <div className="sub">{sub}</div>}
    </>
  );
  const subItem = (href: string, label: string, on: boolean, count?: number) => (
    <Link key={href} href={href} className={on ? "on" : ""} onClick={onNavigate}>
      {label}
      {count != null && <span className="c">{count}</span>}
    </Link>
  );

  return (
    <aside className={`sb${open ? " on" : ""}`} aria-label="Main menu">
      <div className="sb-top">
        <i>N</i>NEO CRM
      </div>
      <nav className="nav">
        <div className="grp">MAIN</div>
        {item("/dashboard", "dash", "Dashboard", path === "/dashboard")}
        {group(
          "leads",
          "appt",
          "Leads",
          undefined,
          <>
            {STAGES.slice(0, 4).map((s) =>
              subItem(`/leads?stage=${s.key}`, s.label, path === "/leads" && stage === s.key, n(crm.stageCount(s.key))),
            )}
            {subItem("/leads?stage=lo", "Lost & Invalid", path === "/leads" && stage === "lo", n(crm.stageCount("lo")))}
          </>,
        )}
        {group(
          "inbox",
          "req",
          "Inbox",
          n(crm.inboxCount),
          REQUEST_TABS.map((t) =>
            subItem(
              `/inbox?tab=${t.key}`,
              t.label,
              path === "/inbox" && tab === t.key,
              t.key === "chat" ? undefined : n(crm.pending(t.key)),
            ),
          ),
        )}
        {group(
          "doctors",
          "doc",
          "Doctors Availability",
          undefined,
          <>
            {subItem("/doctors", "All doctors", path === "/doctors" && !doc)}
            {CLINIC_CONTENT[crm.clinic].docs.map((d) =>
              subItem(`/doctors?doc=${encodeURIComponent(d)}`, d, path === "/doctors" && doc === d),
            )}
          </>,
        )}
        <div className="dv" />
        {item("/appointments", "cal", "Appointments", path === "/appointments")}
        {item("/tasks", "task", "Tasks", path === "/tasks", n(crm.stageCount("fu")))}
        {item("/patients", "con", "Patients", path === "/patients")}
        <div className="dv" />
        {item("/reports", "rep", "Reports", path === "/reports")}
        <div className="dv" />
        <div className="grp">MANAGER</div>
        {item("/team", "team", "Team", path === "/team")}
        {item("/settings", "set", "Settings", path === "/settings")}
      </nav>
    </aside>
  );
}
