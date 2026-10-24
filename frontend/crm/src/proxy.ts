import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

// Runs before every CRM page (Next.js 16 "proxy", formerly middleware). It refreshes the Supabase session
// cookie and does the quick check only: signed-out visitors go to /sign-in, signed-in ones skip it. The real
// permission check (approved profile, clinic role) is done by the backend on every data request.
const PUBLIC = ["/sign-in", "/create-account", "/reset-password"];

export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll(cookiesToSet, headers) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
          Object.entries(headers ?? {}).forEach(([k, v]) => response.headers.set(k, v));
        },
      },
    },
  );
  const { data } = await supabase.auth.getClaims();
  const signedIn = !!data?.claims;
  const path = request.nextUrl.pathname;
  const isPublic = PUBLIC.some((p) => path === p || path.startsWith(p + "/"));

  if (!signedIn && !isPublic) return redirect(request, response, "/sign-in");
  if (signedIn && (isPublic || path === "/")) return redirect(request, response, "/dashboard");
  return response;
}

function redirect(request: NextRequest, from: NextResponse, to: string) {
  const res = NextResponse.redirect(new URL(to, request.url));
  from.cookies.getAll().forEach((c) => res.cookies.set(c)); // keep a refreshed session
  return res;
}

export const config = {
  // Every page, not Next.js files or images.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
