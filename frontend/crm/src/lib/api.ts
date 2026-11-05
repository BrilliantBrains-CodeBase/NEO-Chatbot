"use client";

import { supabase } from "./supabase";

// The CRM's only way to read or change data: our backend's JSON API (/v1/crm/...), with the signed-in
// person's token. The backend checks the token and the person's role for that clinic on every call.
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

/** How often lists and the bell read again by themselves (paused while the tab is hidden). */
export const REFRESH_MS = 30_000;

/** The backend's answer when 2-step login needs this sign-in's emailed code (app/crm/auth.py CODE_NEEDED). */
export const CODE_NEEDED = "Enter the sign-in code sent to your email.";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  retried = false,
): Promise<T> {
  const { data } = await supabase().auth.getSession();
  const token = data.session?.access_token;
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
    });
  } catch {
    throw new ApiError(
      0,
      "The CRM server cannot be reached. Check your connection and try again.",
    );
  }
  // A stored sign-in token can be out of date (e.g. the laptop slept): renew it once and try again.
  if (res.status === 401 && token && !retried) {
    const { data: fresh } = await supabase().auth.refreshSession();
    if (fresh.session) return api<T>(path, init, true);
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    // A check the backend's models make (e.g. "hours overlap") comes as a list: show its first message.
    const first = Array.isArray(detail)
      ? (detail[0] as { msg?: unknown } | undefined)?.msg
      : undefined;
    const message =
      typeof detail === "string"
        ? detail
        : typeof first === "string"
          ? first.replace(/^Value error, /, "")
          : "Something went wrong. Please try again.";
    throw new ApiError(res.status, message);
  }
  return body as T;
}

/** A file from the API (e.g. a CSV export), with the signed-in person's token. */
export async function apiBlob(
  path: string,
  init: RequestInit = {},
  retried = false,
): Promise<Blob> {
  const { data } = await supabase().auth.getSession();
  const token = data.session?.access_token;
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      ...init,
      headers: {
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
  } catch {
    throw new ApiError(
      0,
      "The CRM server cannot be reached. Check your connection and try again.",
    );
  }
  if (res.status === 401 && token && !retried) {
    const { data: fresh } = await supabase().auth.refreshSession();
    if (fresh.session) return apiBlob(path, init, true);
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as {
      detail?: unknown;
    } | null;
    throw new ApiError(
      res.status,
      typeof body?.detail === "string"
        ? body.detail
        : "Something went wrong. Please try again.",
    );
  }
  return res.blob();
}

/** Saves a file made in the browser to the person's downloads. */
export function saveFile(blob: Blob, name: string): void {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/** GET /v1/crm/me: who is signed in and which clinics they see. */
export type Me = {
  id: string;
  name: string;
  email: string;
  initials: string;
  bb_admin: boolean;
  role_label: string;
  // access: Who sees what, screen -> hidden / view / edit
  clinics: {
    id: string;
    name: string;
    role: string;
    role_label: string;
    access?: Record<string, string>;
  }[];
};

export type Count = { key: string; count: number };
export type Dashboard = {
  clinic: string;
  days: number;
  new_leads: number;
  inbox_pending: number;
  callbacks_waiting: number;
  followups_due: number;
  today: {
    time: string | null;
    patient: string;
    lead_code: string;
    doctor: string | null;
    type: string;
    status: string;
    treatment: string | null;
  }[];
  sources: Count[];
  funnel: Count[];
  treatments: Count[];
  chats: number;
  chat_leads: number;
  chat_answered_by: Count[];
  unanswered: number;
};

export type LeadRow = {
  code: string;
  name: string;
  phone: string | null;
  email: string | null;
  source: string;
  campaign: string | null;
  treatment: string | null;
  doctor: string | null;
  type: string | null;
  stage: string;
  assigned: string | null;
  assigned_id: string | null;
  contacts: number;
  last_contact_at: string;
  created_at: string;
};
export type LeadList = {
  total: number;
  stages: Count[];
  items: LeadRow[];
  treatments?: string[];
};
export type PatientRow = {
  code: string;
  name: string;
  phone: string | null;
  email: string | null;
  source: string;
  campaign: string | null;
  treatment: string | null;
  doctor: string | null;
  stage: string;
  assigned: string | null;
  activity: string;
  visits: number;
  no_shows: number;
  contacts: number;
  consent: boolean;
  first_visit: string | null;
  last_visit: string | null;
  next_visit: string | null;
  last_contact_at: string;
  created_at: string;
};
export type PatientList = {
  total: number;
  activities: Count[];
  items: PatientRow[];
  treatments: string[];
  campaigns: string[];
  doctors: { id: string; name: string }[];
  staff: { id: string; name: string }[];
};
export type LeadImportNote = { row: number; name: string; reason: string };
export type LeadImportResult = {
  ready: number;
  added: number;
  duplicates: LeadImportNote[];
  invalid: LeadImportNote[];
};
export type LeadDetail = LeadRow & {
  stage_reason: string | null;
  notes: string;
  page_url: string | null;
  device: string | null;
  verified: boolean;
  events: {
    kind: string;
    data: Record<string, unknown>;
    by: string | null;
    at: string;
  }[];
  chat: { role: string; text: string; at: string }[];
};

export type StaffOption = { id: string; name: string; role_label: string };
export type LeadOptions = {
  treatments: string[];
  doctors: { id: string; name: string }[];
};

export type InboxItem = {
  id: string;
  type: string;
  status: string;
  created_at: string;
  lead_code: string;
  name: string;
  phone: string | null;
  email: string | null;
  treatment: string | null;
  reason: string | null;
  date: string | null;
  time: string | null;
  booked_date: string | null;
  match_status: string | null;
  appointment: {
    id: string;
    start: string | null;
    day: string | null;
    doctor: string | null;
    doctor_id: string | null;
    type: string;
    status: string;
    meet_link: string | null;
  } | null;
};
export type Inbox = {
  pending: Count[];
  items: InboxItem[];
  total?: number;
  treatments?: string[];
};

/** Inbox tabs, in the menu's order. */
export const INBOX_TABS: [string, string][] = [
  ["book", "Booking requests"],
  ["online", "Online consults"],
  ["cancel", "Cancellations"],
  ["reschedule", "Reschedules"],
  ["callback", "Callbacks"],
  ["question", "Questions"],
];

export type Appointment = {
  id: string;
  start: string | null;
  day: string;
  time: string | null;
  doctor: string | null;
  doctor_id: string | null;
  type: string;
  status: string;
  meet_link: string | null;
  lead_code: string;
  name: string;
  phone: string | null;
  email: string | null;
  treatment: string | null;
  stage: string;
};
export type Appointments = {
  doctors: { id: string; name: string }[];
  items: Appointment[];
};
