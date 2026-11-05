"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
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

type MenuName = "clinic" | "bell" | "profile";

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
  const [open, setOpen] = useState<MenuName | null>(null);
  const clinicRef = useRef<HTMLDivElement>(null);
  const bellRef = useRef<HTMLDivElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);
  const openedByKeyboard = useRef(false);

  const toggleMenu = (name: MenuName, e: ReactMouseEvent) => {
    openedByKeyboard.current = e.detail === 0; // Enter or Space, not a mouse click
    setOpen(open === name ? null : name);
  };

  // The menus close on any click outside them and on Esc (which returns to the button that opened them).
  useEffect(() => {
    if (!open) return;
    const box = { clinic: clinicRef, bell: bellRef, profile: profileRef }[open]
      .current;
    if (openedByKeyboard.current)
      box?.querySelector<HTMLElement>(".pmenu button")?.focus();
    const onClick = (e: MouseEvent) => {
      if (!box?.contains(e.target as Node)) setOpen(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(null);
      box?.querySelector<HTMLElement>(":scope > button")?.focus();
    };
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // The up and down arrows move through the open menu.
  const onMenuArrows = (e: ReactKeyboardEvent<HTMLElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const items = [
      ...e.currentTarget.querySelectorAll<HTMLElement>(".pmenu.on button"),
    ];
    if (items.length === 0) return;
    e.preventDefault();
    const at = items.indexOf(document.activeElement as HTMLElement);
    const step = e.key === "ArrowDown" ? 1 : -1;
    items[at < 0 ? 0 : (at + step + items.length) % items.length].focus();
  };

  const go = (href: string) => {
    setOpen(null);
    router.push(href);
  };
  // Newest first, the latest 8.
  const latest = crm.inboxItems
    .filter((i) => !bellOff.includes(i.type))
    .slice(0, 8);

  // Until the person's clinics have loaded, no name shows (not a clinic that may not be theirs).
  const clinicName = crm.clinics.length > 0 ? crm.clinic : "";

  return (
    <header
      className={`tb${compact ? " tb-compact" : ""}`}
      onKeyDown={onMenuArrows}
    >
      <button className="ham" aria-label="Open menu" onClick={onMenu}>
        <Icon name="menu" />
      </button>

      {crm.clinics.length > 1 ? (
        <div ref={clinicRef} className="tb-menu">
          <button
            className="tb-clinic"
            aria-label={`Clinic: ${clinicName}`}
            aria-haspopup="menu"
            aria-expanded={open === "clinic"}
            onClick={(e) => toggleMenu("clinic", e)}
          >
            <span className="tb-clinic-ic">
              <Icon name="clinic" />
            </span>
            <span className="tb-clinic-n">{clinicName}</span>
            <Icon name="chev" className="chev" />
          </button>
          <div
            className={`pmenu tb-left${open === "clinic" ? " on" : ""}`}
            role="menu"
            aria-label="Clinic"
          >
            {crm.clinics.map((c) => (
              <button
                key={c}
                role="menuitemradio"
                aria-checked={c === crm.clinic}
                onClick={() => {
                  crm.setClinic(c as Clinic);
                  setOpen(null);
                }}
              >
                <span className="tb-clinic-n">{c}</span>
                {c === crm.clinic && <Icon name="check" className="tb-tick" />}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="tb-clinic tb-clinic-one">
          <span className="tb-clinic-ic">
            <Icon name="clinic" />
          </span>
          <span className="tb-clinic-n">{clinicName}</span>
        </div>
      )}

      {level(crm.me, crm.clinic, "dash_open") !== "hidden" && (
        <div
          className={`seg tb-seg${inConsole ? " right" : ""}`}
          role="tablist"
          aria-label="Workspace"
        >
          <span className="tb-thumb" aria-hidden="true" />
          <button
            role="tab"
            aria-selected={!inConsole}
            aria-label="CRM"
            className={inConsole ? "" : "on"}
            onClick={() => router.push("/dashboard")}
          >
            <Icon name="team" />
            <span>CRM</span>
          </button>
          <button
            role="tab"
            aria-selected={inConsole}
            aria-label="Dashboard"
            className={inConsole ? "on" : ""}
            onClick={() => router.push("/assistant/appearance")}
          >
            <Icon name="dash" />
            <span>Dashboard</span>
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

      <div ref={bellRef} className="tb-menu">
        <button
          className="ib tb-bell"
          aria-label={pending ? `Notifications, ${pending} waiting` : "Notifications"}
          aria-haspopup="menu"
          aria-expanded={open === "bell"}
          onClick={(e) => toggleMenu("bell", e)}
        >
          <Icon name="bell" />
          {/* Remounting on a new count replays the badge's pop. */}
          {!!pending && <b key={pending}>{pending}</b>}
        </button>
        <div
          className={`pmenu tb-notes${open === "bell" ? " on" : ""}`}
          role="menu"
          aria-label="Notifications"
        >
          <div className="who">
            <b>Notifications</b>
            <span>
              {pending ? `${pending} waiting in the Inbox` : "Nothing waiting"}
            </span>
          </div>
          <div className="tb-notes-list">
            {latest.map((i) => (
              <button
                key={i.id}
                role="menuitem"
                onClick={() => go(`/inbox?tab=${i.type}&open=${i.id}`)}
              >
                <span className="tb-dot" aria-hidden="true" />
                <span className="tb-note">
                  <span>
                    {NOTICE[i.type] ?? "New request"} · {i.name}
                  </span>
                  <small>
                    {[i.treatment, ago(i.created_at)].filter(Boolean).join(" · ")}
                  </small>
                </span>
              </button>
            ))}
          </div>
          <button
            role="menuitem"
            className="tb-all"
            onClick={() => go("/inbox")}
          >
            View all in Inbox
          </button>
        </div>
      </div>

      {/* Leads belong to the CRM: not shown in the Dashboard (the chatbot console). */}
      {!inConsole && level(crm.me, crm.clinic, "leads") === "edit" && (
        <button
          className="btn tb-add"
          aria-label="Add lead"
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

      <div ref={profileRef} className="tb-menu">
        <button
          className="av tb-av"
          id="avb"
          aria-label="Profile menu"
          aria-haspopup="menu"
          aria-expanded={open === "profile"}
          onClick={(e) => toggleMenu("profile", e)}
        >
          {crm.me?.initials ?? ""}
        </button>
        <div
          className={`pmenu${open === "profile" ? " on" : ""}`}
          role="menu"
          aria-label="Profile"
        >
          <div className="who">
            <b>{crm.me?.name}</b>
            <span>
              {crm.me?.role_label} · {crm.me?.email}
            </span>
          </div>
          <button role="menuitem" onClick={() => go("/profile")}>
            <Icon name="user" />
            My profile
          </button>
          <button role="menuitem" onClick={() => go("/settings")}>
            <Icon name="set" />
            Settings
          </button>
          <button
            role="menuitem"
            className="tb-out"
            onClick={() => {
              setOpen(null);
              void crm.signOut();
            }}
          >
            <Icon name="logout" />
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
