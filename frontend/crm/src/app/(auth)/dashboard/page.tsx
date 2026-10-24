import type { Metadata } from "next";
import Link from "next/link";
import { HomeIcon } from "@/components/auth/icons";

export const metadata: Metadata = { title: "NEO CRM | Signed in" };

// TEMPORARY (sub-step 1): the design's "Signed in" screen, until the Dashboard is built.
export default function SignedInPage() {
  return (
    <section className="done">
      <div className="ic">
        <HomeIcon />
      </div>
      <h2>Signed in</h2>
      <p className="sub">Demo only. The Dashboard is the next screen we build.</p>
      <Link className="btn" href="/sign-in">
        Sign out
      </Link>
    </section>
  );
}
