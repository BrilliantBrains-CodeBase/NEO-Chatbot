"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import {
  EMAIL,
  INDIAN_MOBILE,
  STRENGTH_COLOR,
  STRENGTH_HINT,
  passwordScore,
  type Errors,
} from "@/lib/validation";
import { ApiError } from "@/lib/api";
import { FieldError, PasswordInput } from "./fields";
import { CheckIcon, InfoIcon } from "./icons";

type Field = "name" | "phone" | "email" | "clinic" | "role" | "password" | "confirm" | "terms";

// The clinic is asked as its code (e.g. NFHT, given by the admin), so this public page never lists
// the clinics that use the CRM. Only Super Admin approves an Admin request.
const CLINIC_CODE = /^[A-Z][A-Z0-9]{1,9}$/; // as the backend (app/core/codes.py): NFHT, BF2, CL99
const ROLES: [string, string][] = [
  ["front_desk", "Front Desk"],
  ["doctor", "Doctor"],
  ["clinic_manager", "Admin"],
];

export default function CreateAccountForm() {
  const [errors, setErrors] = useState<Errors<Field>>({});
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [sent, setSent] = useState<{ clinic: string; role: string; email: string } | null>(null);
  const score = passwordScore(password);

  const [banner, setBanner] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const v = (k: string) => String(f.get(k) ?? "").trim();
    const next: Errors<Field> = {
      name: v("name").length >= 2 ? undefined : "Enter your full name.",
      phone: INDIAN_MOBILE.test(phone) ? undefined : "Enter a 10 digit mobile number.",
      email: EMAIL.test(v("email")) ? undefined : "Enter a valid work email.",
      clinic: CLINIC_CODE.test(v("clinic").toUpperCase())
        ? undefined
        : "Enter the clinic code your admin gave you, e.g. NFHT.",
      role: v("role") ? undefined : "Select your role.",
      password: score >= 3 ? undefined : "Use 8+ characters with a number and a capital letter.",
      confirm: v("confirm") && f.get("confirm") === password ? undefined : "Passwords do not match.",
      terms: f.get("terms") ? undefined : "Please accept to continue.",
    };
    setErrors(next);
    if (Object.values(next).some(Boolean)) return;
    setBanner("");
    setBusy(true);
    try {
      const done = await requestAccess({
        full_name: v("name"),
        phone: "+91" + phone,
        email: v("email").toLowerCase(),
        password,
        clinic: v("clinic").toUpperCase(),
        role: v("role"),
      });
      setSent({ clinic: done.clinic, role: done.role, email: v("email") });
    } catch (err) {
      setBanner(
        err instanceof ApiError
          ? err.message
          : "Could not send the request. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <section className="done" key="sent">
        <div className="ic">
          <CheckIcon />
        </div>
        <h2>Request sent</h2>
        <p className="sub">
          Your request to join {sent.clinic} as {sent.role} is sent. Your admin will review it, and you
          will get an email at {sent.email} once approved.
        </p>
        <Link className="btn" href="/sign-in">
          Back to sign in
        </Link>
      </section>
    );
  }

  return (
    <section aria-labelledby="t-signup">
      <h2 id="t-signup">Create an account</h2>
      <p className="sub">Request access to your clinic&apos;s CRM.</p>
      <form onSubmit={submit} noValidate>
        {banner && (
          <div className="banner err" role="alert">
            {banner}
          </div>
        )}
        <div className="row2">
          <label>
            Full name
            <input name="name" autoComplete="name" placeholder="Priya Sharma" aria-invalid={!!errors.name} />
            <FieldError message={errors.name} />
          </label>
          <label>
            Mobile number
            <input
              name="phone"
              inputMode="numeric"
              maxLength={10}
              autoComplete="tel-national"
              placeholder="10 digit number"
              value={phone}
              onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))}
              aria-invalid={!!errors.phone}
            />
            <FieldError message={errors.phone} />
          </label>
        </div>
        <label>
          Work email
          <input type="email" name="email" autoComplete="email" placeholder="name@clinic.com" aria-invalid={!!errors.email} />
          <FieldError message={errors.email} />
        </label>
        <div className="row2">
          <label>
            Clinic code
            <input
              name="clinic"
              placeholder="e.g. NFHT"
              maxLength={5}
              autoCapitalize="characters"
              aria-invalid={!!errors.clinic}
            />
            <FieldError message={errors.clinic} />
          </label>
          <label>
            Role
            <select name="role" defaultValue="" aria-invalid={!!errors.role}>
              <option value="">Select role</option>
              {ROLES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <FieldError message={errors.role} />
          </label>
        </div>
        <label>
          Password
          <PasswordInput
            name="password"
            autoComplete="new-password"
            placeholder="At least 8 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={!!errors.password}
          />
          <span className="meter">
            <i style={{ width: `${score * 25}%`, background: STRENGTH_COLOR[score] }} />
          </span>
          <span className="hint">{STRENGTH_HINT[score]}</span>
          <FieldError message={errors.password} />
        </label>
        <label>
          Confirm password
          <input
            type="password"
            name="confirm"
            autoComplete="new-password"
            placeholder="Type it again"
            aria-invalid={!!errors.confirm}
          />
          <FieldError message={errors.confirm} />
        </label>
        <label className="check">
          <input type="checkbox" name="terms" />I agree to keep patient data confidential and follow clinic policy.
        </label>
        <FieldError message={errors.terms} />
        <div className="note">
          <InfoIcon />
          Your access starts after your admin approves the request.
        </div>
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Sending…" : "Request access"}
        </button>
      </form>
      <p className="alt">
        Already have an account?{" "}
        <Link className="link" href="/sign-in">
          Sign in
        </Link>
      </p>
    </section>
  );
}

/** POST /v1/auth/request-access (no sign-in): the login is made, and waits for approval. */
async function requestAccess(body: Record<string, string>): Promise<{ clinic: string; role: string }> {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  let res: Response;
  try {
    res = await fetch(`${base}/v1/auth/request-access`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "The CRM server cannot be reached. Check your connection and try again.");
  }
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail : "Please check the form and try again.");
  }
  return data as { clinic: string; role: string };
}
