"use client";

import { useEffect, useState } from "react";

// Words and helpers shared by Leads, the Inbox and Patients.
export const STAGE_LABEL: Record<string, [string, string]> = {
  new: ["New", "b-new"],
  follow_up: ["Follow Up", "b-fu"],
  booked: ["Booked", "b-bk"],
  visited: ["Visited", "b-vi"],
  lost: ["Lost", "b-lo"],
  invalid: ["Invalid", "b-in"],
};
export const SOURCE: Record<string, string> = {
  chatbot: "Chatbot",
  meta_ads: "Meta Ads",
  google_ads: "Google Ads",
  manual: "Manual",
  whatsapp: "WhatsApp",
  website_form: "Website form",
};
export const EVENT: Record<string, string> = {
  contact: "Contacted",
  stage_change: "Stage changed",
  assigned: "Assigned",
  call: "Call",
  note: "Note",
  request: "Request",
  appointment: "Appointment",
};

export const when = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

export function useDebounced(value: string, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
