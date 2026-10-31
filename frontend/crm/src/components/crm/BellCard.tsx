"use client";

import { BELL_TYPES, setBellOff, useBellOff } from "@/lib/bell";

// Settings → Bell notifications: tick the request types to see in the bell (saved in this browser).
export default function BellCard() {
  const off = useBellOff();

  return (
    <div className="card" style={{ padding: 16, maxWidth: 640, marginTop: 16 }}>
      <b>Bell notifications</b>
      <p className="sub2" style={{ margin: "4px 0 12px" }}>
        Choose what shows in the bell. The Inbox still shows every request.
        Saved in this browser.
      </p>
      <div style={{ display: "grid", gap: 8 }}>
        {BELL_TYPES.map((t) => (
          <label
            key={t.id}
            className="row"
            style={{ gap: 8, cursor: "pointer" }}
          >
            <input
              type="checkbox"
              checked={!off.includes(t.id)}
              onChange={(e) =>
                setBellOff(
                  e.target.checked
                    ? off.filter((x) => x !== t.id)
                    : [...off, t.id],
                )
              }
            />
            {t.label}
          </label>
        ))}
      </div>
    </div>
  );
}
