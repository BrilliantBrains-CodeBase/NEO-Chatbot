"use client";

import { usePathname, useRouter } from "next/navigation";
import { canSee } from "@/lib/access";
import { Suspense, useEffect, useState, type ReactNode } from "react";
import CrmProvider, { useCrm } from "./CrmProvider";
import Icon from "./Icon";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";

// The CRM frame of the approved design: sidebar, top bar, page, and the shared right-side panel, pop-up
// form and confirmation message that every screen uses.
export default function Shell({ children }: { children: ReactNode }) {
  return (
    <CrmProvider>
      <Frame>{children}</Frame>
    </CrmProvider>
  );
}

function Frame({ children }: { children: ReactNode }) {
  const crm = useCrm();
  const path = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const { drawer, closeDrawer, modal, closeModal } = crm;
  // Sign-in lands on the CRM's Dashboard; someone without it (Doctors) starts on their appointments.
  const router = useRouter();
  const noHome = path === "/dashboard" && !!crm.me && !canSee(crm.me, crm.clinic, path);
  useEffect(() => {
    if (noHome) router.replace("/appointments");
  }, [noHome, router]);

  // Esc closes the pop-up form first, then the panel (as in the design).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (modal) closeModal();
      else closeDrawer();
      setMenuOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [modal, closeModal, closeDrawer]);

  return (
    <div className="crm">
      <div className="app">
        {/* The empty card holds the menu's place until its links load. */}
        <Suspense fallback={<aside className="sb" aria-hidden="true" />}>
          <Sidebar open={menuOpen} onNavigate={() => setMenuOpen(false)} />
        </Suspense>
        <div className="main">
          <Topbar onMenu={() => setMenuOpen(!menuOpen)} />
          <main className="page">
            {noHome ? null : canSee(crm.me, crm.clinic, path) ? (
              children
            ) : (
              <div className="empty">
                <h2>No access</h2>
                Your admin has not given you this screen.
              </div>
            )}
          </main>
        </div>
      </div>

      <div
        className={`sb-ov${menuOpen ? " on" : ""}`}
        onClick={() => setMenuOpen(false)}
      />
      <div className={`ov${drawer ? " on" : ""}`} onClick={closeDrawer} />
      <aside
        className={`dr${drawer ? " on" : ""}`}
        aria-label="Details"
        aria-hidden={!drawer}
      >
        {drawer}
      </aside>

      <div
        className={`md${modal ? " on" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="mdt"
        onClick={(e) => e.target === e.currentTarget && closeModal()}
      >
        {modal && (
          <div className="mb">
            <div className="mh">
              <h2 id="mdt">{modal.title}</h2>
              <button aria-label="Close" onClick={closeModal}>
                <Icon name="x" />
              </button>
            </div>
            <div style={{ padding: "16px 20px" }}>{modal.body}</div>
          </div>
        )}
      </div>

      <div className={`toast${crm.toastText ? " on" : ""}`} role="status">
        {crm.toastText}
      </div>
    </div>
  );
}
