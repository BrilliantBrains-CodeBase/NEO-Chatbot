"use client";

import { use, type ReactNode } from "react";
import { browser } from "react-dom";

/** Content whose first render depends on the browser (the current time on every CRM screen). Rendered
 * only in the browser; until then the closest Suspense fallback shows (Next.js "browser-only" pattern). */
export default function BrowserOnly({ children, reason }: { children: ReactNode; reason: string }) {
  use(browser(reason));
  return children;
}
