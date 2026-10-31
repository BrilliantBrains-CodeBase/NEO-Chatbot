"use client";

import { useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError, type Me } from "@/lib/api";

// My profile: my details (name editable; email and roles are changed by a manager in Team).
export default function ProfilePage() {
  const { me, setMe, toast } = useCrm();
  const [name, setName] = useState<string | null>(null); // null: not editing
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!me) return null;

  async function save() {
    const value = (name ?? "").trim();
    if (value.length < 2) {
      setError("Please enter your name.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      setMe(
        await api<Me>("/v1/crm/me", {
          method: "PATCH",
          body: JSON.stringify({ name: value }),
        }),
      );
      setName(null);
      toast("Name saved");
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const row = (label: string, value: React.ReactNode) => (
    <div
      className="row"
      style={{ gap: 12, padding: "10px 0", borderTop: "1px solid var(--line)" }}
    >
      <span className="sub2" style={{ width: 120, flex: "none" }}>
        {label}
      </span>
      <span style={{ flex: 1, minWidth: 0 }}>{value}</span>
    </div>
  );

  return (
    <>
      <div className="ph">
        <div>
          <h1>My profile</h1>
          <p>Your details in the CRM.</p>
        </div>
      </div>
      <div className="card" style={{ padding: 16, maxWidth: 640 }}>
        <div className="row" style={{ gap: 12, marginBottom: 12 }}>
          <span className="av" aria-hidden>
            {me.initials}
          </span>
          <div>
            <b>{me.name}</b>
            <div className="sub2">{me.role_label}</div>
          </div>
        </div>
        {row(
          "Name",
          name === null ? (
            <span
              className="row"
              style={{ gap: 8, justifyContent: "space-between" }}
            >
              {me.name}
              <button className="btn g" onClick={() => setName(me.name)}>
                Edit
              </button>
            </span>
          ) : (
            <span className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <input
                className="f"
                style={{ flex: "1 1 200px" }}
                aria-label="Name"
                maxLength={100}
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void save()}
              />
              <button
                className="btn"
                disabled={busy}
                onClick={() => void save()}
              >
                {busy ? "Saving…" : "Save"}
              </button>
              <button
                className="btn g"
                disabled={busy}
                onClick={() => {
                  setName(null);
                  setError("");
                }}
              >
                Cancel
              </button>
            </span>
          ),
        )}
        {error && (
          <p role="alert" style={{ color: "var(--err)", margin: "0 0 8px" }}>
            {error}
          </p>
        )}
        {row("Email", me.email)}
        {row("Role", me.role_label)}
        {row(
          "Clinics",
          me.clinics.map((c) => `${c.name} (${c.role_label})`).join(", ") ||
            "None",
        )}
        <p className="sub2" style={{ margin: "10px 0 0" }}>
          To change your email or role, ask your clinic manager (Team).
        </p>
      </div>
    </>
  );
}
