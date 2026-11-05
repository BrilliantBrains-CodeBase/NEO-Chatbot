"use client";

import { useState } from "react";
import { NOTE_KINDS, type NotePrefs } from "@/lib/notifications";
import { useCrm } from "./CrmProvider";

// My profile → Notifications: saved for this person, the same on every computer and in every clinic.
export default function BellCard() {
  const { prefs, savePrefs } = useCrm();
  const [blocked, setBlocked] = useState(false);
  const off = prefs.off_kinds;

  const change = (next: Partial<NotePrefs>) => void savePrefs({ ...prefs, ...next });

  async function setDesktop(on: boolean) {
    if (!on) return change({ desktop: false });
    if (!("Notification" in window)) return setBlocked(true);
    const answer = await window.Notification.requestPermission();
    setBlocked(answer !== "granted");
    if (answer === "granted") change({ desktop: true });
  }

  return (
    <section className="st-card">
      <h2>Bell notifications</h2>
      <p>
        Choose what shows in your bell. The Inbox still shows every request, and emergencies always show. Who is
        emailed for the whole clinic is in Clinic settings.
      </p>
      <div style={{ display: "grid", gap: 8 }}>
        {NOTE_KINDS.map((t) => (
          <label key={t.id} className="row" style={{ gap: 8, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={!off.includes(t.id)}
              onChange={(e) =>
                change({
                  off_kinds: e.target.checked ? off.filter((x) => x !== t.id) : [...off, t.id],
                })
              }
            />
            {t.label}
          </label>
        ))}
      </div>
      <b style={{ display: "block", marginTop: 16 }}>Alerts</b>
      <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
        <label className="row" style={{ gap: 8, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={prefs.sound}
            onChange={(e) => change({ sound: e.target.checked })}
          />
          Play a sound when something new arrives
        </label>
        <label className="row" style={{ gap: 8, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={prefs.desktop}
            onChange={(e) => void setDesktop(e.target.checked)}
          />
          Desktop alerts (they never show patient names)
        </label>
        {blocked && (
          <p className="sub2" style={{ margin: 0 }}>
            This browser has blocked desktop alerts. Allow them in the browser&apos;s site settings, then tick this again.
          </p>
        )}
      </div>
    </section>
  );
}
