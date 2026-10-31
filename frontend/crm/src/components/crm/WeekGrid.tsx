"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { type Booking, type Day, type Week, spans } from "@/lib/availability";

// CRM → Doctors Availability → one doctor: their week as a grid (the design's .wkg). Rows step by the doctor's
// smaller slot length (in-clinic or online), so every booking and free time lands on a row.

const DAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MON = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

const mins = (hm: string) =>
  Number(hm.slice(0, 2)) * 60 + Number(hm.slice(3, 5));
const hm = (m: number) =>
  `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const label = (m: number) => {
  const h = Math.floor(m / 60);
  return `${((h + 11) % 12) + 1}:${String(m % 60).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
};
const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};
const head = (iso: string) => {
  const d = new Date(`${iso}T00:00:00Z`);
  return {
    day: DAY[d.getUTCDay()],
    date: `${d.getUTCDate()} ${MON[d.getUTCMonth()]}`,
  };
};
const within = (s: { start: string; end: string }[], m: number) =>
  s.some((x) => mins(x.start) <= m && m < mins(x.end));

export type Kind = "all" | "in_clinic" | "online";

/** The cell at minute m of a day, for the kinds of visit shown: its class and text. */
function cell(
  day: Day,
  m: number,
  past: boolean,
  kind: Kind,
): { cls: string; text: string; sub?: string; title?: string } {
  const b: Booking | undefined = day.bookings.find(
    (x) => x.start && x.end && mins(x.start) <= m && m < mins(x.end),
  );
  if (b && kind !== "all" && b.type !== kind) {
    // The other kind of visit still takes the doctor's time.
    const other = b.type === "online" ? "Online consult" : "In-clinic visit";
    return {
      cls: "blocked",
      text: "",
      title: `${other} booked: ${b.patient} (${b.start}–${b.end})`,
    };
  }
  if (b) {
    const first = mins(b.start!) === m;
    const kind = b.type === "online" ? "Online" : "In-clinic";
    const title = `${b.patient} (${b.lead_code}) · ${kind} ${b.start}–${b.end} · ${b.status}`;
    if (b.status === "pending")
      return {
        cls: "c pending",
        text: first ? b.patient : "",
        sub: first ? `Pending · ${kind}` : "",
        title,
      };
    return {
      cls: `c booked${b.type === "online" ? " onl" : ""}`,
      text: first ? b.patient : "",
      sub: first
        ? `${kind}${b.status === "confirmed" ? "" : ` · ${b.status.replace("_", "-")}`}`
        : "",
      title,
    };
  }
  if (past) return { cls: "past", text: "" };
  const t = hm(m);
  const fi = kind !== "online" && day.free_in_clinic.includes(t);
  const fo = kind !== "in_clinic" && day.free_online.includes(t);
  if (fi || fo) {
    const text = fi && fo ? "Free" : fi ? "Free · in-clinic" : "Free · online";
    return { cls: "c free", text, title: `${text} at ${t}` };
  }
  const works =
    (kind !== "online" && !day.closed && within(day.in_clinic, m)) ||
    (kind !== "in_clinic" && within(day.online, m));
  return works
    ? {
        cls: "blocked",
        text: "",
        title: "Not offered (held, or too close to a booking)",
      }
    : { cls: "", text: "" };
}

export default function WeekGrid({
  clinicId,
  doctorId,
}: {
  clinicId: string;
  doctorId: string;
}) {
  const [start, setStart] = useState<string | null>(null); // null = from today
  const [kind, setKind] = useState<Kind>("all");
  const [week, setWeek] = useState<{ key: string; data: Week }>();
  const [error, setError] = useState("");
  const key = `${clinicId}|${doctorId}|${start ?? ""}`;

  useEffect(() => {
    let live = true;
    api<Week>(
      `/v1/crm/availability/${doctorId}?clinic=${clinicId}${start ? `&start=${start}` : ""}`,
    ).then(
      (data) => live && setWeek({ key, data }),
      (e) =>
        live &&
        setError(
          e instanceof ApiError ? e.message : "Could not load the week.",
        ),
    );
    return () => {
      live = false;
    };
  }, [clinicId, doctorId, start, key]);

  const w = week?.key === key ? week.data : undefined;
  const header = (
    <div className="ph">
      <div>
        <h1>{w?.doctor.name ?? "Doctor"}</h1>
        <p>
          {w
            ? `${w.doctor.role_title} · Slots: in-clinic ${w.doctor.in_clinic_minutes} min, online ${w.doctor.online_minutes} min`
            : "Week schedule, leave and slot settings"}
        </p>
      </div>
    </div>
  );
  if (!w)
    return (
      <>
        {header}
        {error ? (
          <p className="warnbox">{error}</p>
        ) : (
          <p className="sub2">Loading…</p>
        )}
      </>
    );

  // Rows: the clinic's hours and every hour the doctor works this week, stepping by the smaller length.
  const step =
    kind === "in_clinic"
      ? w.doctor.in_clinic_minutes
      : kind === "online"
        ? w.doctor.online_minutes
        : Math.min(w.doctor.in_clinic_minutes, w.doctor.online_minutes);
  const all = w.days.flatMap((d) => [
    ...(kind !== "online" ? d.in_clinic : []),
    ...(kind !== "in_clinic" ? d.online : []),
  ]);
  const from = Math.min(mins(w.open_time), ...all.map((s) => mins(s.start)));
  const to = Math.max(mins(w.close_time), ...all.map((s) => mins(s.end)));
  const rows: number[] = [];
  for (let m = from - (from % step); m < to; m += step) rows.push(m);
  const now = new Date();
  const nowMin = now.getHours() * 60 + now.getMinutes();

  return (
    <>
      {header}
      <div
        className="row"
        style={{ gap: 8, marginBottom: 10, flexWrap: "wrap" }}
      >
        <Link className="btn g" href="/doctors">
          ← All doctors
        </Link>
        <button
          className="btn g"
          onClick={() => setStart(addDays(w.days[0].date, -7))}
        >
          ← Previous week
        </button>
        <button
          className="btn g"
          disabled={w.days[0].date === w.today}
          onClick={() => setStart(null)}
        >
          This week
        </button>
        <button
          className="btn g"
          onClick={() => setStart(addDays(w.days[0].date, 7))}
        >
          Next week →
        </button>
        <input
          className="sel"
          type="date"
          aria-label="Show the week from"
          title="Show the 7 days from this date"
          value={w.days[0].date}
          onChange={(e) =>
            e.target.value &&
            setStart(e.target.value === w.today ? null : e.target.value)
          }
        />
        <select
          className="sel"
          aria-label="Kind of visit"
          value={kind}
          onChange={(e) => setKind(e.target.value as Kind)}
        >
          <option value="all">In-clinic and online</option>
          <option value="in_clinic">In-clinic only</option>
          <option value="online">Online only</option>
        </select>
        <div className="lgd">
          <span>
            <i style={{ background: "#F3FBF6", border: "1px solid #BFE3CC" }} />
            Free
          </span>
          <span>
            <i style={{ background: "#F1EDFB" }} />
            Booked in-clinic
          </span>
          <span>
            <i style={{ background: "#E6F3FF" }} />
            Booked online
          </span>
          <span>
            <i style={{ background: "var(--warnt)" }} />
            Pending
          </span>
          <span>
            <i style={{ background: "var(--errt)" }} />
            Leave
          </span>
          <span>
            <i style={{ background: "#F5F6F8" }} />
            Closed / blocked
          </span>
        </div>
      </div>
      <div className="tw">
        <table className="wkg">
          <thead>
            <tr>
              <th />
              {w.days.map((d) => {
                const h = head(d.date);
                const any = d.bookings.filter((b) => !b.start);
                const hours = [
                  !d.closed && d.in_clinic.length
                    ? `In-clinic ${spans(d.in_clinic)}`
                    : "",
                  d.online.length ? `Online ${spans(d.online)}` : "",
                ].filter(Boolean);
                return (
                  <th
                    key={d.date}
                    className={d.date === w.today ? "today" : ""}
                    title={hours.join(" · ")}
                  >
                    {h.day}
                    <br />
                    <span>{h.date}</span>
                    {any.length > 0 && (
                      <span
                        style={{ display: "block", fontSize: 11 }}
                        title={any.map((b) => b.patient).join(", ")}
                      >
                        {any.length} any-time request
                        {any.length === 1 ? "" : "s"}
                      </span>
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((m, i) => (
              <tr key={m}>
                <td className="tm">{label(m)}</td>
                {w.days.map((d) => {
                  const whole =
                    d.holiday !== null
                      ? {
                          cls: "cl",
                          text: "Holiday",
                          title: d.holiday || "Clinic holiday",
                        }
                      : d.leave !== null
                        ? {
                            cls: "lv",
                            text: "Leave",
                            title: d.leave || "On leave",
                          }
                        : kind === "online"
                          ? !d.online.length
                            ? {
                                cls: "cl",
                                text: "No online hours",
                                title: "No online hours this day",
                              }
                            : null
                          : d.closed &&
                              (kind === "in_clinic" || !d.online.length)
                            ? {
                                cls: "cl",
                                text: "Closed",
                                title: "Clinic closed",
                              }
                            : null;
                  if (whole)
                    return i === 0 ? (
                      <td
                        key={d.date}
                        className={whole.cls}
                        rowSpan={rows.length}
                        title={whole.title}
                      >
                        {whole.text}
                      </td>
                    ) : null;
                  const past =
                    d.date < w.today ||
                    (d.date === w.today && m + step <= nowMin);
                  const c = cell(d, m, past, kind);
                  return (
                    <td key={d.date} className={c.cls} title={c.title}>
                      {c.text && <b>{c.text}</b>}
                      {c.sub && <span>{c.sub}</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="sub2" style={{ marginTop: 8 }}>
        Free times are what the chatbot offers patients now. A time booked
        in-clinic or online is taken for both.
      </p>
    </>
  );
}
