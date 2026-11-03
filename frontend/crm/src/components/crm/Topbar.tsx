"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { Clinic } from "@/lib/sample-data";
import AddLeadForm from "@/components/leads/AddLeadForm";
import { level } from "@/lib/access";
import { useBellOff } from "@/lib/bell";
import { useCrm } from "./CrmProvider";
import Icon from "./Icon";

const NOTICE: Record<string, string> = {
  book: "Booking request",
  online: "Online consult",
  cancel: "Cancellation",
  reschedule: "Reschedule",
  callback: "Callback",
  question: "Question",
};
function ago(iso: string) {
  const min = Math.max(
    1,
    Math.round((Date.now() - new Date(iso).getTime()) / 60000),
  );
  if (min < 60) return `${min} min ago`;
  if (min < 1440) return `${Math.round(min / 60)} h ago`;
  return `${Math.round(min / 1440)} d ago`;
}

export default function Topbar({ onMenu }: { onMenu: () => void }) {
  const crm = useCrm();
  // The bell shows only the request types left on in Settings → Bell notifications.
  const bellOff = useBellOff();
  const pending = Object.entries(crm.inbox ?? {})
    .filter(([type]) => !bellOff.includes(type))
    .reduce((a, [, n]) => a + n, 0);
  const clinicId = crm.me?.clinics.find((c) => c.name === crm.clinic)?.id;
  const path = usePathname();
  const inConsole = path.startsWith("/assistant");
  const compact = path === "/assistant/menu"; // the workflow canvas needs the whole page
  const router = useRouter();
  const [open, setOpen] = useState<"profile" | "bell" | null>(null);
  const menu = open === "profile";
  const setMenu = (on: boolean) => setOpen(on ? "profile" : null);
  const menuRef = useRef<HTMLDivElement>(null);
  const bellRef = useRef<HTMLDivElement>(null);

  // The menus close on any click outside them.
  useEffect(() => {
    if (!open) return;
    const ref = open === "profile" ? menuRef : bellRef;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(null);
    };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [open]);

  const go = (href: string) => {
    setOpen(null);
    router.push(href);
  };
  // Newest first, the latest 8.
  const latest = crm.inboxItems
    .filter((i) => !bellOff.includes(i.type))
    .slice(0, 8);

  return (
    <header className={`tb${compact ? " tb-compact" : ""}`}>
      <button className="ham" aria-label="Open menu" onClick={onMenu}>
        <Icon name="menu" />
      </button>
      <select
        className="sel"
        aria-label="Clinic"
        value={crm.clinic}
        onChange={(e) => crm.setClinic(e.target.value as Clinic)}
      >
        {crm.clinics.map((c) => (
          <option key={c}>{c}</option>
        ))}
      </select>
      {level(crm.me, crm.clinic, "dash_open") !== "hidden" && (
        <div className="seg" role="tablist" aria-label="Workspace">
          <button
            role="tab"
            aria-selected={!inConsole}
            className={inConsole ? "" : "on"}
            onClick={() => router.push("/dashboard")}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            <Icon name="team" />
            CRM
          </button>
          <button
            role="tab"
            aria-selected={inConsole}
            className={inConsole ? "on" : ""}
            onClick={() => router.push("/assistant/appearance")}
            style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          >
            <Icon name="dash" />
            Dashboard
          </button>
        </div>
      )}
      {!inConsole && (
        <label className="search hide-m">
          <Icon name="search" />
          <input
            placeholder="Search name, phone or treatment"
            aria-label="Search leads by name, phone or treatment"
            onKeyDown={(e) => {
              if (e.key === "Enter")
                router.push(
                  `/leads?q=${encodeURIComponent(e.currentTarget.value.trim())}`,
                );
            }}
          />
        </label>
      )}
      <div id="tb-slot" className="tb-slot" />
      <span className="sp" />
      <div ref={bellRef} style={{ position: "relative" }}>
        <button
          className="ib"
          aria-label="Notifications"
          aria-expanded={open === "bell"}
          onClick={() => setOpen(open === "bell" ? null : "bell")}
        >
          <Icon name="bell" />
          {!!pending && <b>{pending}</b>}
        </button>
        <div
          className={`pmenu${open === "bell" ? " on" : ""}`}
          style={{ top: 44, right: 0, width: 320 }}
          role="menu"
        >
          <div className="who">
            <b>Notifications</b>
            <span>
              {pending ? `${pending} waiting in the Inbox` : "Nothing waiting"}
            </span>
          </div>
          {latest.map((i) => (
            <button
              key={i.id}
              role="menuitem"
              onClick={() => go(`/inbox?tab=${i.type}&open=${i.id}`)}
            >
              <span
                style={{
                  display: "flex",
                  flexDirection: "column",
                  minWidth: 0,
                }}
              >
                <span>
                  {NOTICE[i.type] ?? "New request"} · {i.name}
                </span>
                <small style={{ color: "var(--soft)", fontWeight: 500 }}>
                  {[i.treatment, ago(i.created_at)].filter(Boolean).join(" · ")}
                </small>
              </span>
            </button>
          ))}
          <button
            role="menuitem"
            style={{ color: "var(--brand)" }}
            onClick={() => go("/inbox")}
          >
            View all in Inbox
          </button>
        </div>
      </div>
      {/* Leads belong to the CRM: not shown in the Dashboard (the chatbot console). */}
      {!inConsole && level(crm.me, crm.clinic, "leads") === "edit" && (
        <button
          className="btn"
          onClick={() =>
            crm.openModal({
              title: "Add lead",
              body: clinicId ? (
                <AddLeadForm clinicId={clinicId} onDone={crm.closeModal} />
              ) : (
                <p className="sub2" style={{ margin: 0 }}>
                  Loading your clinics…
                </p>
              ),
            })
          }
        >
          <Icon name="plus" />
          <span className="hide-m">Add lead</span>
        </button>
      )}
      <div ref={menuRef} style={{ position: "relative" }}>
        <button
          className="av"
          id="avb"
          aria-label="Profile menu"
          aria-expanded={menu}
          onClick={() => setMenu(!menu)}
        >
          {crm.me?.initials ?? ""}
        </button>
        <div
          className={`pmenu${menu ? " on" : ""}`}
          style={{ top: 44, right: 0 }}
          role="menu"
        >
          <div className="who">
            <b>{crm.me?.name}</b>
            <span>
              {crm.me?.role_label} · {crm.me?.email}
            </span>
          </div>
          <button role="menuitem" onClick={() => go("/profile")}>
            My profile
          </button>
          <button role="menuitem" onClick={() => go("/settings")}>
            Settings
          </button>
          <button
            role="menuitem"
            style={{ color: "var(--err)" }}
            onClick={() => {
              setMenu(false);
              void crm.signOut();
            }}
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
