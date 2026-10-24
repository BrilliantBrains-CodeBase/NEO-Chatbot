"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Slots = {
  doctors: { id: string; name: string }[];
  days: Record<string, string[]>;
};
export type Pick = { doctorId: string; date: string; time: string };

const label = (d: string) =>
  new Date(d + "T00:00:00").toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
const clock = (t: string) => {
  const [h, m] = t.split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
};

/** Choose a doctor, then one of their free days, then a free time (in-clinic and online share one diary). */
export default function SlotPicker({
  clinicId,
  mode,
  doctorId,
  value,
  onChange,
}: {
  clinicId: string;
  mode: string;
  doctorId: string | null;
  value: Pick | null;
  onChange: (p: Pick | null) => void;
}) {
  const [doctor, setDoctor] = useState(doctorId ?? "");
  const [day, setDay] = useState("");
  const key = `${clinicId}|${mode}|${doctor}`;
  const [data, setData] = useState<{ key: string; d?: Slots; error?: string }>({
    key: "",
  });

  useEffect(() => {
    let live = true;
    const q = new URLSearchParams({ clinic: clinicId, mode });
    if (doctor) q.set("doctor_id", doctor);
    api<Slots>(`/v1/crm/slots?${q}`).then(
      (d) => live && setData({ key, d }),
      () => live && setData({ key, error: "Could not load the free times." }),
    );
    return () => {
      live = false;
    };
  }, [clinicId, mode, doctor, key]);

  const d = data.key === key ? data.d : undefined;
  const days = Object.keys(d?.days ?? {}).sort();
  // One step at a time: the days until one is chosen, then only that day and its free times.
  const shownDay = day && d?.days[day] ? day : "";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 8,
        marginBottom: 8,
      }}
    >
      <select
        className="f"
        aria-label="Doctor"
        value={doctor}
        onChange={(e) => {
          setDoctor(e.target.value);
          setDay("");
          onChange(null);
        }}
      >
        <option value="">Any free doctor</option>
        {d?.doctors.map((x) => (
          <option key={x.id} value={x.id}>
            {x.name}
          </option>
        ))}
      </select>
      {data.key === key && data.error && (
        <div className="warnbox">{data.error}</div>
      )}
      {!d && !data.error && <p className="sub2">Loading free times…</p>}
      {d && !days.length && (
        <p className="sub2">No free times in the next 2 weeks.</p>
      )}
      {!!days.length && (
        <>
          <div className="row" aria-label="Free days">
            {shownDay && (
              <>
                <button type="button" className="pill on">
                  {label(shownDay)}
                </button>
                <button
                  type="button"
                  className="lnk"
                  style={{ border: 0, background: "none", cursor: "pointer" }}
                  onClick={() => {
                    setDay("");
                    onChange(null);
                  }}
                >
                  Change date
                </button>
              </>
            )}
            {!shownDay &&
              days.map((x) => (
                <button
                  key={x}
                  type="button"
                  className={`pill${x === shownDay ? " on" : ""}`}
                  onClick={() => setDay(x)}
                >
                  {label(x)}
                  <span className="c">{d?.days[x].length}</span>
                </button>
              ))}
          </div>
          {!shownDay && (
            <p className="sub2" style={{ margin: 0 }}>
              Choose a day to see its free times.
            </p>
          )}
          <div className="row" aria-label="Free times">
            {(d?.days[shownDay] ?? []).map((t) => {
              const on = value?.date === shownDay && value.time === t;
              return (
                <button
                  key={t}
                  type="button"
                  className={`pill${on ? " on" : ""}`}
                  onClick={() =>
                    onChange(
                      on ? null : { doctorId: doctor, date: shownDay, time: t },
                    )
                  }
                >
                  {clock(t)}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
