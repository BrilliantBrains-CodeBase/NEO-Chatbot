import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { NextConfig } from "next";

// All keys live in one file, backend/.env (user's choice). The CRM takes ONLY its NEXT_PUBLIC_ lines from it
// (the Supabase URL and publishable key, both safe in the browser) and never the database password or any
// other backend secret. Where that file does not exist (a hosting service), the normal environment is used.
function crmPublicEnv(): Record<string, string> {
  const file = join(process.cwd(), "..", "..", "backend", ".env");
  const out: Record<string, string> = {};
  if (existsSync(file)) {
    for (const line of readFileSync(file, "utf-8").split(/\r?\n/)) {
      const m = line.match(/^\s*(NEXT_PUBLIC_[A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
      if (m) out[m[1]] = m[2].replace(/^["']|["']$/g, "");
    }
  }
  for (const key of ["NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"]) {
    out[key] ??= process.env[key] ?? "";
  }
  return out;
}

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  env: crmPublicEnv(),
};

export default nextConfig;
