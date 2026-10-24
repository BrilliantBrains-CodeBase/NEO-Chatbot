"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { EMAIL } from "@/lib/validation";
import { FieldError } from "./fields";
import { MailIcon } from "./icons";

export default function ResetPasswordForm() {
  const [error, setError] = useState<string>();
  const [sent, setSent] = useState(false);

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const email = String(new FormData(e.currentTarget).get("email") ?? "").trim();
    if (!EMAIL.test(email)) {
      setError("Enter a valid work email.");
      return;
    }
    // Sub-step 1 (screens only): no email is sent yet. The real reset link comes from Supabase Auth.
    setSent(true);
  }

  if (sent) {
    return (
      <section className="done" key="sent">
        <div className="ic">
          <MailIcon />
        </div>
        <h2>Check your email</h2>
        <p className="sub">If an account exists for that email, a reset link is on its way. The link expires in 1 hour.</p>
        <Link className="btn" href="/sign-in">
          Back to sign in
        </Link>
      </section>
    );
  }

  return (
    <section aria-labelledby="t-forgot">
      <h2 id="t-forgot">Reset password</h2>
      <p className="sub">Enter your work email and we&apos;ll send you a reset link.</p>
      <form onSubmit={submit} noValidate>
        <label>
          Work email
          <input type="email" name="email" autoComplete="email" placeholder="name@clinic.com" aria-invalid={!!error} autoFocus />
          <FieldError message={error} />
        </label>
        <button className="btn" type="submit">
          Send reset link
        </button>
      </form>
      <p className="alt">
        <Link className="link" href="/sign-in">
          Back to sign in
        </Link>
      </p>
    </section>
  );
}
