"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import { INBOX_TABS } from "@/lib/api";
import { SECTIONS } from "@/lib/assistant";
import { CLINIC_CONTENT } from "@/lib/sample-data";
import { useCrm } from "./CrmProvider";
import Icon, { type IconName } from "./Icon";

type Group = "leads" | "inbox" | "doctors";

// Stage links open that tab of the Leads screen (live counts are on its tabs).
const LEAD_STAGES = [
  ["new", "New"],
  ["follow_up", "Follow Up"],
  ["booked", "Booked"],
  ["visited", "Visited"],
  ["lost", "Lost"],
  ["invalid", "Invalid"],
] as const;

export default function Sidebar({
  open,
  onNavigate,
}: {
  open: boolean;
  onNavigate: () => void;
}) {
  const crm = useCrm();
  const path = usePathname();
  const params = useSearchParams();
  // Leads starts open, as in the design.
  const [expanded, setExpanded] = useState<Record<Group, boolean>>({
    leads: true,
    inbox: false,
    doctors: false,
  });
  const toggle = (g: Group) => setExpanded((e) => ({ ...e, [g]: !e[g] }));

  // Sample counts are hidden: each menu count comes back when its screen reads live data.
  const LIVE_COUNTS = false;
  const n = (x: number) => (LIVE_COUNTS && crm.ready ? x : undefined);
  const stage = params.get("stage") ?? "";
  const tab = params.get("tab") ?? "book";
  const inboxTotal = Object.values(crm.inbox ?? {}).reduce((a, b) => a + b, 0);
  const doc = params.get("doc") ?? "";

  const item = (
    href: string,
    icon: IconName,
    label: string,
    on: boolean,
    count?: number,
  ) => (
    <Link
      key={href}
      href={href}
      className={on ? "on" : ""}
      onClick={onNavigate}
      title={label}
    >
      <Icon name={icon} />
      <span>{label}</span>
      {count != null && <span className="c">{count}</span>}
    </Link>
  );
  const group = (
    g: Group,
    icon: IconName,
    label: string,
    count: number | undefined,
    sub: ReactNode,
  ) => (
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
  const subItem = (
    href: string,
    label: string,
    on: boolean,
    count?: number,
  ) => (
    <Link
      key={href}
      href={href}
      className={on ? "on" : ""}
      onClick={onNavigate}
    >
      {label}
      {count != null && <span className="c">{count}</span>}
    </Link>
  );

  return (
    <aside className={`sb${open ? " on" : ""}`} aria-label="Main menu">
      <div className="sb-top">
        <i>N</i>
        <span className="sb-name">NEO CRM</span>
      </div>
      {path.startsWith("/assistant") ? (
        <nav className="nav">
          {/* The Assistant console's menu (design: Patient Assistant Console), grouped as in the design. */}
          {[...new Set(SECTIONS.map((s) => s.group))].map((g) => (
            <div key={g || "top"}>
              {g && <div className="grp">{g.toUpperCase()}</div>}
              {SECTIONS.filter(
                (s) => s.group === g && (!s.bbOnly || crm.me?.bb_admin),
              ).map((s) =>
                item(
                  `/assistant/${s.id}`,
                  s.icon,
                  s.label,
                  path === `/assistant/${s.id}`,
                ),
              )}
            </div>
          ))}
        </nav>
      ) : (
        <nav className="nav">
          <div className="grp">MAIN</div>
          {item("/dashboard", "dash", "Dashboard", path === "/dashboard")}
          {group(
            "leads",
            "appt",
            "Leads",
            undefined,
            <>
              {LEAD_STAGES.map(([key, label]) =>
                subItem(
                  `/leads?stage=${key}`,
                  label,
                  path === "/leads" && stage === key,
                ),
              )}
            </>,
          )}
          {group(
            "inbox",
            "req",
            "Inbox",
            inboxTotal || undefined,
            INBOX_TABS.map(([key, label]) =>
              subItem(
                `/inbox?tab=${key}`,
                label,
                path === "/inbox" && tab === key,
                crm.inbox?.[key] || undefined,
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
                subItem(
                  `/doctors?doc=${encodeURIComponent(d)}`,
                  d,
                  path === "/doctors" && doc === d,
                ),
              )}
            </>,
          )}
          <div className="dv" />
          {item(
            "/appointments",
            "cal",
            "Appointments",
            path === "/appointments",
          )}
          {item(
            "/tasks",
            "task",
            "Tasks",
            path === "/tasks",
            n(crm.stageCount("fu")),
          )}
          {item("/patients", "con", "Patients", path === "/patients")}
          <div className="dv" />
          {item("/reports", "rep", "Reports", path === "/reports")}
          <div className="dv" />
          <div className="grp">MANAGER</div>
          {item("/team", "team", "Team", path === "/team")}
          {item("/settings", "set", "Settings", path === "/settings")}
        </nav>
      )}
    </aside>
  );
}
