"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { FieldError } from "./fields";

// 2-step login: after the password, the 6-digit code emailed to the person (from their clinic's Gmail, or the
// BB Gmail). The backend accepts this sign-in only once the code is verified. Sent once on arrival; Resend.
export default function VerifyCodeForm() {
  const router = useRouter();
  const [note, setNote] = useState("Sending your code…");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const sent = useRef(false);

  async function send() {
    setError("");
    try {
      const r = await api<{ sent_to: string }>("/v1/auth/code/send", {
        method: "POST",
      });
      setNote(
        `We sent a 6-digit code to ${r.sent_to}. It works for 10 minutes.`,
      );
    } catch (e) {
      if (e instanceof ApiError && e.status === 401)
        return router.replace("/sign-in");
      setNote("");
      setError(
        e instanceof ApiError
          ? e.message
          : "Could not send the code. Please try again.",
      );
    }
  }

  useEffect(() => {
    if (sent.current) return; // once, even when React runs effects twice
    sent.current = true;
    void send();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const code = String(
      new FormData(e.currentTarget).get("code") ?? "",
    ).replace(/\D/g, "");
    if (code.length !== 6)
      return setError("Enter the 6 digits from the email.");
    setBusy(true);
    setError("");
    try {
      await api("/v1/auth/code/verify", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      router.replace("/dashboard");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not check the code. Please try again.",
      );
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="t-code">
      <h2 id="t-code">Enter your sign-in code</h2>
      <p className="sub">{note}</p>
      <form onSubmit={submit} noValidate>
        <label>
          Code
          <input
            name="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            placeholder="6 digits"
            aria-invalid={!!error}
            autoFocus
          />
          <FieldError message={error} />
        </label>
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Checking…" : "Sign in"}
        </button>
      </form>
      <p className="alt">
        <button type="button" className="link" onClick={() => void send()}>
          Send a new code
        </button>
        {" · "}
        <button
          type="button"
          className="link"
          onClick={async () => {
            await supabase().auth.signOut();
            router.replace("/sign-in");
          }}
        >
          Use another account
        </button>
      </p>
    </section>
  );
}
