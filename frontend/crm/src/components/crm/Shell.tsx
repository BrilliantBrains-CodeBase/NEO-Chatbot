"use client";

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
  const [menuOpen, setMenuOpen] = useState(false);
  const { drawer, closeDrawer, modal, closeModal } = crm;

  // Esc closes the pop-up form first, then the panel (as in the design).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (modal) closeModal();
      else closeDrawer();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [modal, closeModal, closeDrawer]);

  return (
    <div className="crm">
      <div className="app">
        <Suspense>
          <Sidebar open={menuOpen} onNavigate={() => setMenuOpen(false)} />
        </Suspense>
        <div className="main">
          <Topbar onMenu={() => setMenuOpen(!menuOpen)} />
          <main className="page">{children}</main>
        </div>
      </div>

      <div className={`ov${drawer ? " on" : ""}`} onClick={closeDrawer} />
      <aside className={`dr${drawer ? " on" : ""}`} aria-label="Details" aria-hidden={!drawer}>
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
