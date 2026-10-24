"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { demoSignIn } from "@/lib/auth-demo";
import { EMAIL, type Errors } from "@/lib/validation";
import { FieldError, PasswordInput } from "./fields";

type Field = "email" | "password";

export default function SignInForm() {
  const router = useRouter();
  const [errors, setErrors] = useState<Errors<Field>>({});
  const [banner, setBanner] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");
    const next: Errors<Field> = {
      email: EMAIL.test(email) ? undefined : "Enter a valid work email.",
      password: password ? undefined : "Enter your password.",
    };
    setErrors(next);
    setBanner("");
    if (next.email || next.password) return;
    setBusy(true);
    const { ok } = await demoSignIn(email, password);
    setBusy(false);
    if (!ok) {
      setBanner("Email or password is incorrect.");
      return;
    }
    router.push("/dashboard");
  }

  return (
    <section aria-labelledby="t-login">
      <h2 id="t-login">Sign in</h2>
      <p className="sub">Welcome back. Sign in to your clinic workspace.</p>
      <form onSubmit={submit} noValidate>
        {banner && (
          <div className="banner err" role="alert">
            {banner}
          </div>
        )}
        <label>
          Work email
          <input
            type="email"
            name="email"
            autoComplete="email"
            placeholder="name@clinic.com"
            aria-invalid={!!errors.email}
            autoFocus
          />
          <FieldError message={errors.email} />
        </label>
        <label>
          Password
          <PasswordInput
            name="password"
            autoComplete="current-password"
            placeholder="Your password"
            aria-invalid={!!errors.password}
          />
          <FieldError message={errors.password} />
        </label>
        <div className="line">
          <label className="check">
            <input type="checkbox" name="remember" defaultChecked />
            Remember me
          </label>
          <Link className="link" href="/reset-password">
            Forgot password?
          </Link>
        </div>
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="alt">
        New to the team?{" "}
        <Link className="link" href="/create-account">
          Create an account
        </Link>
      </p>
    </section>
  );
}
