"use client";

import { useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { supabase } from "@/lib/supabase";
import { STRENGTH_COLOR, STRENGTH_HINT, passwordScore } from "@/lib/validation";

// My profile → Change password, for the signed-in person (Supabase Auth changes it for this sign-in).
// No "current password" box: signing in again would start a new sign-in that 2-step login asks a code for.
export default function PasswordCard() {
  const { toast } = useCrm();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [shown, setShown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const score = passwordScore(password);

  async function save() {
    if (score < 3) {
      setError("Use 8+ characters with a number and a capital letter.");
      return;
    }
    if (confirm !== password) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError("");
    const { error: e } = await supabase().auth.updateUser({ password });
    setBusy(false);
    if (e) {
      setError(
        e.message.includes("different")
          ? "Choose a password different from your old one."
          : "Could not change the password. Please try again.",
      );
      return;
    }
    setPassword("");
    setConfirm("");
    toast("Password changed");
  }

  return (
    <section className="st-card">
      <h2>Change password</h2>
      <p>Use at least 8 characters with a number and a capital letter.</p>
      <div style={{ display: "grid", gap: 8, maxWidth: 420 }}>
        <input
          className="f"
          type={shown ? "text" : "password"}
          aria-label="New password"
          placeholder="New password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {password && (
          <span style={{ color: STRENGTH_COLOR[score], fontSize: "var(--fs-small)" }}>
            {STRENGTH_HINT[score]}
          </span>
        )}
        <input
          className="f"
          type={shown ? "text" : "password"}
          aria-label="Confirm new password"
          placeholder="Type it again"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void save()}
        />
        {error && (
          <p role="alert" style={{ color: "var(--err)", margin: 0 }}>
            {error}
          </p>
        )}
        <div className="row" style={{ gap: 8 }}>
          <button
            className="btn"
            disabled={busy || !password}
            onClick={() => void save()}
          >
            {busy ? "Saving…" : "Change password"}
          </button>
          <button className="btn g" onClick={() => setShown(!shown)}>
            {shown ? "Hide" : "Show"}
          </button>
        </div>
      </div>
    </section>
  );
}
