"use client";

import { supabase } from "./supabase";

// The CRM's only way to read or change data: our backend's JSON API (/v1/crm/...), with the signed-in
// person's token. The backend checks the token and the person's role for that clinic on every call.
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
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
    throw new ApiError(0, "The CRM server cannot be reached. Check your connection and try again.");
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail : "Something went wrong. Please try again.");
  }
  return body as T;
}

/** GET /v1/crm/me: who is signed in and which clinics they see. */
export type Me = {
  id: string;
  name: string;
  email: string;
  initials: string;
  bb_admin: boolean;
  role_label: string;
  clinics: { id: string; name: string; role: string; role_label: string }[];
};
