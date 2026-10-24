"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CLINICS, ME, type Clinic } from "@/lib/sample-data";
import { useCrm } from "./CrmProvider";
import Icon from "./Icon";

export default function Topbar({ onMenu }: { onMenu: () => void }) {
  const crm = useCrm();
  const router = useRouter();
  const [menu, setMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // The profile menu closes on any click outside it.
  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenu(false);
    };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [menu]);

  const go = (href: string) => {
    setMenu(false);
    router.push(href);
  };

  return (
    <header className="tb">
      <button className="ham" aria-label="Open menu" onClick={onMenu}>
        <Icon name="menu" />
      </button>
      <select
        className="sel"
        aria-label="Clinic"
        value={crm.clinic}
        onChange={(e) => crm.setClinic(e.target.value as Clinic)}
      >
        {CLINICS.map((c) => (
          <option key={c}>{c}</option>
        ))}
      </select>
      <label className="search hide-m">
        <Icon name="search" />
        <input
          placeholder="Search name or phone"
          aria-label="Search name or phone"
          onKeyDown={(e) => {
            if (e.key === "Enter") router.push(`/leads?q=${encodeURIComponent(e.currentTarget.value.trim())}`);
          }}
        />
      </label>
      <span className="sp" />
      <button className="ib" aria-label="Notifications" onClick={() => router.push("/inbox")}>
        <Icon name="bell" />
        {crm.ready && <b>{crm.inboxCount + crm.pending("cb")}</b>}
      </button>
      <button
        className="btn"
        onClick={() =>
          crm.openModal({
            title: "Add lead",
            body: <p className="sub2" style={{ margin: 0 }}>The Add lead form is built with the Leads screen.</p>,
          })
        }
      >
        <Icon name="plus" />
        <span className="hide-m">Add lead</span>
      </button>
      <div ref={menuRef} style={{ position: "relative" }}>
        <button
          className="av"
          id="avb"
          aria-label="Profile menu"
          aria-expanded={menu}
          onClick={() => setMenu(!menu)}
        >
          {ME.initials}
        </button>
        <div className={`pmenu${menu ? " on" : ""}`} style={{ top: 44, right: 0 }} role="menu">
          <div className="who">
            <b>{ME.name}</b>
            <span>
              {ME.role} · {ME.email}
            </span>
          </div>
          <button role="menuitem" onClick={() => go("/profile")}>
            My profile
          </button>
          <button role="menuitem" onClick={() => go("/settings")}>
            Settings
          </button>
          <button role="menuitem" style={{ color: "var(--err)" }} onClick={() => go("/sign-in")}>
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
