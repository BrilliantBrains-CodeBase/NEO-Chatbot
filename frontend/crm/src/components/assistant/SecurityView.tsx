"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";
import GmailPanel from "./GmailPanel";
import ClinicsCard from "./ClinicsCard";

// Dashboard → Login & security (BB Admin). Main BB Admin: the one email with full power over every clinic;
// nobody can disable, remove or demote it, and only the main BB Admin changes it (any BB Admin sets the first).

type MainAdmin = { email: string | null; is_me: boolean; can_change: boolean };

export default function SecurityView() {
  const { me, toast } = useCrm();
  const [main, setMain] = useState<MainAdmin | null>(null);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    api<MainAdmin>("/v1/crm/security/main-admin").then(
      (m) => live && setMain(m),
      (e) =>
        live && setError(e instanceof ApiError ? e.message : "Could not load."),
    );
    return () => {
      live = false;
    };
  }, []);

  if (me && !me.bb_admin)
    return (
      <div className="empty">
        <h2>No access</h2>
        Login & security is for BB Admin.
      </div>
    );

  async function save() {
    const next = email.trim().toLowerCase();
    if (
      !window.confirm(
        `Make ${next} the main BB Admin? That login gets full control of every clinic, and only it can change this again.`,
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      setMain(
        await api<MainAdmin>("/v1/crm/security/main-admin", {
          method: "PUT",
          body: JSON.stringify({ email: next }),
        }),
      );
      setEmail("");
      toast(`${next} is now the main BB Admin`);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page" style={{ maxWidth: 820 }}>
      <h2 style={{ margin: "0 0 4px" }}>Login & security</h2>
      <p className="sub2" style={{ margin: "0 0 14px" }}>
        Who controls the whole platform. 2-step login comes next.
      </p>
      {error && <div className="warnbox">{error}</div>}
      {!main && !error && <p className="sub2">Loading…</p>}
      {main && (
        <section className="card">
          <h3 style={{ margin: "0 0 4px" }}>Main BB Admin</h3>
          <p className="sub2" style={{ margin: "0 0 10px" }}>
            One email with full power over every clinic. Nobody can disable,
            remove or demote it in Team & access. Only the main BB Admin can
            change it.
          </p>
          <p style={{ margin: "0 0 10px" }}>
            {main.email ? (
              <>
                Now: <b>{main.email}</b>
                {main.is_me && <span className="sub2"> (you)</span>}
              </>
            ) : (
              <span className="sub2">
                Not set yet. Any BB Admin can set the first one.
              </span>
            )}
          </p>
          {main.can_change ? (
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <input
                className="f"
                style={{ flex: 1, minWidth: 240 }}
                type="email"
                placeholder="Email of an existing login"
                maxLength={120}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <button
                className="btn"
                disabled={busy || !email.includes("@")}
                onClick={() => void save()}
              >
                {main.email ? "Change main BB Admin" : "Set main BB Admin"}
              </button>
            </div>
          ) : (
            <p className="sub2" style={{ margin: 0 }}>
              Only {main.email} can change this.
            </p>
          )}
          <p className="sub2" style={{ margin: "8px 0 0", fontSize: 12 }}>
            The email must belong to a login that can already sign in (invite
            them in Team & access first). Use an email you can always open, so
            you never lock yourself out.
          </p>
        </section>
      )}
      <ClinicsCard />
      <TwoStep />
      <section className="card" style={{ marginTop: 14 }}>
        <h3 style={{ margin: "0 0 4px" }}>BB Gmail</h3>
        <p className="sub2" style={{ margin: 0 }}>
          Sends BB Admins&apos; login codes, and any clinic&apos;s emails while
          that clinic has not connected its own Gmail (Integrations → Email).
        </p>
        <GmailPanel url="/v1/crm/security/email" />
      </section>
    </div>
  );
}

const ROLES: [string, string][] = [
  ["bb_admin", "BB Admin"],
  ["clinic_manager", "Clinic Manager"],
  ["front_desk", "Front Desk"],
  ["doctor", "Doctor"],
];

/** 2-step login: the roles that need an emailed code after the password (BB Admin only; needs the BB Gmail). */
function TwoStep() {
  const { toast } = useCrm();
  const [roles, setRoles] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    api<{ roles: string[] }>("/v1/crm/security/two-step").then(
      (r) => live && setRoles(r.roles),
      (e) =>
        live && setError(e instanceof ApiError ? e.message : "Could not load."),
    );
    return () => {
      live = false;
    };
  }, []);

  async function save(next: string[]) {
    setBusy(true);
    setError("");
    try {
      const r = await api<{ roles: string[] }>("/v1/crm/security/two-step", {
        method: "PUT",
        body: JSON.stringify({ roles: next }),
      });
      setRoles(r.roles);
      toast(r.roles.length ? "2-step login saved" : "2-step login is off");
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" style={{ marginTop: 14 }}>
      <h3 style={{ margin: "0 0 4px" }}>2-step login</h3>
      <p className="sub2" style={{ margin: "0 0 8px" }}>
        After the password, these roles must type a 6-digit code sent to their
        email (from their clinic&apos;s Gmail, or the BB Gmail). The code works
        for 10 minutes; 5 wrong codes lock sign-in for 15 minutes. It applies at
        their next sign-in; you stay signed in.
      </p>
      {roles && (
        <div className="row" style={{ gap: 14, flexWrap: "wrap" }}>
          {ROLES.map(([id, label]) => (
            <label
              key={id}
              className="row"
              style={{ gap: 6, cursor: "pointer" }}
            >
              <input
                type="checkbox"
                disabled={busy}
                checked={roles.includes(id)}
                onChange={(e) =>
                  void save(
                    e.target.checked
                      ? [...roles, id]
                      : roles.filter((r) => r !== id),
                  )
                }
              />
              {label}
            </label>
          ))}
        </div>
      )}
      {error && (
        <p className="warnbox" style={{ marginTop: 6 }}>
          {error}
        </p>
      )}
    </section>
  );
}
