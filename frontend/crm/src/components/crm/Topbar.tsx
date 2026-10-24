"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { Clinic } from "@/lib/sample-data";
import AddLeadForm from "@/components/leads/AddLeadForm";
import { useCrm } from "./CrmProvider";
import Icon from "./Icon";

export default function Topbar({ onMenu }: { onMenu: () => void }) {
  const crm = useCrm();
  const pending = Object.values(crm.inbox ?? {}).reduce((a, b) => a + b, 0);
  const clinicId = crm.me?.clinics.find((c) => c.name === crm.clinic)?.id;
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
        {crm.clinics.map((c) => (
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
        {!!pending && <b>{pending}</b>}
      </button>
      <button
        className="btn"
        onClick={() =>
          crm.openModal({
            title: "Add lead",
            body: clinicId ? (
              <AddLeadForm clinicId={clinicId} onDone={crm.closeModal} />
            ) : (
              <p className="sub2" style={{ margin: 0 }}>Loading your clinics…</p>
            ),
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
          {crm.me?.initials ?? ""}
        </button>
        <div className={`pmenu${menu ? " on" : ""}`} style={{ top: 44, right: 0 }} role="menu">
          <div className="who">
            <b>{crm.me?.name}</b>
            <span>
              {crm.me?.role_label} · {crm.me?.email}
            </span>
          </div>
          <button role="menuitem" onClick={() => go("/profile")}>
            My profile
          </button>
          <button role="menuitem" onClick={() => go("/settings")}>
            Settings
          </button>
          <button
            role="menuitem"
            style={{ color: "var(--err)" }}
            onClick={() => {
              setMenu(false);
              void crm.signOut();
            }}
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
