"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError } from "@/lib/api";
import Icon from "@/components/crm/Icon";

// What the Team page's tabs share: the data it reads, the role names, the row menu and the confirm pop-up.

export type Member = {
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
  doctor_id: string | null;
};
export type AccessRequest = {
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
export type DoctorRecord = {
  id: string;
  name: string;
  linked_to: string | null;
};
export type Team = {
  members: Member[];
  requests: AccessRequest[];
  can_manage: boolean;
  managed: Record<string, string>; // the clinics you give access to: id -> name
  doctors: DoctorRecord[];
  can_add_admins: boolean;
};

export const ROLES: Record<
  string,
  { label: string; badge: string; about: string }
> = {
  bb_admin: {
    label: "Super Admin",
    badge: "b-bk",
    about:
      "Every clinic. Adds and manages clinics, sets the defaults for all of them.",
  },
  clinic_manager: {
    label: "Admin",
    badge: "b-new",
    about:
      "One clinic's leads, patients, team and chatbot. Cannot add clinics.",
  },
  front_desk: {
    label: "Front Desk",
    badge: "b-on",
    about:
      "Telecallers and reception, in the clinics you tick: leads, inbox, appointments, patients.",
  },
  doctor: {
    label: "Doctor",
    badge: "b-cl",
    about:
      "Their own appointments and patients, and their own hours and leave.",
  },
};
export const roleLabel = (role: string) => ROLES[role]?.label ?? role;

/** The roles this person may give. */
export function givableRoles(team: Team, superAdmin: boolean): string[] {
  return [
    "front_desk",
    "doctor",
    ...(superAdmin ? ["clinic_manager"] : []),
    ...(team.can_add_admins ? ["bb_admin"] : []),
  ];
}

export const message = (e: unknown, fallback: string) =>
  e instanceof ApiError ? e.message : fallback;

export const dateTime = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString("en-IN", {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Never";

export function lastSeen(iso: string | null) {
  if (!iso) return "Never";
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 2) return "Just now";
  if (min < 60) return `${min} min ago`;
  if (min < 1440) return `${Math.round(min / 60)} h ago`;
  if (min < 2880) return "Yesterday";
  if (min < 43200) return `${Math.round(min / 1440)} days ago`;
  return new Date(iso).toLocaleDateString("en-IN", { dateStyle: "medium" });
}

export const initials = (name: string) =>
  name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

export function Person({
  name,
  sub,
  you,
}: {
  name: string;
  sub: string;
  you?: boolean;
}) {
  return (
    <div className="tm-person">
      <span className="av" aria-hidden="true">
        {initials(name)}
      </span>
      <div>
        <div className="nm">
          {name}
          {you && <span className="sub2"> (you)</span>}
        </div>
        <div className="tm-sub">{sub}</div>
      </div>
    </div>
  );
}

export type MenuItem = {
  label: string;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
};

/** The ⋯ on a table row. Drawn over the page, so a table's scrolling never cuts it off. */
export function RowMenu({
  label,
  items,
}: {
  label: string;
  items: MenuItem[];
}) {
  const [at, setAt] = useState<{ top: number; right: number } | null>(null);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!at) return;
    const close = () => setAt(null);
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setAt(null);
        button.current?.focus();
      }
    };
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("keydown", key);
    };
  }, [at]);

  return (
    <>
      <button
        ref={button}
        type="button"
        className="tm-dots"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={!!at}
        onClick={(e) => {
          e.stopPropagation();
          if (at) return setAt(null);
          const r = e.currentTarget.getBoundingClientRect();
          setAt({ top: r.bottom + 4, right: window.innerWidth - r.right });
        }}
      >
        <Icon name="more" />
      </button>
      {at && (
        <div
          className="tm-menu"
          role="menu"
          style={{ top: at.top, right: at.right }}
        >
          {items.map((i) => (
            <button
              key={i.label}
              type="button"
              role="menuitem"
              disabled={i.disabled}
              className={i.danger ? "danger" : ""}
              onClick={i.onClick}
            >
              {i.label}
            </button>
          ))}
        </div>
      )}
    </>
  );
}

/** A pop-up's question: its action runs here, and a refusal stays on screen. `typed`: a word to type first. */
export function Confirm({
  text,
  action,
  danger,
  typed,
  onConfirm,
  onClose,
}: {
  text: ReactNode;
  action: string;
  danger?: boolean;
  typed?: string;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [word, setWord] = useState("");
  return (
    <div>
      <p style={{ margin: "0 0 12px" }}>{text}</p>
      {typed && (
        <label className="tm-field" style={{ marginBottom: 12 }}>
          Type {typed} to confirm
          <input
            className="f"
            value={word}
            onChange={(e) => setWord(e.target.value)}
          />
        </label>
      )}
      {error && (
        <div className="warnbox" role="alert" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}
      <div className="tm-actions">
        <button type="button" className="btn g" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className={`btn${danger ? " red" : ""}`}
          disabled={busy || (!!typed && word.trim().toUpperCase() !== typed)}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await onConfirm();
              onClose();
            } catch (e) {
              setError(message(e, "Could not save. Please try again."));
              setBusy(false);
            }
          }}
        >
          {busy ? "Working…" : action}
        </button>
      </div>
    </div>
  );
}
