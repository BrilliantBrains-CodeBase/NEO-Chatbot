"use client";

// The bell: types, words, and the two ways it gets someone's attention. No patient details ever leave the
// page: a desktop alert only says that something is waiting.

export type BellNote = {
  id: string;
  kind: string;
  severity: "normal" | "urgent";
  created_at: string;
  read: boolean;
  resolved: boolean;
  resolved_by: string | null;
  request_id: string | null;
  tab: string | null;
  lead_code: string | null;
  name: string | null;
  treatment: string | null;
  reason: string | null;
  time_passed: boolean;
  count: number;
  detail: string | null;
};
export type NoteSummary = { unread: number; urgent: number };
export type NoteList = NoteSummary & { items: BellNote[]; total: number };
export type NotePrefs = { off_kinds: string[]; sound: boolean; desktop: boolean };
export type ClinicCounts = Record<string, NoteSummary>;

export const NOTE_KINDS: { id: string; label: string; one: string }[] = [
  { id: "book", label: "Booking requests", one: "Booking request" },
  { id: "online", label: "Online consults", one: "Online consult" },
  { id: "cancel", label: "Cancellations", one: "Cancellation" },
  { id: "reschedule", label: "Reschedules", one: "Reschedule" },
  { id: "callback", label: "Callbacks", one: "Callback" },
  { id: "question", label: "Questions", one: "Question" },
  { id: "callback_late", label: "Call backs left waiting", one: "Call back still waiting" },
  { id: "booking_late", label: "Bookings left waiting", one: "Booking still waiting" },
  { id: "lead_new", label: "New leads", one: "New lead" },
  { id: "lead_assigned", label: "Leads assigned to me", one: "Lead assigned to you" },
  { id: "access_request", label: "Access requests", one: "Access request waiting" },
  { id: "integration_failed", label: "Failed integrations", one: "Integration failed" },
];

export function noteTitle(n: BellNote): string {
  if (n.kind === "lead_new" && n.count > 1) return `${n.count} new leads`;
  if (n.kind === "integration_failed") return `${n.detail ?? "An integration"} is failing`;
  if (n.kind === "access_request") return "Access request waiting";
  const what =
    n.kind === "emergency"
      ? "Emergency"
      : (NOTE_KINDS.find((k) => k.id === n.kind)?.one ?? "New request");
  if (n.name) return `${what} · ${n.name}`;
  return n.kind === "emergency" ? `${what} · no phone number given` : what;
}

/** Where a notification opens. None: an emergency with no phone number has nothing to open. A request or a
 * lead opens the lead's drawer: from the Inbox while it waits for an owner (it shows how to assign it), from
 * Leads once it has one (its owner handles the request there). */
export function noteHref(n: BellNote): string | null {
  const code = n.lead_code ? encodeURIComponent(n.lead_code) : null;
  if (n.kind === "access_request") return "/team";
  if (n.kind === "integration_failed") return "/assistant/integrations";
  if (n.kind === "lead_new") return code ? `/inbox?open=${code}` : "/inbox";
  if (n.request_id || n.kind === "lead_assigned") return code ? `/leads?open=${code}` : "/leads";
  return null;
}

export const needsAction = (n: BellNote) =>
  n.severity === "urgent" && !n.resolved;

export function ago(iso: string): string {
  const min = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 1) return "Just now";
  if (min < 60) return `${min} min ago`;
  if (min < 1440) return `${Math.floor(min / 60)} h ago`;
  return `${Math.floor(min / 1440)} d ago`;
}

/** Emergencies waiting first, then Today, Yesterday and Earlier by this computer's clock. */
export function groupNotes(items: BellNote[]): [string, BellNote[]][] {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const today = startOfToday.getTime();
  const groups: [string, BellNote[]][] = [
    ["Needs action", []],
    ["Today", []],
    ["Yesterday", []],
    ["Earlier", []],
  ];
  for (const n of items) {
    const at = new Date(n.created_at).getTime();
    const slot = needsAction(n)
      ? 0
      : at >= today
        ? 1
        : at >= today - 86_400_000
          ? 2
          : 3;
    groups[slot][1].push(n);
  }
  return groups.filter(([, rows]) => rows.length > 0);
}

/** A short tone made in the browser (no sound file). It may be refused until the page has been clicked. */
export function playTone(urgent: boolean) {
  try {
    const ctx = new AudioContext();
    const tone = ctx.createOscillator();
    const gain = ctx.createGain();
    tone.frequency.value = urgent ? 880 : 660;
    gain.gain.setValueAtTime(0.12, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(
      0.001,
      ctx.currentTime + (urgent ? 0.8 : 0.3),
    );
    tone.connect(gain).connect(ctx.destination);
    tone.start();
    tone.stop(ctx.currentTime + (urgent ? 0.8 : 0.3));
    tone.onended = () => void ctx.close();
  } catch {
    // no audio here: the badge and the message still show
  }
}

export function desktopAlert(urgent: boolean) {
  try {
    if (!("Notification" in window) || window.Notification.permission !== "granted")
      return;
    const alert = new window.Notification("NEO CRM", {
      body: urgent ? "Emergency waiting in the CRM" : "New notification in the CRM",
      tag: urgent ? "neo-emergency" : "neo-new",
    });
    alert.onclick = () => {
      window.focus();
      alert.close();
    };
  } catch {
    // some browsers allow these only from a service worker: the badge and tab title still show
  }
}
