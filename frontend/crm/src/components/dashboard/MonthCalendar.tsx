"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type DashMonth } from "@/lib/api";

// A month of appointments: each day shows how many (refused, cancelled and moved ones not counted). A day
// opens Appointments on that day.

const WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const pad = (n: number) => String(n).padStart(2, "0");

function shift(month: string, by: number) {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + by, 1);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
}

export default function MonthCalendar({ clinicId, linkDays }: { clinicId: string; linkDays: boolean }) {
  const [month, setMonth] = useState<string | null>(null); // null: this month (the clinic's today)
  const [data, setData] = useState<{ key: string; m?: DashMonth; failed?: boolean }>({ key: "" });
  const key = `${clinicId}-${month}`;

  useEffect(() => {
    let live = true;
    api<DashMonth>(`/v1/crm/dashboard/calendar?clinic=${clinicId}${month ? `&month=${month}` : ""}`).then(
      (m) => live && setData({ key, m }),
      () => live && setData({ key, failed: true }),
    );
    return () => {
      live = false;
    };
  }, [clinicId, month, key]);

  const m = data.m;
  const shown = month ?? m?.month;
  if (!shown) {
    return <section className="card db-cal">{data.failed ? <p className="ch-empty">Could not load the calendar.</p> : <div className="db-cal-ph" />}</section>;
  }
  const [y, mo] = shown.split("-").map(Number);
  const first = new Date(y, mo - 1, 1);
  const lead = (first.getDay() + 6) % 7; // Monday first
  const length = new Date(y, mo, 0).getDate();
  const counts = Object.fromEntries((data.key === key ? m?.days ?? [] : []).map((c) => [c.key, c.count]));
  const today = m?.today ?? "";
  const title = first.toLocaleDateString("en-IN", { month: "long", year: "numeric" });

  return (
    <section className={`card db-cal${data.key !== key ? " db-stale" : ""}`} aria-label={`Appointments in ${title}`}>
      <div className="db-cal-h">
        <h3>{title}</h3>
        <div>
          <button className="ib" aria-label="Previous month" onClick={() => setMonth(shift(shown, -1))}>
            <svg viewBox="0 0 24 24" aria-hidden><path d="m15 18-6-6 6-6" /></svg>
          </button>
          <button className="ib" aria-label="Next month" onClick={() => setMonth(shift(shown, 1))}>
            <svg viewBox="0 0 24 24" aria-hidden><path d="m9 18 6-6-6-6" /></svg>
          </button>
        </div>
      </div>
      <div className="db-cal-g" role="grid">
        {WEEK.map((w) => (
          <span key={w} className="db-cal-w" role="columnheader">
            {w.slice(0, 2)}
          </span>
        ))}
        {Array.from({ length: lead }, (_, i) => (
          <span key={`x${i}`} />
        ))}
        {Array.from({ length }, (_, i) => {
          const day = `${shown}-${pad(i + 1)}`;
          const n = counts[day] ?? 0;
          const cls = `db-day${day === today ? " today" : ""}${n ? " has" : ""}`;
          const label = `${i + 1} ${title}: ${n ? `${n} appointment${n === 1 ? "" : "s"}` : "no appointments"}`;
          const body = (
            <>
              <span>{i + 1}</span>
              {n > 0 && <em>{n}</em>}
            </>
          );
          return linkDays ? (
            <Link key={day} href={`/appointments?day=${day}`} className={cls} aria-label={label}>
              {body}
            </Link>
          ) : (
            <span key={day} className={cls} aria-label={label} role="gridcell">
              {body}
            </span>
          );
        })}
      </div>
      {month && month !== m?.today.slice(0, 7) && (
        <button className="btn g sm db-cal-today" onClick={() => setMonth(null)}>
          Back to this month
        </button>
      )}
    </section>
  );
}
