"use client";

import { Suspense, type ReactNode } from "react";
import BrowserOnly from "./BrowserOnly";

/** A part of a screen that depends on the current time (dates, "5m ago", today's appointments). The rest
 * of the screen renders ahead; this part fills in in the browser (Next.js "instant navigation" pattern). */
export default function Live({ children, fallback = null }: { children: ReactNode; fallback?: ReactNode }) {
  return (
    <Suspense fallback={fallback}>
      <BrowserOnly reason="Shows times relative to now.">{children}</BrowserOnly>
    </Suspense>
  );
}

/** Today's date, e.g. "Saturday, 24 October". Use inside <Live>. */
export function Today() {
  return <>{new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}</>;
}
