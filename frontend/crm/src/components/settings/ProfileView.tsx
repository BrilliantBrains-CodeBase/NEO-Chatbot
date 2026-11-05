"use client";

import DataImg from "@/components/crm/DataImg";
import { useSearchParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import BellCard from "@/components/crm/BellCard";
import PasswordCard from "@/components/crm/PasswordCard";
import PhoneField, { phoneError, phoneValue } from "@/components/crm/PhoneField";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError, type Me } from "@/lib/api";
import { fitImage, ImageError } from "@/lib/image";
import { supabase } from "@/lib/supabase";

// My profile: everything about the signed-in person, the same in every clinic. Details (photo, name, phone,
// email), Security (password, other devices), Notifications (their own bell) and Clinics & roles (read only:
// a manager changes roles in Team). The clinic's own settings are in Clinic settings.

const TABS = [
  ["details", "Details"],
  ["security", "Password & security"],
  ["notifications", "Notifications"],
  ["clinics", "Clinics & roles"],
] as const;
type Tab = (typeof TABS)[number][0];

const message = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export default function ProfileView() {
  const { me } = useCrm();
  const asked = useSearchParams().get("tab");
  const [tab, setTab] = useState<Tab>(TABS.some(([k]) => k === asked) ? (asked as Tab) : "details");
  if (!me) return null;

  return (
    <div className="st">
      <div className="ph">
        <div>
          <h1>My profile</h1>
          <p>Your details, sign-in and notifications. They are the same in every clinic.</p>
        </div>
      </div>
      <div className="tabs" role="tablist" aria-label="My profile">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "on" : ""} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      {tab === "details" && (
        <>
          <DetailsCard me={me} />
          <EmailCard me={me} />
        </>
      )}
      {tab === "security" && (
        <>
          <PasswordCard />
          <SessionsCard />
        </>
      )}
      {tab === "notifications" && <BellCard />}
      {tab === "clinics" && <ClinicsCard me={me} />}
    </div>
  );
}

function Card({ title, text, children }: { title: string; text?: string; children: ReactNode }) {
  return (
    <section className="st-card">
      <h2>{title}</h2>
      {text && <p>{text}</p>}
      {!text && <div style={{ height: 12 }} />}
      {children}
    </section>
  );
}

/** Photo, name and phone. The photo is saved as soon as it is chosen. */
function DetailsCard({ me }: { me: Me }) {
  const { setMe, toast } = useCrm();
  const [name, setName] = useState(me.name);
  const [phone, setPhone] = useState(me.phone ?? "");
  const [busy, setBusy] = useState<"save" | "photo" | null>(null);
  const [error, setError] = useState("");
  const dirty = name.trim() !== me.name || (phoneValue(phone) ?? "") !== (me.phone ?? "");

  async function save() {
    if (name.trim().length < 2) return setError("Please enter your name.");
    const bad = phoneError(phone);
    if (bad) return setError(bad);
    setBusy("save");
    setError("");
    try {
      const next = await api<Me>("/v1/crm/me", {
        method: "PATCH",
        body: JSON.stringify({ name: name.trim(), phone: phoneValue(phone) }),
      });
      setMe(next);
      setName(next.name);
      setPhone(next.phone ?? "");
      toast("Profile saved");
    } catch (e) {
      setError(message(e, "Could not save. Please try again."));
    } finally {
      setBusy(null);
    }
  }

  async function photo(value: string | null) {
    setBusy("photo");
    setError("");
    try {
      setMe(await api<Me>("/v1/crm/me/photo", { method: "PUT", body: JSON.stringify({ photo: value }) }));
      toast(value ? "Photo saved" : "Photo removed");
    } catch (e) {
      setError(message(e, "Could not save the photo. Please try again."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card title="Your details" text="Your name shows to your team: on leads you work on, in Team and in notes.">
      <div className="st-who">
        <span className="st-photo" aria-hidden>
          {me.photo ? <DataImg src={me.photo} alt="" /> : me.initials}
        </span>
        <div>
          <b>{me.name}</b>
          <div className="sub2">
            {me.role_label} · {me.email}
          </div>
          <div className="st-btns" style={{ marginTop: 8 }}>
            <label className="btn g sm" style={{ cursor: "pointer" }} aria-disabled={busy !== null}>
              {busy === "photo" ? "Saving…" : me.photo ? "Change photo" : "Upload photo"}
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                hidden
                disabled={busy !== null}
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  try {
                    await photo(await fitImage(file, { width: 160, height: 160, square: true, type: "image/jpeg" }));
                  } catch (err) {
                    setError(err instanceof ImageError ? err.message : "Could not prepare the photo.");
                  }
                }}
              />
            </label>
            {me.photo && (
              <button className="btn g sm" disabled={busy !== null} onClick={() => void photo(null)}>
                Remove
              </button>
            )}
          </div>
        </div>
      </div>
      <div className="tm-form">
        <label className="tm-field">
          Full name
          <input className="f" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <div className="tm-field">
          Phone
          <PhoneField label="Phone" value={phone} onChange={setPhone} />
          <span className="tm-hint">Optional. For your team to reach you.</span>
        </div>
      </div>
      {error && (
        <div className="warnbox" role="alert" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}
      <div className="tm-actions" style={{ marginTop: 14 }}>
        {dirty && (
          <button
            className="btn g"
            disabled={busy !== null}
            onClick={() => {
              setName(me.name);
              setPhone(me.phone ?? "");
              setError("");
            }}
          >
            Cancel
          </button>
        )}
        <button className="btn" disabled={busy !== null || !dirty} onClick={() => void save()}>
          {busy === "save" ? "Saving…" : "Save"}
        </button>
      </div>
    </Card>
  );
}

/** The sign-in email: Supabase Auth emails a confirmation link; the profile follows once it is clicked. */
function EmailCard({ me }: { me: Me }) {
  const [email, setEmail] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState("");

  async function change() {
    const value = email.trim().toLowerCase();
    setBusy(true);
    setError("");
    try {
      await api("/v1/crm/me/email", { method: "POST", body: JSON.stringify({ email: value }) });
      const { error: e } = await supabase().auth.updateUser(
        { email: value },
        { emailRedirectTo: `${window.location.origin}/profile` },
      );
      if (e) throw new ApiError(0, e.message.includes("rate") ? "Too many tries. Please wait a few minutes." : "Could not send the confirmation email. Please try again.");
      setSent(value);
      setOpen(false);
      setEmail("");
    } catch (e) {
      setError(message(e, "Could not change the email. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Sign-in email" text="The address you sign in with, and where the CRM sends your codes and alerts.">
      <div className="row" style={{ gap: 12, justifyContent: "space-between", flexWrap: "wrap" }}>
        <b style={{ fontWeight: 600 }}>{me.email}</b>
        {!open && (
          <button className="btn g sm" onClick={() => setOpen(true)}>
            Change email
          </button>
        )}
      </div>
      {sent && !open && (
        <p className="sub2" style={{ margin: "10px 0 0" }}>
          We sent a confirmation link to {sent}. Your email changes when you click it (Supabase may also ask you to
          confirm from your current address). Until then, keep signing in with {me.email}.
        </p>
      )}
      {open && (
        <div style={{ marginTop: 12 }}>
          <label className="tm-field">
            New email
            <input
              className="f"
              type="email"
              autoFocus
              maxLength={120}
              placeholder="name@clinic.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && email.trim() && void change()}
            />
          </label>
          {error && (
            <div className="warnbox" role="alert" style={{ marginTop: 10 }}>
              {error}
            </div>
          )}
          <div className="tm-actions" style={{ marginTop: 12 }}>
            <button
              className="btn g"
              disabled={busy}
              onClick={() => {
                setOpen(false);
                setError("");
              }}
            >
              Cancel
            </button>
            <button className="btn" disabled={busy || !email.trim()} onClick={() => void change()}>
              {busy ? "Sending…" : "Send confirmation link"}
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}

/** Sign out everywhere else, e.g. after using a shared computer. */
function SessionsCard() {
  const { toast } = useCrm();
  const [busy, setBusy] = useState(false);
  return (
    <Card title="Other devices" text="Signed in on a shared or lost computer? Sign out there. This device stays signed in.">
      <button
        className="btn g"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          const { error } = await supabase().auth.signOut({ scope: "others" });
          setBusy(false);
          toast(error ? "Could not sign out the other devices" : "Signed out on every other device");
        }}
      >
        {busy ? "Signing out…" : "Sign out of other devices"}
      </button>
    </Card>
  );
}

function ClinicsCard({ me }: { me: Me }) {
  return (
    <Card title="Clinics & roles" text="The clinics you can open and your role in each. To change them, ask your admin (Team).">
      <ul className="st-list">
        {me.clinics.map((c) => (
          <li key={c.id}>
            <span>
              <b style={{ fontWeight: 600 }}>{c.name}</b> <span className="sub2">{c.id}</span>
            </span>
            <span>{c.role_label}</span>
          </li>
        ))}
        {me.clinics.length === 0 && <li>None yet</li>}
      </ul>
    </Card>
  );
}
