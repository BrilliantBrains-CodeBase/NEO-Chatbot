"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError, type Appointment, type Appointments } from "@/lib/api";

const STATUS: Record<string, [string, string]> = {
  pending: ["Pending", "b-fu"],
  confirmed: ["Confirmed", "b-bk"],
  visited: ["Visited", "b-vi"],
  no_show: ["No show", "b-lo"],
  missed: ["Missed", "b-lo"],
  cancelled: ["Cancelled", "b-cl"],
  rejected: ["Rejected", "b-cl"],
  rescheduled: ["Moved", "b-cl"],
};
// Colour of a block in the day grid, as in the design.
const tone = (a: Appointment) =>
  a.status === "visited" ? "vis" : ["no_show", "missed"].includes(a.status) ? "ns" : ["cancelled", "rejected", "rescheduled"].includes(a.status) ? "cx" : a.type === "online" ? "onl" : "";

const ymd = (d: Date) => d.toLocaleDateString("en-CA");
const shift = (day: string, n: number) => {
  const d = new Date(day + "T00:00:00");
  d.setDate(d.getDate() + n);
  return ymd(d);
};
const longDay = (day: string) =>
  new Date(day + "T00:00:00").toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
const clock = (t: string) => {
  const [h, m] = t.split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
};
// Rows of the day grid: every 15 minutes from 10:00 to 18:45, widened to fit any appointment outside.
function rows(items: Appointment[]) {
  const mins = items.filter((a) => a.time).map((a) => Number(a.time!.slice(0, 2)) * 60 + Number(a.time!.slice(3)));
  const first = Math.min(600, ...mins);
  const last = Math.max(1125, ...mins);
  const out: string[] = [];
  for (let m = first - (first % 15); m <= last; m += 15) out.push(`${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`);
  return out;
}

// Today in the browser; "" while the server pre-renders (it must not use the current time).
const noSubscription = () => () => {};
const useToday = () => useSyncExternalStore(noSubscription, () => ymd(new Date()), () => "");

export default function AppointmentsView() {
  const { clinic, me } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const today = useToday();
  const [chosen, setDay] = useState(""); // "" = today
  const day = chosen || today;
  const [view, setView] = useState<"doctor" | "list">("doctor");
  const [all, setAll] = useState(false); // also cancelled, rejected and moved ones
  const key = `${clinicId}|${day}|${all}`;
  const [data, setData] = useState<{ key: string; d?: Appointments; error?: string }>({ key: "" });
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    if (!clinicId || !day) return;
    let live = true;
    api<Appointments>(`/v1/crm/appointments?clinic=${clinicId}&from=${day}${all ? "&status=all" : ""}`).then(
      (d) => live && setData({ key, d }),
      (e) => live && setData({ key, error: e instanceof ApiError ? e.message : "Could not load appointments." }),
    );
    return () => {
      live = false;
    };
  }, [clinicId, day, all, key]);

  const d = data.key === key ? data.d : undefined;
  const items = d?.items ?? [];
  const open = items.find((a) => a.id === openId);
  // Columns: the clinic's doctors, plus "No doctor yet" when some appointment has none.
  const columns = [...(d?.doctors ?? []), ...(items.some((a) => !a.doctor_id) ? [{ id: "", name: "No doctor yet" }] : [])];
  const anyTime = items.filter((a) => !a.time);

  return (
    <>
      <div className="ph">
        <div>
          <h1>Appointments</h1>
          <p>
            {day ? longDay(day) : "…"} · {d ? `${items.length} appointment${items.length === 1 ? "" : "s"}` : "…"}
          </p>
        </div>
        <div className="seg">
          <button className={view === "doctor" ? "on" : ""} onClick={() => setView("doctor")}>
            By doctor
          </button>
          <button className={view === "list" ? "on" : ""} onClick={() => setView("list")}>
            List
          </button>
        </div>
      </div>
      <div className="tools">
        <button className="pill" disabled={!day} onClick={() => setDay(shift(day, -1))} aria-label="Previous day">
          ‹
        </button>
        <input className="sel" type="date" aria-label="Day" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} />
        <button className="pill" disabled={!day} onClick={() => setDay(shift(day, 1))} aria-label="Next day">
          ›
        </button>
        <button className={`pill${day === today ? " on" : ""}`} onClick={() => setDay("")}>
          Today
        </button>
        <label className="sub2" style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />
          Show cancelled and moved
        </label>
      </div>
      {data.key === key && data.error && <div className="warnbox">{data.error}</div>}
      {!d && !(data.key === key && data.error) && <p className="sub2">Loading…</p>}

      {d && view === "doctor" && (
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="cday">
            <thead>
              <tr>
                <th>Time</th>
                {columns.map((c) => (
                  <th key={c.id || "none"}>{c.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {!!anyTime.length && (
                <tr>
                  <td className="tm">Any time</td>
                  {columns.map((c) => (
                    <td key={c.id || "none"}>
                      {anyTime
                        .filter((a) => (a.doctor_id ?? "") === c.id)
                        .map((a) => (
                          <Block key={a.id} a={a} onOpen={setOpenId} />
                        ))}
                    </td>
                  ))}
                </tr>
              )}
              {rows(items).map((t) => (
                <tr key={t}>
                  <td className="tm">{clock(t)}</td>
                  {columns.map((c) => (
                    <td key={c.id || "none"}>
                      {items
                        .filter((a) => a.time === t && (a.doctor_id ?? "") === c.id)
                        .map((a) => (
                          <Block key={a.id} a={a} onOpen={setOpenId} />
                        ))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {d && view === "list" && (
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Patient</th>
                <th>Treatment</th>
                <th>Doctor</th>
                <th>Type</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {!items.length && (
                <tr>
                  <td colSpan={6}>No appointments on this day.</td>
                </tr>
              )}
              {items.map((a) => (
                <tr key={a.id} onClick={() => setOpenId(a.id)} style={{ cursor: "pointer" }}>
                  <td>{a.time ? clock(a.time) : "Any time"}</td>
                  <td>
                    <div className="nm">{a.name}</div>
                    <div className="pn">
                      {a.lead_code} · {a.phone ?? a.email}
                    </div>
                  </td>
                  <td>{a.treatment ?? "—"}</td>
                  <td>{a.doctor ?? "—"}</td>
                  <td>{a.type === "online" ? "Online" : "In-clinic"}</td>
                  <td>
                    <span className={`badge ${STATUS[a.status]?.[1]}`}>{STATUS[a.status]?.[0] ?? a.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className={`ov${open ? " on" : ""}`} onClick={() => setOpenId(null)} />
      <aside className={`dr${open ? " on" : ""}`} aria-hidden={!open}>
        {open && (
          <>
            <div className="dh">
              <div>
                <h2>{open.name}</h2>
                <p>
                  <Link className="lnk" href={`/leads?open=${open.lead_code}`}>
                    {open.lead_code}
                  </Link>
                  <span className={`badge ${STATUS[open.status]?.[1]}`}>{STATUS[open.status]?.[0] ?? open.status}</span>
                </p>
              </div>
              <button className="x" onClick={() => setOpenId(null)} aria-label="Close">
                ✕
              </button>
            </div>
            <div className="db">
              <div className="kv">
                {(
                  [
                    ["Date", longDay(open.day)],
                    ["Time", open.time ? clock(open.time) : "Any time"],
                    ["Doctor", open.doctor],
                    ["Type", open.type === "online" ? "Online (Google Meet)" : "In-clinic"],
                    ["Treatment", open.treatment],
                    ["Phone", open.phone],
                    ["Email", open.email],
                    ["Meet link", open.meet_link],
                  ] as [string, string | null][]
                )
                  .filter(([, v]) => v)
                  .map(([k, v]) => (
                    <div key={k} style={k === "Meet link" || k === "Date" ? { gridColumn: "1 / -1" } : undefined}>
                      <span>{k}</span>
                      <b>
                        {k === "Meet link" ? (
                          <a className="lnk" href={v!} target="_blank" rel="noreferrer">
                            {v}
                          </a>
                        ) : (
                          v
                        )}
                      </b>
                    </div>
                  ))}
              </div>
              {open.meet_link && (
                <div className="row">
                  <button className="pill" onClick={() => void navigator.clipboard.writeText(open.meet_link!)}>
                    Copy Meet link
                  </button>
                </div>
              )}
            </div>
          </>
        )}
      </aside>
    </>
  );
}

function Block({ a, onOpen }: { a: Appointment; onOpen: (id: string) => void }) {
  return (
    <div className={`ap ${tone(a)}`} onClick={() => onOpen(a.id)} title={`${a.name} · ${a.treatment ?? ""}`}>
      <b>{a.name}</b>
      <span>
        {a.type === "online" ? "Online" : "In-clinic"}
        {a.treatment ? ` · ${a.treatment}` : ""}
      </span>
    </div>
  );
}
