"use client";

import { supabase } from "./supabase";

// The CRM's only way to read or change data: our backend's JSON API (/v1/crm/...), with the signed-in
// person's token. The backend checks the token and the person's role for that clinic on every call.
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

/** How often lists and the bell read again by themselves (paused while the tab is hidden). */
export const REFRESH_MS = 30_000;
// The main clinic (Neo Follicle Hair Transplant): the main template, and the CRM's first clinic by default.
export const MAIN_CLINIC = "NFHT";

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
  /** +919876543210, or null when not given. */
  phone: string | null;
  /** A small uploaded data:image (My profile), or null: the initials show. */
  photo: string | null;
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

/** The CRM's look for one clinic (Clinic settings): shown while that clinic is chosen. */
export type Branding = {
  logo: string | null;
  favicon: string | null;
  updated_at: string | null;
};

export type Count = { key: string; count: number };
/** One period's headline numbers on the Dashboard. */
export type Totals = { leads: number; converted: number; bookings: number; visits: number; chats: number; chat_leads: number };

export type TodayAppt = {
  time: string | null;
  end: string | null;
  patient: string;
  lead_code: string;
  doctor: string | null;
  doctor_id: string | null;
  type: string;
  status: string;
  treatment: string | null;
};

export type Dashboard = {
  clinic: string;
  days: number;
  start: string; // the period's first day, 2026-10-31
  new_leads: number;
  inbox_pending: number;
  callbacks_waiting: number;
  followups_due: number; // leads in the Follow Up stage
  now: Totals;
  before: Totals; // the same number of days just before
  series: { day: string; leads: number; leads_before: number; bookings: number; visits: number; chats: number }[];
  outcomes: Count[]; // appointments on days in the period, by status
  today: TodayAppt[];
  sources: Count[];
  funnel: Count[];
  treatments: Count[];
  chats: number;
  chat_leads: number;
  chat_answered_by: Count[];
  unanswered: number;
};

/** Appointments per day in one month, for the Dashboard calendar. */
export type DashMonth = { month: string; today: string; days: Count[] };

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
  pending: number; // requests waiting for the owner ("Needs action")
  doctor_id?: string | null; // the preferred doctor (Edit details)
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
  extra?: Record<string, string>; // More information (Lead & Booking API)
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
  urgent?: boolean; // an emergency in the chat
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
/** A request waiting on an Inbox lead, as a summary (its owner handles it after assigning). */
export type InboxRequest = {
  id: string;
  type: string;
  created_at: string;
  treatment: string | null;
  reason: string | null;
  date: string | null;
  time: string | null;
  booked_date: string | null;
  urgent: boolean;
};
/** The Inbox: new leads waiting for an owner. */
export type InboxLead = LeadRow & { requests: InboxRequest[] };
export type Inbox = {
  total: number;
  all: number; // the same without the type filter
  types: Count[]; // leads per waiting request type, and "none"
  items: InboxLead[];
  treatments?: string[];
};
export type Assigned = { assigned: string[]; taken: string[]; to: string };

/** Request types, in order: the Inbox's and Leads' filters and badges. */
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
