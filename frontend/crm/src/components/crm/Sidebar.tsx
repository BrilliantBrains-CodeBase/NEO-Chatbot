"use client";

import DataImg from "@/components/crm/DataImg";
import { canSee } from "@/lib/access";
import { inDashboard } from "@/lib/workspace";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type FocusEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import { ON_SECTIONS } from "@/lib/assistant";
import { useDoctors } from "@/lib/availability";
import { isMenuRail, subscribeMenu, toggleMenuMini } from "@/lib/menu-state";
import { useCrm } from "./CrmProvider";
import Icon, { type IconName } from "./Icon";

type Group = "leads" | "doctors";

// Stage links open that tab of the Leads screen (live counts are on its tabs).
const LEAD_STAGES = [
  ["new", "New"],
  ["follow_up", "Follow Up"],
  ["booked", "Booked"],
  ["visited", "Visited"],
  ["lost", "Lost"],
  ["invalid", "Invalid"],
] as const;

const GROUP_PAGE: Record<Group, string> = {
  leads: "/leads",
  doctors: "/doctors",
};
const groupOf = (path: string) =>
  (Object.keys(GROUP_PAGE) as Group[]).find((g) => GROUP_PAGE[g] === path) ??
  null;

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
  const rail = useSyncExternalStore(subscribeMenu, isMenuRail, () => false);

  // Leads starts open, as in the design; the group of the page you land on opens too.
  const activeGroup = groupOf(path);
  const [expanded, setExpanded] = useState<Record<Group, boolean>>({
    leads: true,
    doctors: activeGroup === "doctors",
  });
  const [seenGroup, setSeenGroup] = useState(activeGroup);
  if (seenGroup !== activeGroup) {
    setSeenGroup(activeGroup);
    if (activeGroup) setExpanded((e) => ({ ...e, [activeGroup]: true }));
  }

  // The icon strip's dark labels and floating sub-menu. They are fixed to the screen, because the
  // scrolling menu would otherwise cut them off at its edge.
  const [tip, setTip] = useState<{
    label: string;
    top: number;
    left: number;
  } | null>(null);
  const [fly, setFly] = useState<{
    group: Group;
    top: number;
    left: number;
    maxHeight: number;
  } | null>(null);
  const flyRef = useRef<HTMLDivElement>(null);
  const flyOpener = useRef<HTMLElement | null>(null);
  const flyByKeyboard = useRef(false);
  const flyGroup = rail ? (fly?.group ?? null) : null;

  const showTip = (
    e: MouseEvent<HTMLElement> | FocusEvent<HTMLElement>,
    label: string,
  ) => {
    if (!rail) return;
    const r = e.currentTarget.getBoundingClientRect();
    setTip({ label, top: r.top + r.height / 2, left: r.right + 12 });
  };
  const hideTip = () => setTip(null);
  const tipProps = (label: string) => ({
    onMouseEnter: (e: MouseEvent<HTMLElement>) => showTip(e, label),
    onMouseLeave: hideTip,
    onFocus: (e: FocusEvent<HTMLElement>) => showTip(e, label),
    onBlur: hideTip,
  });
  const navigated = () => {
    hideTip();
    setFly(null);
    onNavigate();
  };

  const toggleGroup = (g: Group, e: MouseEvent<HTMLElement>) => {
    hideTip();
    if (!rail) {
      setExpanded((x) => ({ ...x, [g]: !x[g] }));
      return;
    }
    if (flyGroup === g) {
      setFly(null);
      return;
    }
    const r = e.currentTarget.getBoundingClientRect();
    const top = Math.max(12, Math.min(r.top, window.innerHeight - 340));
    flyOpener.current = e.currentTarget;
    flyByKeyboard.current = e.detail === 0; // Enter or Space, not a mouse click
    setFly({
      group: g,
      top,
      left: r.right + 16,
      maxHeight: window.innerHeight - top - 12,
    });
  };

  // The floating sub-menu closes on a click outside it, on Esc, and when the window is resized.
  useEffect(() => {
    if (!flyGroup) return;
    if (flyByKeyboard.current) flyRef.current?.querySelector("a")?.focus();
    const onClick = (e: globalThis.MouseEvent) => {
      const target = e.target as Element;
      if (!flyRef.current?.contains(target) && !target.closest("[data-fly]"))
        setFly(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setFly(null);
      flyOpener.current?.focus();
    };
    const close = () => setFly(null);
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", close);
    };
  }, [flyGroup]);

  const stage = params.get("stage") ?? "";
  // New leads waiting for an owner (one link: the Inbox has its own type filters).
  const inboxTotal = crm.inbox?.all ?? 0;
  const doc = params.get("doc") ?? "";
  // The clinic's real doctors (Dashboard → Doctors), each opening their week.
  const doctors = useDoctors(
    crm.me?.clinics.find((c) => c.name === crm.clinic)?.id,
  );

  // The navy marker sits behind the active row and slides to the next one when the page changes.
  const navRef = useRef<HTMLElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const markerRef = useRef<HTMLSpanElement>(null);
  const placeMarker = useCallback((slide: boolean) => {
    const nav = navRef.current;
    const marker = markerRef.current;
    if (!nav || !marker) return;
    const row = nav.querySelector<HTMLElement>(".ni.on");
    nav.dataset.marker = row ? "1" : "";
    if (!row) {
      marker.style.opacity = "0";
      return;
    }
    const placed = marker.style.opacity === "1";
    marker.style.transition = slide && placed ? "" : "none";
    marker.style.transform = `translate(${row.offsetLeft}px,${row.offsetTop}px)`;
    marker.style.width = `${row.offsetWidth}px`;
    marker.style.height = `${row.offsetHeight}px`;
    marker.style.opacity = "1";
  }, []);
  useLayoutEffect(() => placeMarker(true), [placeMarker, path, stage, doc]);
  // Sub-menus opening above it, or the menu collapsing, move the row: the marker follows exactly.
  useEffect(() => {
    if (!innerRef.current) return;
    const watcher = new ResizeObserver(() => placeMarker(false));
    watcher.observe(innerRef.current);
    return () => watcher.disconnect();
  }, [placeMarker]);

  const see = (href: string) => canSee(crm.me, crm.clinic, href);
  const logo = crm.branding?.logo ?? null;
  const mark = crm.branding?.favicon ?? null;

  const item = (
    href: string,
    icon: IconName,
    label: string,
    on: boolean,
    count?: number,
  ) =>
    !see(href) ? null : (
      <Link
        key={href}
        href={href}
        className={`ni${on ? " on" : ""}`}
        aria-current={on ? "page" : undefined}
        onClick={navigated}
        {...tipProps(label)}
      >
        <span className="ni-ic">
          <Icon name={icon} />
        </span>
        <span className="ni-l">{label}</span>
        {count != null && <span className="c">{count}</span>}
      </Link>
    );
  const subItem = (href: string, label: string, on: boolean, count?: number) => (
    <Link
      key={href}
      href={href}
      className={`si${on ? " on" : ""}`}
      aria-current={on ? "page" : undefined}
      onClick={navigated}
    >
      <span className="si-l">{label}</span>
      {count != null && <span className="c">{count}</span>}
    </Link>
  );

  const subs: Record<Group, ReactNode> = {
    leads: LEAD_STAGES.map(([key, label]) =>
      subItem(`/leads?stage=${key}`, label, path === "/leads" && stage === key),
    ),
    doctors: (
      <>
        {subItem("/doctors", "All doctors", path === "/doctors" && !doc)}
        {doctors.map((d) =>
          subItem(
            `/doctors?doc=${d.id}`,
            d.name,
            path === "/doctors" && doc === d.id,
          ),
        )}
      </>
    ),
  };
  const groupLabel: Record<Group, string> = {
    leads: "Leads",
    doctors: "Doctors Availability",
  };

  const group = (g: Group, icon: IconName, count?: number) => {
    // Someone without this screen sees neither the group nor its links.
    if (!see(GROUP_PAGE[g])) return null;
    const label = groupLabel[g];
    const opened = rail ? flyGroup === g : expanded[g];
    return (
      <div key={g}>
        <button
          type="button"
          data-fly
          className={`ni${activeGroup === g ? " on" : ""}${opened ? " open" : ""}`}
          aria-expanded={opened}
          onClick={(e) => toggleGroup(g, e)}
          {...tipProps(label)}
        >
          <span className="ni-ic">
            <Icon name={icon} />
          </span>
          <span className="ni-l">{label}</span>
          {count != null && <span className="c">{count}</span>}
          <Icon name="chev" className="chev" />
        </button>
        <div className={`sub${expanded[g] ? " open" : ""}`}>
          <div>
            <div className="sub-in">{subs[g]}</div>
          </div>
        </div>
      </div>
    );
  };

  const consoleGroups = [...new Set(ON_SECTIONS.map((s) => s.group))];
  const console_ = inDashboard(path);
  const showAdmin = see("/team") || (!console_ && see("/settings"));

  return (
    <aside className={`sb${open ? " on" : ""}`} aria-label="Main menu">
      {/* The chosen clinic's logo (Clinic settings); the narrow menu shows its favicon. Without them: NEO CRM. */}
      <div className={`sb-top${logo ? " has-logo" : ""}`}>
        {mark ? <DataImg className="sb-mark" src={mark} alt="" /> : <i>{logo ? crm.clinic.charAt(0) : "N"}</i>}
        {logo ? (
          <DataImg className="sb-logo" src={logo} alt={crm.clinic} />
        ) : (
          <span className="sb-name">NEO CRM</span>
        )}
      </div>
      <button
        type="button"
        className="sb-tg"
        aria-label={rail ? "Expand menu" : "Collapse menu"}
        aria-expanded={!rail}
        title={rail ? "Expand menu" : "Collapse menu"}
        onClick={() => {
          hideTip();
          setFly(null);
          toggleMenuMini();
        }}
      >
        <Icon name="chev" />
      </button>

      <nav
        className="nav"
        ref={navRef}
        onScroll={() => {
          hideTip();
          setFly(null);
        }}
      >
        <div className="nav-in" ref={innerRef}>
          <span className="sb-ind" ref={markerRef} aria-hidden="true" />
          {console_ ? (
            /* The Assistant console's menu (design: Patient Assistant Console), grouped as in the design. */
            consoleGroups.map((g) => {
              const rows = ON_SECTIONS.filter(
                (s) =>
                  s.group === g &&
                  (!s.bbOnly || crm.me?.bb_admin) &&
                  see(`/assistant/${s.id}`),
              );
              if (rows.length === 0) return null;
              return (
                <div key={g || "top"}>
                  {g && <div className="grp">{g.toUpperCase()}</div>}
                  {rows.map((s) =>
                    item(
                      `/assistant/${s.id}`,
                      s.icon,
                      s.label,
                      path === `/assistant/${s.id}`,
                    ),
                  )}
                </div>
              );
            })
          ) : (
            <>
              <div className="grp">MAIN</div>
              {item("/dashboard", "dash", "Dashboard", path === "/dashboard")}
              {group("leads", "appt")}
              {item("/inbox", "req", "Inbox", path === "/inbox", inboxTotal || undefined)}
              {group("doctors", "doc")}
              <div className="dv" />
              {item(
                "/appointments",
                "cal",
                "Appointments",
                path === "/appointments",
              )}
              {/* Tasks and Reports are turned off for everyone. */}
              {item("/patients", "con", "Patients", path === "/patients")}
            </>
          )}
          {/* The same place on both sides of the switch. */}
          {showAdmin && (
            <>
              <div className="dv" />
              <div className="grp">ADMIN</div>
              {item("/team", "team", "Team", path === "/team")}
              {!console_ && item("/settings", "set", "Clinic settings", path === "/settings")}
            </>
          )}
        </div>
      </nav>

      <div className="sb-foot">
        <button
          type="button"
          className="ni sb-out"
          {...tipProps("Sign out")}
          onClick={() => {
            hideTip();
            void crm.signOut();
          }}
        >
          <span className="ni-ic">
            <Icon name="logout" />
          </span>
          <span className="ni-l">Sign out</span>
        </button>
      </div>

      {flyGroup && fly && (
        <div
          className="sb-fly"
          ref={flyRef}
          role="group"
          aria-label={groupLabel[flyGroup]}
          style={{ top: fly.top, left: fly.left, maxHeight: fly.maxHeight }}
        >
          <div className="sb-fly-h">{groupLabel[flyGroup]}</div>
          {subs[flyGroup]}
        </div>
      )}
      {rail && tip && (
        <div
          className="sb-tip"
          role="tooltip"
          style={{ top: tip.top, left: tip.left }}
        >
          {tip.label}
        </div>
      )}
    </aside>
  );
}
