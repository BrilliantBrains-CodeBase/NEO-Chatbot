"use client";

import { useEffect, useState } from "react";
import { api } from "./api";

// CRM → Doctors Availability: the shapes of GET /v1/crm/availability (cards) and /availability/{id} (week).

export type Span = { start: string; end: string };
export type Booking = {
  id: string;
  start: string | null; // HH:MM; null = the patient chose "Any time"
  end: string | null;
  type: "in_clinic" | "online";
  status: string;
  patient: string;
  lead_code: string;
  phone: string | null;
  treatment: string | null;
  stage: string; // the lead's stage
  request_id: string | null; // its Inbox request while still pending
};
export type Day = {
  date: string;
  closed: boolean;
  holiday: string | null;
  leave: string | null; // null = not on leave
  in_clinic: Span[];
  online: Span[];
  free_in_clinic: string[];
  free_online: string[];
  bookings: Booking[];
};
export type AvailDoctor = {
  id: string;
  name: string;
  role_title: string;
  in_clinic_minutes: number;
  online_minutes: number;
};
export type Board = {
  today: string;
  open_time: string;
  close_time: string;
  doctors: { doctor: AvailDoctor; today: Day }[];
};
export type Week = {
  doctor: AvailDoctor;
  today: string;
  open_time: string;
  close_time: string;
  days: Day[];
};

/** The clinic's active doctors (sidebar); empty while loading or without access. */
export function useDoctors(clinicId: string | undefined): AvailDoctor[] {
  const [list, setList] = useState<{
    clinic: string;
    doctors: AvailDoctor[];
  }>();
  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<AvailDoctor[]>(`/v1/crm/availability/doctors?clinic=${clinicId}`).then(
      (doctors) => live && setList({ clinic: clinicId, doctors }),
      () => live && setList({ clinic: clinicId, doctors: [] }),
    );
    return () => {
      live = false;
    };
  }, [clinicId]);
  return list && list.clinic === clinicId ? list.doctors : [];
}

/** "10:00–19:00, 15:00–18:00" (24-hour clinic time). */
export const spans = (s: Span[]) =>
  s.map((x) => `${x.start}–${x.end}`).join(", ");
