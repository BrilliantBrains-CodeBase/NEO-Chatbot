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
import { FieldError, PasswordInput } from "./fields";
import { CheckIcon, InfoIcon } from "./icons";

type Field = "name" | "phone" | "email" | "clinic" | "role" | "password" | "confirm" | "terms";

const CLINICS = ["Neo Fertility", "Neo Follicle", "Derma Solutions"];
const ROLES = ["Front Desk", "Clinic Manager"];

export default function CreateAccountForm() {
  const [errors, setErrors] = useState<Errors<Field>>({});
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [sent, setSent] = useState<{ clinic: string; role: string; email: string } | null>(null);
  const score = passwordScore(password);

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const v = (k: string) => String(f.get(k) ?? "").trim();
    const next: Errors<Field> = {
      name: v("name").length >= 2 ? undefined : "Enter your full name.",
      phone: INDIAN_MOBILE.test(phone) ? undefined : "Enter a 10 digit mobile number.",
      email: EMAIL.test(v("email")) ? undefined : "Enter a valid work email.",
      clinic: v("clinic") ? undefined : "Select your clinic.",
      role: v("role") ? undefined : "Select your role.",
      password: score >= 3 ? undefined : "Use 8+ characters with a number and a capital letter.",
      confirm: v("confirm") && f.get("confirm") === password ? undefined : "Passwords do not match.",
      terms: f.get("terms") ? undefined : "Please accept to continue.",
    };
    setErrors(next);
    if (Object.values(next).some(Boolean)) return;
    // Sub-step 1 (screens only): nothing is sent yet. Connecting sends the request to the backend as JSON.
    setSent({ clinic: v("clinic"), role: v("role"), email: v("email") });
  }

  if (sent) {
    return (
      <section className="done" key="sent">
        <div className="ic">
          <CheckIcon />
        </div>
        <h2>Request sent</h2>
        <p className="sub">
          Your request to join {sent.clinic} as {sent.role} is sent. Your clinic manager will review it, and you
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
            Clinic
            <select name="clinic" defaultValue="" aria-invalid={!!errors.clinic}>
              <option value="">Select clinic</option>
              {CLINICS.map((c) => (
                <option key={c}>{c}</option>
              ))}
              <option disabled>Clinic 4 (coming soon)</option>
            </select>
            <FieldError message={errors.clinic} />
          </label>
          <label>
            Role
            <select name="role" defaultValue="" aria-invalid={!!errors.role}>
              <option value="">Select role</option>
              {ROLES.map((r) => (
                <option key={r}>{r}</option>
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
          Your access starts after your clinic manager approves the request.
        </div>
        <button className="btn" type="submit">
          Request access
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
