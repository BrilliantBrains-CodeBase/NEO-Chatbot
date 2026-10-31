"use client";

import { useSyncExternalStore } from "react";

// Settings → Bell notifications: which request types show in the top bar's bell. Saved in this browser
// (user's choice); the Inbox still shows everything.

export const BELL_TYPES: { id: string; label: string }[] = [
  { id: "book", label: "Booking requests" },
  { id: "online", label: "Online consults" },
  { id: "cancel", label: "Cancellations" },
  { id: "reschedule", label: "Reschedules" },
  { id: "callback", label: "Callbacks" },
  { id: "question", label: "Questions" },
];

const KEY = "neo-crm-bell-off";
const EVENT = "neo-crm-bell";

/** The types turned off, as saved text ("" = all on); text keeps the snapshot stable for React. */
function read(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

function subscribe(change: () => void) {
  window.addEventListener(EVENT, change);
  window.addEventListener("storage", change); // another tab changed it
  return () => {
    window.removeEventListener(EVENT, change);
    window.removeEventListener("storage", change);
  };
}

/** The request types turned off in the bell. */
export function useBellOff(): string[] {
  const saved = useSyncExternalStore(subscribe, read, () => "");
  return saved ? saved.split(",") : [];
}

export function setBellOff(off: string[]) {
  try {
    localStorage.setItem(KEY, off.join(","));
  } catch {
    // private mode or storage full: the choice lasts until the page reloads
  }
  window.dispatchEvent(new Event(EVENT));
}
