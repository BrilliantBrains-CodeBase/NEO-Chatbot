"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

// Supabase Auth in the browser (sign in, sign out, the current session). The session is kept in cookies so
// the proxy (src/proxy.ts) can send signed-out visitors to /sign-in. Only the publishable key is used here;
// all CRM data comes from our backend as JSON, never straight from the database.
let client: SupabaseClient | undefined;

export function supabase(): SupabaseClient {
  client ??= createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
  );
  return client;
}
