"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";

// Integrations → Cal.com → Set up online consults: which doctors take online consults through Cal.com, and the
// clinic's holidays. Each doctor's online hours, leave and consult length are set in Dashboard → Doctors and
// shown here read-only; saving sends them to the clinic's Cal.com as one schedule and one event per doctor.

type Hours = { weekday: number; start: string; end: string };
type Leave = { from_date: string; to_date: string; reason: string };
type Doctor = {
  doctor_id: string;
  name: string;
  online: boolean;
  consult_minutes: number;
  hours: Hours[];
  leave: Leave[];
};
type Setup = {
  doctors: Doctor[];
  holidays: { day: string; reason: string }[];
  problems: string[];
};

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const row = {
  display: "flex",
  gap: 6,
  alignItems: "center",
  flexWrap: "wrap" as const,
  marginTop: 4,
};

export default function OnlineSetup({ clinicId }: { clinicId: string }) {
  const { toast } = useCrm();
  const [setup, setSetup] = useState<Setup | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const url = `/v1/crm/console/${clinicId}/integrations/calcom`;

  useEffect(() => {
    let live = true;
    api<Setup>(`${url}/setup`).then(
      (s) => live && setSetup(s),
      (e) =>
        live &&
        setError(
          e instanceof ApiError ? e.message : "Could not load the setup.",
        ),
    );
    return () => {
      live = false;
    };
  }, [url]);

  async function save() {
    if (!setup) return;
    setBusy(true);
    setError("");
    try {
      const s = await api<Setup>(`${url}/setup`, {
        method: "PUT",
        body: JSON.stringify({
          doctors: setup.doctors,
          holidays: setup.holidays,
        }),
      });
      setSetup(s);
      toast(
        s.problems.length
          ? "Saved, with problems from Cal.com"
          : "Saved and sent to Cal.com",
      );
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!setup)
    return error ? (
      <p className="warnbox">{error}</p>
    ) : (
      <p className="sub2">Loading…</p>
    );

  return (
    <div
      style={{
        marginTop: 12,
        borderTop: "1px solid var(--line)",
        paddingTop: 10,
      }}
    >
      <h3 style={{ margin: "0 0 4px" }}>Set up online consults</h3>
      <p className="sub2" style={{ margin: "0 0 8px", fontSize: 12.5 }}>
        Tick the doctors who take online consults. Their online hours, leave and
        consult length come from{" "}
        <Link href="/assistant/doctors">Dashboard → Doctors</Link>; saving here
        sends them to Cal.com (one consult per doctor, with Google Meet).
      </p>
      {setup.doctors.map((d, i) => (
        <div
          key={d.doctor_id}
          className="card"
          style={{ marginBottom: 8, padding: 10 }}
        >
          <label
            style={{
              display: "flex",
              gap: 8,
              alignItems: "center",
              fontWeight: 600,
            }}
          >
            <input
              type="checkbox"
              checked={d.online}
              onChange={(e) =>
                setSetup({
                  ...setup,
                  doctors: setup.doctors.map((x, k) =>
                    k === i ? { ...x, online: e.target.checked } : x,
                  ),
                })
              }
            />
            {d.name}
          </label>
          <p className="sub2" style={{ margin: "4px 0 0", fontSize: 12.5 }}>
            {d.consult_minutes} min consult ·{" "}
            {d.hours.length
              ? d.hours
                  .map((h) => `${DAYS[h.weekday]} ${h.start}–${h.end}`)
                  .join(", ")
              : "No online hours yet"}
            {d.leave.length
              ? ` · Leave: ${d.leave
                  .map((x) =>
                    x.from_date === x.to_date
                      ? x.from_date
                      : `${x.from_date} to ${x.to_date}`,
                  )
                  .join(", ")}`
              : ""}
          </p>
          {d.online && !d.hours.length && (
            <p className="warnbox" style={{ margin: "6px 0 0" }}>
              Add {d.name}&apos;s online hours in Dashboard → Doctors first.
            </p>
          )}
        </div>
      ))}
      <p
        className="sub2"
        style={{ margin: "12px 0 0", fontSize: 12.5, fontWeight: 600 }}
      >
        Clinic holidays (no consults that day)
      </p>
      {setup.holidays.map((h, j) => (
        <div key={j} style={row}>
          <input
            type="date"
            value={h.day}
            onChange={(e) =>
              setSetup({
                ...setup,
                holidays: setup.holidays.map((x, k) =>
                  k === j ? { ...x, day: e.target.value } : x,
                ),
              })
            }
          />
          <input
            placeholder="Reason, e.g. Diwali"
            maxLength={200}
            value={h.reason}
            onChange={(e) =>
              setSetup({
                ...setup,
                holidays: setup.holidays.map((x, k) =>
                  k === j ? { ...x, reason: e.target.value } : x,
                ),
              })
            }
          />
          <button
            aria-label="Remove"
            onClick={() =>
              setSetup({
                ...setup,
                holidays: setup.holidays.filter((_, k) => k !== j),
              })
            }
          >
            ✕
          </button>
        </div>
      ))}
      <button
        className="pill"
        style={{ marginTop: 4 }}
        onClick={() =>
          setSetup({
            ...setup,
            holidays: [
              ...setup.holidays,
              { day: new Date().toISOString().slice(0, 10), reason: "" },
            ],
          })
        }
      >
        + Add holiday
      </button>
      {error && (
        <p className="warnbox" style={{ marginTop: 8 }}>
          {error}
        </p>
      )}
      {setup.problems.map((p) => (
        <p key={p} className="warnbox" style={{ marginTop: 8 }}>
          {p}
        </p>
      ))}
      <div style={{ marginTop: 12 }}>
        <button className="btn" disabled={busy} onClick={() => void save()}>
          {busy ? "Saving and sending to Cal.com…" : "Save and send to Cal.com"}
        </button>
      </div>
    </div>
  );
}
