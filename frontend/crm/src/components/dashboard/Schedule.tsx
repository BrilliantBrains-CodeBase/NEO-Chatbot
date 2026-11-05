"use client";

import Link from "next/link";
import type { TodayAppt } from "@/lib/api";

// Today's appointments as a timeline, one colour per doctor (named in the key above it, so colour is never the
// only way to tell). "Any time" bookings come last.

const SLOTS = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s7)", "var(--s5)", "var(--s6)", "var(--s4)", "var(--s8)"];
const STATUS: Record<string, [string, string]> = {
  pending: ["Pending", "b-fu"],
  confirmed: ["Confirmed", "b-bk"],
  visited: ["Visited", "b-vi"],
};

function hour(t: string) {
  const h = Number(t.slice(0, 2));
  return `${h % 12 || 12} ${h < 12 ? "AM" : "PM"}`;
}

export default function Schedule({ today, link }: { today: TodayAppt[]; link: boolean }) {
  // The colour follows the doctor (sorted by id, so it does not move as the list changes during the day).
  const doctors = [...new Map(today.filter((a) => a.doctor_id).map((a) => [a.doctor_id!, a.doctor ?? "Doctor"])).entries()].sort(([a], [b]) => a.localeCompare(b));
  const color = (id: string | null) => {
    const i = doctors.findIndex(([d]) => d === id);
    return i >= 0 && i < SLOTS.length ? SLOTS[i] : "var(--idle)";
  };
  const groups: [string, TodayAppt[]][] = [];
  for (const a of today) {
    const g = a.time ? hour(a.time) : "Any time";
    const last = groups[groups.length - 1];
    if (last && last[0] === g) last[1].push(a);
    else groups.push([g, [a]]);
  }

  return (
    <section className="card db-sched" aria-label="Today's schedule">
      <h3>
        Today <small>{today.length ? `${today.length} appointment${today.length === 1 ? "" : "s"}` : ""}</small>
      </h3>
      {doctors.length > 1 && (
        <div className="ch-keys">
          {doctors.map(([id, name]) => (
            <span key={id}>
              <i style={{ background: color(id) }} />
              {name}
            </span>
          ))}
        </div>
      )}
      {today.length === 0 && <p className="ch-empty">No appointments today.</p>}
      <ol className="db-tl">
        {groups.map(([g, items]) => (
          <li key={g}>
            <span className="db-tl-h">{g}</span>
            <div className="db-tl-items">
              {items.map((a) => {
                const [word, badge] = STATUS[a.status] ?? [a.status, "b-cl"];
                const inner = (
                  <>
                    <div className="db-tl-t">
                      <b>{a.patient}</b>
                      <span className={`badge ${badge}`}>{word}</span>
                    </div>
                    <span className="db-tl-s">
                      {[a.time ? `${a.time}${a.end ? `–${a.end}` : ""}` : null, a.treatment, a.doctor, a.type === "online" ? "Online" : null]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </>
                );
                const style = { borderLeftColor: color(a.doctor_id) };
                return link ? (
                  <Link key={a.lead_code + a.time} href={`/leads?open=${a.lead_code}`} className="db-tl-i" style={style}>
                    {inner}
                  </Link>
                ) : (
                  <div key={a.lead_code + a.time} className="db-tl-i" style={style}>
                    {inner}
                  </div>
                );
              })}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
