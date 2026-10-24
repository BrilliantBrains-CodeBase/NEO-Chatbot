"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError, type LeadDetail, type LeadOptions } from "@/lib/api";

const SOURCES: [string, string][] = [
  ["manual", "Walk-in or call"],
  ["whatsapp", "WhatsApp"],
  ["meta_ads", "Meta Ads"],
  ["google_ads", "Google Ads"],
];

/** The Add lead form (in the pop-up). A number already in the clinic is refused with that lead's code. */
export default function AddLeadForm({ clinicId, onDone }: { clinicId: string; onDone: () => void }) {
  const router = useRouter();
  const { toast } = useCrm();
  const [options, setOptions] = useState<LeadOptions>({ treatments: [], doctors: [] });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<LeadOptions>(`/v1/crm/lead-options?clinic=${clinicId}`).then(setOptions, () => {});
  }, [clinicId]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    setBusy(true);
    setError("");
    try {
      const lead = await api<LeadDetail>("/v1/crm/leads", {
        method: "POST",
        body: JSON.stringify({
          clinic: clinicId,
          name: f.name.trim(),
          phone: f.phone.trim(),
          email: f.email.trim() || null,
          source: f.source,
          campaign: f.campaign.trim() || null,
          treatment: f.treatment || null,
          doctor_id: f.doctor || null,
          type: f.type || null,
          note: f.note.trim(),
        }),
      });
      onDone();
      toast(`Lead ${lead.code} added`);
      router.push(`/leads?open=${lead.code}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the lead. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="fg" onSubmit={submit}>
      {error && (
        <div className="warnbox full" role="alert">
          {error}
        </div>
      )}
      <label>
        Full name
        <input className="f" name="name" required minLength={2} maxLength={100} autoFocus />
      </label>
      <label>
        Mobile number
        <input className="f" name="phone" required inputMode="tel" placeholder="98765 43210" maxLength={15} />
      </label>
      <label>
        Email (optional)
        <input className="f" name="email" type="email" maxLength={200} />
      </label>
      <label>
        Source
        <select className="f" name="source" defaultValue="manual">
          {SOURCES.map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </label>
      <label>
        Treatment
        <select className="f" name="treatment" defaultValue="">
          <option value="">Not decided</option>
          {options.treatments.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
      </label>
      <label>
        Doctor
        <select className="f" name="doctor" defaultValue="">
          <option value="">Any doctor</option>
          {options.doctors.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Visit type
        <select className="f" name="type" defaultValue="">
          <option value="">Not decided</option>
          <option value="in_clinic">In-clinic</option>
          <option value="online">Online</option>
        </select>
      </label>
      <label>
        Campaign (optional)
        <input className="f" name="campaign" maxLength={100} />
      </label>
      <label className="full">
        Note (optional)
        <textarea className="f" name="note" rows={2} maxLength={2000} />
      </label>
      <div className="full" style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button type="button" className="btn" style={{ background: "#fff", color: "var(--ink)", border: "1px solid var(--line)" }} onClick={onDone}>
          Cancel
        </button>
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Adding…" : "Add lead"}
        </button>
      </div>
    </form>
  );
}
