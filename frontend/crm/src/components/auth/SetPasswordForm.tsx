"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { api, type Me } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import {
  STRENGTH_COLOR,
  STRENGTH_HINT,
  passwordScore,
  type Errors,
} from "@/lib/validation";
import { FieldError, PasswordInput } from "./fields";

type Field = "password" | "confirm";

/** The sign-in an emailed link brings. An invite (made by the backend) carries it after "#"; this browser
 * client only reads "?code=" links (a reset asked for in this browser) by itself, so "#" links are read here. */
async function linkSession(): Promise<string> {
  const hash = new URLSearchParams(window.location.hash.slice(1));
  if (hash.get("error_description"))
    return "This link has expired or was already used. Ask for a new one.";
  const access = hash.get("access_token");
  const refresh = hash.get("refresh_token");
  if (access && refresh) {
    const { error } = await supabase().auth.setSession({
      access_token: access,
      refresh_token: refresh,
    });
    window.history.replaceState(null, "", window.location.pathname); // the tokens leave the address bar
    if (error) return "This link has expired or was already used. Ask for a new one.";
  }
  const { data } = await supabase().auth.getSession(); // a "?code=" link is exchanged by the client itself
  return data.session ? "" : "Open this page from the link in your email.";
}

export default function SetPasswordForm() {
  const router = useRouter();
  const [ready, setReady] = useState<"wait" | "ok" | string>("wait");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Errors<Field>>({});
  const [banner, setBanner] = useState("");
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState(false); // password set, access not approved yet
  const score = passwordScore(password);

  useEffect(() => {
    linkSession().then((problem) => setReady(problem || "ok"));
  }, []);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const next: Errors<Field> = {
      password:
        score >= 3
          ? undefined
          : "Use 8+ characters with a number and a capital letter.",
      confirm:
        f.get("confirm") === password ? undefined : "Passwords do not match.",
    };
    setErrors(next);
    setBanner("");
    if (next.password || next.confirm) return;
    setBusy(true);
    const { error } = await supabase().auth.updateUser({ password });
    if (error) {
      setBusy(false);
      setBanner(
        error.message.includes("different")
          ? "Choose a password different from your old one."
          : "Could not save the password. Open the link from your email again.",
      );
      return;
    }
    try {
      await api<Me>("/v1/crm/me"); // approved: straight into the CRM
      router.replace("/dashboard");
    } catch {
      await supabase().auth.signOut(); // a login waiting for approval
      setWaiting(true);
      setBusy(false);
    }
  }

  if (waiting)
    return (
      <section className="done">
        <h2>Password saved</h2>
        <p className="sub">
          Your access is waiting for approval by your admin. You can
          sign in once it is approved.
        </p>
        <Link className="btn" href="/sign-in">
          Back to sign in
        </Link>
      </section>
    );

  if (ready !== "ok")
    return (
      <section>
        <h2>Set your password</h2>
        <p className="sub">
          {ready === "wait" ? "Checking your link…" : ready}
        </p>
        {ready !== "wait" && (
          <Link className="btn" href="/reset-password">
            Send a new link
          </Link>
        )}
      </section>
    );

  return (
    <section aria-labelledby="t-set">
      <h2 id="t-set">Set your password</h2>
      <p className="sub">Choose a password for your NEO CRM account.</p>
      <form onSubmit={submit} noValidate>
        {banner && (
          <div className="banner err" role="alert">
            {banner}
          </div>
        )}
        <label>
          New password
          <PasswordInput
            name="password"
            autoComplete="new-password"
            placeholder="At least 8 characters"
            aria-invalid={!!errors.password}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
          />
          {password && (
            <span style={{ color: STRENGTH_COLOR[score], fontSize: 13 }}>
              {STRENGTH_HINT[score]}
            </span>
          )}
          <FieldError message={errors.password} />
        </label>
        <label>
          Confirm password
          <PasswordInput
            name="confirm"
            autoComplete="new-password"
            placeholder="Type it again"
            aria-invalid={!!errors.confirm}
          />
          <FieldError message={errors.confirm} />
        </label>
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save password"}
        </button>
      </form>
    </section>
  );
}
