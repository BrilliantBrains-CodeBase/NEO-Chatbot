"use client";

import { useState } from "react";
import PhoneField, {
  phoneError,
  phoneParts,
} from "@/components/crm/PhoneField";
import { api, ApiError, type LeadDetail, type LeadOptions } from "@/lib/api";

/** Edit details: what the first call corrected or added. Only what changed is sent; each change goes on the
 * lead's timeline. */
export default function EditDetails({
  lead,
  options,
  onSaved,
  onCancel,
}: {
  lead: LeadDetail;
  options: LeadOptions | null;
  onSaved: (d: LeadDetail) => void;
  onCancel: () => void;
}) {
  const treatments = options?.treatments ?? [];
  const known = !lead.treatment || treatments.includes(lead.treatment);
  const [f, setF] = useState({
    name: lead.name,
    phone: lead.phone ?? "+91",
    email: lead.email ?? "",
    treatment: known ? (lead.treatment ?? "") : "Other",
    other: known ? "" : (lead.treatment ?? ""),
    doctor_id: lead.doctor_id ?? "",
    type: lead.type ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) =>
    setF({ ...f, [k]: e.target.value });

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const treatment = f.treatment === "Other" ? f.other.trim() : f.treatment;
    const body: Record<string, string> = {};
    if (f.name.trim() !== lead.name) body.name = f.name;
    if (f.phone !== (lead.phone ?? "")) {
      const { code, digits } = phoneParts(f.phone);
      Object.assign(body, { phone: digits, phone_cc: code });
    }
    if (f.email.trim() !== (lead.email ?? "")) body.email = f.email.trim();
    if (treatment !== (lead.treatment ?? "")) body.treatment = treatment;
    if (f.doctor_id !== (lead.doctor_id ?? "")) body.doctor_id = f.doctor_id;
    if (f.type !== (lead.type ?? "")) body.type = f.type;
    if (Object.keys(body).length === 0) return onCancel();
    setBusy(true);
    setError("");
    try {
      onSaved(
        await api<LeadDetail>(
          `/v1/crm/leads/${encodeURIComponent(lead.code)}`,
          {
            method: "PATCH",
            body: JSON.stringify(body),
          },
        ),
      );
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const badPhone = phoneError(f.phone);
  return (
    <form className="fg" onSubmit={save} aria-label="Edit details">
      {error && (
        <div className="warnbox full" role="alert">
          {error}
        </div>
      )}
      <label>
        Full name
        <input
          className="f"
          value={f.name}
          onChange={set("name")}
          required
          minLength={2}
          maxLength={100}
        />
      </label>
      <label>
        Mobile number
        <PhoneField
          label="Mobile number"
          value={f.phone}
          onChange={(v) => setF({ ...f, phone: v })}
        />
        {badPhone && <span className="sub2">{badPhone}</span>}
      </label>
      <label className="full">
        Email
        <input
          className="f"
          type="email"
          value={f.email}
          onChange={set("email")}
          maxLength={200}
        />
      </label>
      <label>
        Treatment
        <select className="f" value={f.treatment} onChange={set("treatment")}>
          <option value="">Not decided</option>
          {treatments.map((t) => (
            <option key={t}>{t}</option>
          ))}
          {!treatments.includes("Other") && <option>Other</option>}
        </select>
      </label>
      {f.treatment === "Other" ? (
        <label>
          Other treatment
          <input
            className="f"
            value={f.other}
            onChange={set("other")}
            maxLength={100}
            required
            minLength={2}
          />
        </label>
      ) : (
        <span />
      )}
      <label>
        Preferred doctor
        <select className="f" value={f.doctor_id} onChange={set("doctor_id")}>
          <option value="">Any doctor</option>
          {(options?.doctors ?? []).map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Consultation
        <select className="f" value={f.type} onChange={set("type")}>
          <option value="">Not decided</option>
          <option value="in_clinic">In-clinic</option>
          <option value="online">Online</option>
        </select>
      </label>
      <div className="row full">
        <button className="btn" type="submit" disabled={busy || !!badPhone}>
          {busy ? "Saving…" : "Save details"}
        </button>
        <button
          className="btn g"
          type="button"
          onClick={onCancel}
          disabled={busy}
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
