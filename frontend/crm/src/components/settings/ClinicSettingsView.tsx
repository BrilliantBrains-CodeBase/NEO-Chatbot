"use client";

import DataImg from "@/components/crm/DataImg";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import Loading from "@/components/crm/Loading";
import PhoneField, { phoneError, phoneValue } from "@/components/crm/PhoneField";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError, type Branding, type Me } from "@/lib/api";
import { fitImage, ImageError, type Fit } from "@/lib/image";

// Clinic settings: the chosen clinic's own record for the CRM (backend: app/api/v1/crm_settings.py). Its look
// in the CRM (logo, favicon), its details, how new leads are assigned and who is emailed on an emergency.
// The chatbot keeps its own contact details (Dashboard → Clinic info): nothing here changes what patients see.
// Each person's own bell choices are on My profile.

type Assign = "inbox" | "round_robin" | "manager";
type Stored = Record<string, string | null>;
type Alerts = { emergency_admins: boolean; emergency_emails: string[] };
type Settings = { id: string; details: Stored; alerts: Alerts; can_edit: boolean };

const FIELDS = [
  "name", "email", "phone", "alt_phone", "whatsapp", "website", "address", "city", "state", "postal_code",
  "country", "registration_no", "gstin",
] as const;
type Form = Record<(typeof FIELDS)[number], string> & { lead_assignment: Assign };

const TABS = [
  ["general", "General"],
  ["contact", "Contact"],
  ["notifications", "Notifications"],
] as const;
type Tab = (typeof TABS)[number][0];

const ASSIGN: [Assign, string, string][] = [
  [
    "inbox",
    "Assign from the Inbox (recommended)",
    "New leads wait in the Inbox. Front Desk takes them, or an Admin assigns them; they then move to Leads.",
  ],
  ["round_robin", "Share among Front Desk", "Each new lead goes straight to the next Front Desk member who takes part in lead sharing (Team), skipping the Inbox."],
  ["manager", "Give to the Admin", "Every new lead goes straight to the clinic's first Admin, skipping the Inbox."],
];

const LOGO: Fit = { width: 480, height: 160, type: "image/png" };
const FAVICON: Fit = { width: 64, height: 64, square: true, type: "image/png" };
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;

function toForm(d: Stored): Form {
  const f = Object.fromEntries(FIELDS.map((k) => [k, d[k] ?? ""])) as Form;
  f.country ||= "India";
  // "manual" is the old name of the Inbox setting.
  const saved = d.lead_assignment === "manual" ? "inbox" : (d.lead_assignment as Assign);
  f.lead_assignment = saved || "inbox";
  return f;
}

/** What to send: blanks as null, phones without a number as null, a website with https://. */
function toSave(f: Form): Record<string, string | null> {
  const out: Record<string, string | null> = { lead_assignment: f.lead_assignment };
  for (const k of FIELDS) out[k] = f[k].trim() || null;
  for (const k of ["phone", "alt_phone", "whatsapp"] as const) out[k] = phoneValue(f[k]);
  const site = out.website;
  if (site && !/^https?:\/\//i.test(site)) out.website = `https://${site}`;
  else if (site) out.website = site.replace(/^http:\/\//i, "https://");
  if (out.gstin) out.gstin = out.gstin.replace(/\s/g, "").toUpperCase();
  return out;
}

function check(f: Form): string {
  if (f.name.trim().length < 2) return "Please enter the clinic's name.";
  if (f.email.trim() && !EMAIL.test(f.email.trim())) return "Please enter a valid clinic email.";
  for (const [k, label] of [["phone", "Main phone"], ["alt_phone", "Other phone"], ["whatsapp", "WhatsApp"]] as const) {
    const e = phoneError(f[k]);
    if (e) return `${label}: ${e}`;
  }
  if (f.postal_code.trim() && !/^[A-Za-z0-9][A-Za-z0-9 -]{1,9}$/.test(f.postal_code.trim()))
    return "Please check the PIN / postal code.";
  const gst = f.gstin.replace(/\s/g, "").toUpperCase();
  if (gst && !/^[0-9]{2}[A-Z0-9]{13}$/.test(gst)) return "A GSTIN has 15 letters and numbers, starting with 2 numbers.";
  return "";
}

const message = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export default function ClinicSettingsView() {
  const { clinicId, toast, setMe, setClinic, branding, setBranding } = useCrm();
  const [loaded, setLoaded] = useState<{ clinic: string; s?: Settings; error?: string }>({ clinic: "" });
  const [form, setForm] = useState<Form | null>(null);
  const [alerts, setAlerts] = useState<Alerts | null>(null);
  const [tab, setTab] = useState<Tab>("general");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Settings>(`/v1/crm/clinic-settings/${clinicId}`).then(
      (s) => {
        if (!live) return;
        setLoaded({ clinic: clinicId, s });
        setForm(toForm(s.details));
        setAlerts(s.alerts);
        setError("");
      },
      (e) => live && setLoaded({ clinic: clinicId, error: message(e, "Could not load the clinic settings.") }),
    );
    return () => {
      live = false;
    };
  }, [clinicId]);

  const s = loaded.clinic === clinicId ? loaded.s : undefined;
  const dirty =
    !!s &&
    !!form &&
    !!alerts &&
    (JSON.stringify(form) !== JSON.stringify(toForm(s.details)) || JSON.stringify(alerts) !== JSON.stringify(s.alerts));

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  if (loaded.clinic === clinicId && loaded.error) return <div className="warnbox">{loaded.error}</div>;
  if (!s || !form || !alerts || !clinicId) return <Loading label="Loading the clinic settings" />;

  const ro = !s.can_edit;
  const set = (patch: Partial<Form>) => setForm({ ...form, ...patch });

  async function save() {
    if (!s || !form || !alerts || !clinicId) return;
    const problem = check(form);
    if (problem) return setError(problem);
    setBusy(true);
    setError("");
    try {
      const next = await api<Settings>(`/v1/crm/clinic-settings/${clinicId}`, {
        method: "PUT",
        body: JSON.stringify({ details: toSave(form), alerts }),
      });
      setLoaded({ clinic: clinicId, s: next });
      setForm(toForm(next.details));
      setAlerts(next.alerts);
      // A new name shows in the clinic switch and the browser tab at once.
      if (next.details.name !== s.details.name) {
        setMe(await api<Me>("/v1/crm/me"));
        setClinic(next.details.name ?? "");
      }
      toast("Clinic settings saved");
    } catch (e) {
      setError(message(e, "Could not save. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  const field = (key: (typeof FIELDS)[number], label: string, extra: { full?: boolean; hint?: string; placeholder?: string; max?: number; type?: string } = {}) => (
    <label className={`tm-field${extra.full ? " full" : ""}`}>
      {label}
      <input
        className="f"
        type={extra.type ?? "text"}
        maxLength={extra.max ?? 100}
        placeholder={extra.placeholder}
        disabled={ro}
        value={form[key]}
        onChange={(e) => set({ [key]: e.target.value })}
      />
      {extra.hint && <span className="tm-hint">{extra.hint}</span>}
    </label>
  );
  const phone = (key: "phone" | "alt_phone" | "whatsapp", label: string, hint?: string) => (
    <div className="tm-field">
      {label}
      <PhoneField label={label} value={form[key]} disabled={ro} onChange={(v) => set({ [key]: v })} />
      {hint && <span className="tm-hint">{hint}</span>}
    </div>
  );

  return (
    <div className="st">
      <div className="ph">
        <div>
          <h1>Clinic settings</h1>
          <p>
            {s.details.name} · clinic code {s.id}. How this clinic looks and works in the CRM.
          </p>
        </div>
      </div>
      {ro && (
        <div className="warnbox" style={{ marginBottom: 12 }}>
          You can see these settings, but only your admin can change them.
        </div>
      )}

      <div className="tabs" role="tablist" aria-label="Clinic settings">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "on" : ""} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "general" && (
        <>
          <Card title="Logo and favicon" text="Shown in the CRM while this clinic is chosen: the logo at the top of the menu, the favicon in the browser tab and the narrow menu. The chatbot's own logo is in Dashboard → Appearance.">
            <BrandingEditor clinicId={clinicId} branding={branding} readOnly={ro} onSaved={setBranding} />
          </Card>
          <Card title="Clinic" text="The clinic's name in the CRM: the clinic switch, emails to staff and the browser tab.">
            <div className="tm-form">
              {field("name", "Clinic name", { full: true })}
              {field("registration_no", "Registration number", { hint: "Optional. e.g. the clinical establishment number.", max: 60 })}
              {field("gstin", "GSTIN", { hint: "Optional. 15 letters and numbers.", max: 15, placeholder: "29ABCDE1234F1Z5" })}
            </div>
          </Card>
          <Card title="New leads" text="Who a new lead from the chatbot, a form, a sheet or a webhook is given to.">
            <div className="fg" role="radiogroup" aria-label="New leads">
              <div className="fld" style={{ gap: 10 }}>
                {ASSIGN.map(([key, label, hint]) => (
                  <label key={key} className="opt" style={{ alignItems: "flex-start" }}>
                    <input
                      type="radio"
                      name="lead_assignment"
                      checked={form.lead_assignment === key}
                      disabled={ro}
                      onChange={() => set({ lead_assignment: key })}
                      style={{ marginTop: 2 }}
                    />
                    <span>
                      <b style={{ fontWeight: 600 }}>{label}</b>
                      <span className="sub2" style={{ display: "block" }}>{hint}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          </Card>
        </>
      )}

      {tab === "contact" && (
        <Card title="Contact details" text="The clinic's official details for staff. What the chatbot tells patients is set separately in Dashboard → Clinic info.">
          <div className="tm-form">
            {field("email", "Clinic email", { type: "email", max: 120, placeholder: "hello@clinic.com" })}
            {field("website", "Website", { max: 200, placeholder: "https://clinic.com" })}
            {phone("phone", "Main phone")}
            {phone("alt_phone", "Other phone", "Optional. e.g. a landline or front desk number.")}
            {phone("whatsapp", "WhatsApp")}
            <span />
            <label className="tm-field full">
              Address
              <textarea
                className="f"
                rows={2}
                maxLength={300}
                disabled={ro}
                placeholder="Floor, building, street, area"
                value={form.address}
                onChange={(e) => set({ address: e.target.value })}
              />
            </label>
            {field("city", "City", { max: 60 })}
            {field("state", "State", { max: 60 })}
            {field("postal_code", "PIN / postal code", { max: 10 })}
            {field("country", "Country", { max: 60 })}
          </div>
        </Card>
      )}

      {tab === "notifications" && (
        <>
          <Card title="Emergency emails" text="When a patient uses emergency words in the chatbot, these people are emailed at once. The email names the lead, never what the patient wrote.">
            <div className="fg">
              <label className="opt">
                <input
                  type="checkbox"
                  checked={alerts.emergency_admins}
                  disabled={ro}
                  onChange={(e) => setAlerts({ ...alerts, emergency_admins: e.target.checked })}
                />
                Email the clinic&apos;s Admins
              </label>
            </div>
            <EmailList value={alerts.emergency_emails} readOnly={ro} onChange={(emergency_emails) => setAlerts({ ...alerts, emergency_emails })} />
            {!alerts.emergency_admins && alerts.emergency_emails.length === 0 && (
              <div className="warnbox" style={{ marginTop: 12 }}>
                No one will be emailed about emergencies. They still show in the bell.
              </div>
            )}
          </Card>
          <Card title="Your own notifications" text="What shows in each person's bell, sounds and desktop alerts are each person's own choice.">
            <Link className="btn g" href="/profile?tab=notifications">
              Open My profile → Notifications
            </Link>
          </Card>
        </>
      )}

      {error && (
        <div className="warnbox" role="alert" style={{ marginBottom: 12 }}>
          {error}
        </div>
      )}
      {tab !== "general" || dirty ? (
        <div className={`tm-savebar${dirty ? " on" : ""}`}>
          <span>{dirty ? "You have unsaved changes." : ""}</span>
          {dirty && (
            <button
              className="btn g"
              disabled={busy}
              onClick={() => {
                setForm(toForm(s.details));
                setAlerts(s.alerts);
                setError("");
              }}
            >
              Discard
            </button>
          )}
          {!ro && (
            <button className="btn" disabled={busy || !dirty} onClick={() => void save()}>
              {busy ? "Saving…" : "Save changes"}
            </button>
          )}
        </div>
      ) : null}
    </div>
  );
}

function Card({ title, text, children }: { title: string; text: string; children: ReactNode }) {
  return (
    <section className="st-card">
      <h2>{title}</h2>
      <p>{text}</p>
      {children}
    </section>
  );
}

/** Logo and favicon: each saved as soon as it is chosen or removed. */
function BrandingEditor({
  clinicId,
  branding,
  readOnly,
  onSaved,
}: {
  clinicId: string;
  branding: Branding | null;
  readOnly: boolean;
  onSaved: (b: Branding) => void;
}) {
  const { toast } = useCrm();
  const [busy, setBusy] = useState<"logo" | "favicon" | null>(null);
  const [error, setError] = useState("");
  const current = { logo: branding?.logo ?? null, favicon: branding?.favicon ?? null };

  async function put(which: "logo" | "favicon", value: string | null) {
    setBusy(which);
    setError("");
    try {
      const b = await api<Branding>(`/v1/crm/clinic-settings/${clinicId}/branding`, {
        method: "PUT",
        body: JSON.stringify({ ...current, [which]: value }),
      });
      onSaved(b);
      toast(`${which === "logo" ? "Logo" : "Favicon"} ${value ? "saved" : "removed"}`);
    } catch (e) {
      setError(message(e, "Could not save the image. Please try again."));
    } finally {
      setBusy(null);
    }
  }

  async function choose(which: "logo" | "favicon", file: File | undefined) {
    if (!file) return;
    try {
      await put(which, await fitImage(file, which === "logo" ? LOGO : FAVICON));
    } catch (e) {
      setError(e instanceof ImageError ? e.message : "Could not prepare the image.");
    }
  }

  const slot = (which: "logo" | "favicon", label: string, hint: string) => (
    <div className="st-image">
      {label}
      <div className={`st-drop${which === "favicon" ? " sq" : ""}`}>
        {current[which] ? <DataImg src={current[which]} alt={`${label} preview`} /> : <span>No {label.toLowerCase()}</span>}
      </div>
      <span className="tm-hint">{hint}</span>
      {!readOnly && (
        <div className="st-btns">
          <label className="btn g sm" style={{ cursor: "pointer" }} aria-disabled={busy !== null}>
            {busy === which ? "Saving…" : current[which] ? "Replace" : "Upload"}
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/svg+xml,image/x-icon,image/vnd.microsoft.icon"
              hidden
              disabled={busy !== null}
              onChange={(e) => {
                void choose(which, e.target.files?.[0]);
                e.target.value = ""; // the same file can be chosen again
              }}
            />
          </label>
          {current[which] && (
            <button className="btn g sm" disabled={busy !== null} onClick={() => void put(which, null)}>
              Remove
            </button>
          )}
        </div>
      )}
    </div>
  );

  return (
    <>
      <div className="st-images">
        {slot("logo", "Logo", "A wide logo on a clear background works best. PNG, JPG, WebP or SVG; resized to fit 480 × 160.")}
        {slot("favicon", "Favicon", "A square icon. Resized to 64 × 64.")}
      </div>
      {error && (
        <div className="warnbox" role="alert" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}
    </>
  );
}

/** Extra addresses, up to 10. */
function EmailList({ value, readOnly, onChange }: { value: string[]; readOnly: boolean; onChange: (v: string[]) => void }) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const add = () => {
    const e = draft.trim().toLowerCase();
    if (!e) return;
    if (!EMAIL.test(e)) return setError("Please enter a valid email address.");
    if (value.includes(e)) return setError("That address is already in the list.");
    if (value.length >= 10) return setError("Up to 10 addresses.");
    onChange([...value, e]);
    setDraft("");
    setError("");
  };
  return (
    <div className="tm-field" style={{ marginTop: 14 }}>
      Also email these addresses
      {value.length > 0 && (
        <div className="st-chips">
          {value.map((e) => (
            <span key={e}>
              {e}
              {!readOnly && (
                <button aria-label={`Remove ${e}`} onClick={() => onChange(value.filter((x) => x !== e))}>
                  ×
                </button>
              )}
            </span>
          ))}
        </div>
      )}
      {!readOnly && (
        <span className="st-phone">
          <input
            className="f"
            type="email"
            maxLength={120}
            placeholder="frontdesk@clinic.com"
            aria-label="Email address to add"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
          />
          <button className="btn g" type="button" onClick={add}>
            Add
          </button>
        </span>
      )}
      {error ? (
        <span className="tm-hint" role="alert" style={{ color: "var(--err)" }}>
          {error}
        </span>
      ) : (
        <span className="tm-hint">For example a shared front desk inbox. Up to 10.</span>
      )}
    </div>
  );
}
