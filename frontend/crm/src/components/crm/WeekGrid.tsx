"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { level } from "@/lib/access";
import {
  api,
  ApiError,
  type LeadList,
  type LeadOptions,
  type LeadRow,
} from "@/lib/api";
import { COUNTRY_CODES } from "@/lib/countries";
import { type Booking, type Day, type Week, spans } from "@/lib/availability";
import { useCrm } from "./CrmProvider";
import {
  HoursEditor,
  LeaveEditor,
  overlap,
  type Hours,
  type Leave,
} from "./ScheduleEditors";

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
): {
  cls: string;
  text: string;
  sub?: string;
  title?: string;
  free?: Kind[]; // the kinds of visit free at this time (a click books one)
  booking?: Booking; // the booking here (a click shows its details)
} {
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
        booking: b,
      };
    return {
      cls: `c booked${b.type === "online" ? " onl" : ""}`,
      text: first ? b.patient : "",
      sub: first
        ? `${kind}${b.status === "confirmed" ? "" : ` · ${b.status.replace("_", "-")}`}`
        : "",
      title,
      booking: b,
    };
  }
  if (past) return { cls: "past", text: "" };
  const t = hm(m);
  const fi = kind !== "online" && day.free_in_clinic.includes(t);
  const fo = kind !== "in_clinic" && day.free_online.includes(t);
  if (fi || fo) {
    const text = fi && fo ? "Free" : fi ? "Free · in-clinic" : "Free · online";
    const free: Kind[] = [
      ...(fi ? (["in_clinic"] as const) : []),
      ...(fo ? (["online"] as const) : []),
    ];
    return { cls: "c free", text, title: `${text} at ${t}`, free };
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
  const { me, clinic } = useCrm();
  const canEdit = level(me, clinic, "doctors") === "edit";
  const [editing, setEditing] = useState(false);
  const canBook = level(me, clinic, "appointments") === "edit";
  const [detail, setDetail] = useState<{
    date: string;
    booking: Booking;
  } | null>(null);
  const [booking, setBooking] = useState<{
    date: string;
    time: string;
    kinds: Kind[];
  } | null>(null);
  const [version, setVersion] = useState(0); // bumped after a save, to load the week again
  const [kind, setKind] = useState<Kind>("all");
  const [week, setWeek] = useState<{ key: string; data: Week }>();
  const [error, setError] = useState("");
  const key = `${clinicId}|${doctorId}|${start ?? ""}|${version}`;

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
      {detail && (
        <DetailCard
          doctor={w.doctor.name}
          date={detail.date}
          booking={detail.booking}
          onClose={(saved) => {
            setDetail(null);
            if (saved) setVersion((v) => v + 1);
          }}
        />
      )}
      {booking && (
        <BookCard
          clinicId={clinicId}
          doctorId={doctorId}
          doctor={w.doctor.name}
          slot={booking}
          onClose={(saved) => {
            setBooking(null);
            if (saved) setVersion((v) => v + 1);
          }}
        />
      )}
      {editing && (
        <ScheduleCard
          clinicId={clinicId}
          doctorId={doctorId}
          onClose={(saved) => {
            setEditing(false);
            if (saved) setVersion((v) => v + 1);
          }}
        />
      )}
      <div
        className="row"
        style={{ gap: 8, marginBottom: 10, flexWrap: "wrap" }}
      >
        <Link className="btn g" href="/doctors">
          ← All doctors
        </Link>
        {canEdit && !editing && (
          <button className="btn" onClick={() => setEditing(true)}>
            Edit hours &amp; leave
          </button>
        )}
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
                    <td
                      key={d.date}
                      className={c.cls}
                      title={
                        c.free && canBook
                          ? `${c.title} · click to add a patient`
                          : c.booking && canBook
                            ? `${c.title} · click for details`
                            : c.title
                      }
                      onClick={
                        c.free && canBook
                          ? () => {
                              setDetail(null);
                              setBooking({
                                date: d.date,
                                time: hm(m),
                                kinds: c.free!,
                              });
                            }
                          : c.booking && canBook
                            ? () => {
                                setBooking(null);
                                setDetail({
                                  date: d.date,
                                  booking: c.booking!,
                                });
                              }
                            : undefined
                      }
                    >
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

type Schedule = {
  in_clinic: Hours[];
  online: Hours[];
  leave: Leave[];
  calcom: boolean;
  problems: string[];
};

/** Edit a doctor's weekly hours and upcoming leave (profile and slot lengths: Dashboard → Doctors). */
function ScheduleCard({
  clinicId,
  doctorId,
  onClose,
}: {
  clinicId: string;
  doctorId: string;
  onClose: (saved: boolean) => void;
}) {
  const { toast } = useCrm();
  const url = `/v1/crm/availability/${doctorId}/schedule?clinic=${clinicId}`;
  const [s, setS] = useState<Schedule | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    api<Schedule>(url).then(
      (x) => live && setS(x),
      (e) =>
        live &&
        setError(
          e instanceof ApiError ? e.message : "Could not load the hours.",
        ),
    );
    return () => {
      live = false;
    };
  }, [url]);

  async function save() {
    if (!s) return;
    setBusy(true);
    setError("");
    try {
      const x = await api<Schedule>(url, {
        method: "PUT",
        body: JSON.stringify({
          in_clinic: s.in_clinic,
          online: s.online,
          leave: s.leave,
        }),
      });
      if (x.problems.length) {
        setS(x);
        toast("Saved, with problems from Cal.com");
      } else {
        toast("Hours and leave saved");
        onClose(true);
      }
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const clash = s ? overlap(s.in_clinic, s.online) : "";
  return (
    <div
      className="card"
      style={{ padding: 16, marginBottom: 12, maxWidth: 760 }}
    >
      <b>Edit hours &amp; leave</b>
      <p className="sub2" style={{ margin: "4px 0 0" }}>
        Weekly hours and leave. In-clinic and online hours can be the same: a
        time booked for one is no longer offered for the other. Profile and slot
        lengths are in Dashboard → Doctors.
      </p>
      {!s && !error && <p className="sub2">Loading…</p>}
      {s && (
        <>
          <HoursEditor
            title="In-clinic hours"
            hours={s.in_clinic}
            onChange={(h) => setS({ ...s, in_clinic: h })}
          />
          <HoursEditor
            title="Online hours"
            hours={s.online}
            onChange={(h) => setS({ ...s, online: h })}
          />
          {s.calcom && (
            <p className="sub2" style={{ margin: "6px 0 0", fontSize: 12.5 }}>
              Connected to Cal.com: online hours and leave are sent there when
              you save.
            </p>
          )}
          <LeaveEditor
            leave={s.leave}
            onChange={(l) => setS({ ...s, leave: l })}
          />
        </>
      )}
      {clash && (
        <p className="warnbox" style={{ marginTop: 12 }}>
          {clash}
        </p>
      )}
      {s?.problems.map((p) => (
        <p key={p} className="warnbox" style={{ marginTop: 8 }}>
          {p}
        </p>
      ))}
      {error && error !== clash && (
        <p role="alert" style={{ color: "var(--err)", margin: "12px 0 0" }}>
          {error}
        </p>
      )}
      <div className="row" style={{ gap: 8, marginTop: 16 }}>
        <button
          className="btn"
          disabled={busy || !s}
          onClick={() => void save()}
        >
          {busy ? "Saving…" : "Save"}
        </button>
        <button
          className="btn g"
          disabled={busy}
          onClick={() => onClose(false)}
        >
          {s?.problems.length ? "Close" : "Cancel"}
        </button>
      </div>
    </div>
  );
}

/** Add a patient at a free time: an existing patient (search) or a new one. It becomes a booking request (Inbox →
 * Booking requests, or Online consults) holding the time; the Inbox then opens on it, ready to confirm. */
function BookCard({
  clinicId,
  doctorId,
  doctor,
  slot,
  onClose,
}: {
  clinicId: string;
  doctorId: string;
  doctor: string;
  slot: { date: string; time: string; kinds: Kind[] };
  onClose: (saved: boolean) => void;
}) {
  const { toast } = useCrm();
  const router = useRouter();
  const [type, setType] = useState<Kind>(slot.kinds[0]);
  const [mode, setMode] = useState<"find" | "new">("find");
  const [q, setQ] = useState("");
  const [found, setFound] = useState<LeadRow[]>([]);
  const [lead, setLead] = useState<LeadRow | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [cc, setCc] = useState("+91");
  const [treatments, setTreatments] = useState<string[]>([]);
  const [treatment, setTreatment] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (mode !== "find" || q.trim().length < 2) return;
    let live = true;
    const t = setTimeout(() => {
      api<LeadList>(
        `/v1/crm/leads?clinic=${clinicId}&q=${encodeURIComponent(q.trim())}&limit=6`,
      ).then(
        (r) => live && setFound(r.items),
        () => live && setFound([]),
      );
    }, 300);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [q, mode, clinicId]);

  useEffect(() => {
    let live = true;
    api<LeadOptions>(`/v1/crm/lead-options?clinic=${clinicId}`).then(
      (o) => live && setTreatments(o.treatments),
      () => {},
    );
    return () => {
      live = false;
    };
  }, [clinicId]);

  async function book() {
    setBusy(true);
    setError("");
    try {
      const r = await api<{
        lead_code: string;
        request_id: string;
        tab: string;
      }>(`/v1/crm/availability/${doctorId}/book?clinic=${clinicId}`, {
        method: "POST",
        body: JSON.stringify({
          date: slot.date,
          time: slot.time,
          type,
          ...(mode === "find"
            ? { lead_code: lead?.code }
            : {
                patient: {
                  name: name.trim(),
                  phone: phone.trim(),
                  phone_cc: cc,
                },
              }),
          email: needEmail ? email.trim() : null,
          treatment: treatment.trim() || null,
          note,
        }),
      });
      toast(`Added (${r.lead_code}): confirm it in the Inbox`);
      onClose(true);
      router.push(`/inbox?tab=${r.tab}&open=${r.request_id}`);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not book. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const needEmail =
    type === "online" && (mode === "new" || (!!lead && !lead.email));
  const h = head(slot.date);
  const ready =
    mode === "find"
      ? !!lead
      : name.trim().length >= 2 && phone.trim().length >= 6;
  return (
    <div
      className="card"
      style={{ padding: 16, marginBottom: 12, maxWidth: 760 }}
    >
      <b>
        Add a patient · {doctor} · {h.day} {h.date}, {label(mins(slot.time))}
      </b>
      <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: "wrap" }}>
        {slot.kinds.length > 1 ? (
          <select
            className="sel"
            aria-label="Kind of visit"
            value={type}
            onChange={(e) => setType(e.target.value as Kind)}
          >
            <option value="in_clinic">In-clinic visit</option>
            <option value="online">Online consult</option>
          </select>
        ) : (
          <span className="sub2">
            {type === "online" ? "Online consult" : "In-clinic visit"}
          </span>
        )}
        <div className="seg">
          <button
            className={mode === "find" ? "on" : ""}
            onClick={() => setMode("find")}
          >
            Existing patient
          </button>
          <button
            className={mode === "new" ? "on" : ""}
            onClick={() => setMode("new")}
          >
            New patient
          </button>
        </div>
      </div>
      {mode === "find" ? (
        <div style={{ marginTop: 10 }}>
          {lead ? (
            <div className="row" style={{ gap: 8 }}>
              <span>
                <b>{lead.name}</b> · {lead.code} · {lead.phone}
              </span>
              <button className="btn g" onClick={() => setLead(null)}>
                Change
              </button>
            </div>
          ) : (
            <>
              <input
                className="f"
                style={{ width: "100%" }}
                placeholder="Search name, phone or lead code"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                autoFocus
              />
              {q.trim().length >= 2 &&
                found.map((x) => (
                  <button
                    key={x.code}
                    className="btn g"
                    style={{
                      display: "block",
                      width: "100%",
                      textAlign: "left",
                      marginTop: 4,
                    }}
                    onClick={() => setLead(x)}
                  >
                    {x.name} · {x.code} · {x.phone}
                  </button>
                ))}
              {q.trim().length >= 2 && !found.length && (
                <p className="sub2" style={{ margin: "6px 0 0" }}>
                  No patient found. Use New patient.
                </p>
              )}
            </>
          )}
        </div>
      ) : (
        <div
          className="row"
          style={{ gap: 8, marginTop: 10, flexWrap: "wrap" }}
        >
          <input
            className="f"
            style={{ flex: "1 1 200px" }}
            placeholder="Patient name"
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <select
            className="sel"
            aria-label="Country code"
            value={cc}
            onChange={(e) => setCc(e.target.value)}
          >
            {COUNTRY_CODES.map((c) => (
              <option key={c.code} value={c.code}>
                {c.label}
              </option>
            ))}
          </select>
          <input
            className="f"
            style={{ flex: "1 1 160px" }}
            placeholder="Mobile, e.g. 9876543210"
            maxLength={20}
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </div>
      )}
      <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: "wrap" }}>
        <select
          className="sel"
          style={{ flex: "1 1 200px" }}
          aria-label="Treatment"
          value={treatment}
          onChange={(e) => setTreatment(e.target.value)}
        >
          <option value="">Treatment: not decided</option>
          {treatments.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <input
          className="f"
          style={{ flex: "2 1 260px" }}
          placeholder="Note (optional)"
          maxLength={2000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      {needEmail && (
        <input
          className="f"
          style={{ width: "100%", marginTop: 10 }}
          type="email"
          placeholder="Patient's email (the Google Meet link is sent here)"
          maxLength={200}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      )}
      {type === "online" && (
        <p className="sub2" style={{ margin: "8px 0 0" }}>
          Goes to Inbox → Online consults to confirm: confirming books Cal.com
          and emails the Google Meet link to the patient.
        </p>
      )}
      {error && (
        <p role="alert" style={{ color: "var(--err)", margin: "10px 0 0" }}>
          {error}
        </p>
      )}
      <div className="row" style={{ gap: 8, marginTop: 14 }}>
        <button
          className="btn"
          disabled={busy || !ready}
          onClick={() => void book()}
        >
          {busy ? "Adding…" : "Add"}
        </button>
        <button
          className="btn g"
          disabled={busy}
          onClick={() => onClose(false)}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

const LOST: [string, string][] = [
  ["not_reachable", "Not reachable"],
  ["not_interested", "Not interested"],
  ["price", "Price"],
  ["chose_another_clinic", "Chose another clinic"],
  ["other", "Other"],
];
const STATUS: Record<string, string> = {
  pending: "Pending (waiting in the Inbox)",
  confirmed: "Confirmed",
  visited: "Visited",
  no_show: "No show",
  missed: "Missed",
};

/** A booking's details, with what staff can do with it: pending → confirm in the Inbox or reject; confirmed
 * → visited, no show or cancel; and mark the lead Lost. */
function DetailCard({
  doctor,
  date,
  booking: b,
  onClose,
}: {
  doctor: string;
  date: string;
  booking: Booking;
  onClose: (saved: boolean) => void;
}) {
  const { toast } = useCrm();
  const router = useRouter();
  const [reason, setReason] = useState("");
  const [lost, setLost] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function call(
    path: string,
    method: string,
    body: object,
    done: string,
  ) {
    setBusy(true);
    setError("");
    try {
      await api(path, { method, body: JSON.stringify(body) });
      toast(done);
      onClose(true);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const h = head(date);
  const kind = b.type === "online" ? "Online consult" : "In-clinic visit";
  const tab = b.type === "online" ? "online" : "book";
  const open = b.status === "pending" || b.status === "confirmed";
  const needReason = reason.trim().length < 3;
  return (
    <div
      className="card"
      style={{ padding: 16, marginBottom: 12, maxWidth: 760 }}
    >
      <b>
        {b.patient} · {doctor} · {h.day} {h.date}, {b.start}–{b.end}
      </b>
      <p className="sub2" style={{ margin: "4px 0 0" }}>
        {kind} · {STATUS[b.status] ?? b.status} · {b.lead_code}
        {b.phone ? ` · ${b.phone}` : ""}
        {b.treatment ? ` · ${b.treatment}` : ""} · Lead:{" "}
        {b.stage.replace("_", " ")}
      </p>

      {open && (
        <input
          className="f"
          style={{ width: "100%", marginTop: 12 }}
          placeholder={
            b.request_id
              ? "Reason to reject (needed to reject)"
              : "Reason to cancel (needed to cancel)"
          }
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      )}
      <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: "wrap" }}>
        {b.request_id && (
          <>
            <button
              className="btn"
              disabled={busy}
              onClick={() =>
                router.push(`/inbox?tab=${tab}&open=${b.request_id}`)
              }
            >
              Open in Inbox to confirm
            </button>
            <button
              className="btn red"
              disabled={busy || needReason}
              onClick={() =>
                void call(
                  `/v1/crm/requests/${b.request_id}/reject`,
                  "POST",
                  { reason: reason.trim() },
                  "Request rejected: the time is free again",
                )
              }
            >
              Reject
            </button>
          </>
        )}
        {open && !b.request_id && (
          <>
            <button
              className="btn"
              disabled={busy}
              onClick={() =>
                void call(
                  `/v1/crm/appointments/${b.id}/status`,
                  "POST",
                  { status: "visited" },
                  "Marked visited",
                )
              }
            >
              Visited
            </button>
            <button
              className="btn g"
              disabled={busy}
              onClick={() =>
                void call(
                  `/v1/crm/appointments/${b.id}/status`,
                  "POST",
                  { status: "no_show" },
                  "Marked no show",
                )
              }
            >
              No show
            </button>
            <button
              className="btn red"
              disabled={busy || needReason}
              onClick={() =>
                void call(
                  `/v1/crm/appointments/${b.id}/status`,
                  "POST",
                  { status: "cancelled", reason: reason.trim() },
                  "Booking cancelled: the time is free again",
                )
              }
            >
              Cancel booking
            </button>
          </>
        )}
      </div>

      {b.stage !== "lost" && (
        <div
          className="row"
          style={{ gap: 8, marginTop: 12, flexWrap: "wrap" }}
        >
          <select
            className="sel"
            aria-label="Lost reason"
            value={lost}
            onChange={(e) => setLost(e.target.value)}
          >
            <option value="">Mark lead as Lost: choose a reason</option>
            {LOST.map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          <button
            className="btn g"
            disabled={busy || !lost}
            onClick={() =>
              void call(
                `/v1/crm/leads/${b.lead_code}`,
                "PATCH",
                { stage: "lost", stage_reason: lost },
                "Lead marked Lost",
              )
            }
          >
            Mark Lost
          </button>
          <span className="sub2">
            The booking itself stays until you cancel or reject it.
          </span>
        </div>
      )}

      {error && (
        <p role="alert" style={{ color: "var(--err)", margin: "10px 0 0" }}>
          {error}
        </p>
      )}
      <div className="row" style={{ gap: 8, marginTop: 14 }}>
        <Link className="btn g" href={`/leads?open=${b.lead_code}`}>
          Open lead
        </Link>
        <button
          className="btn g"
          disabled={busy}
          onClick={() => onClose(false)}
        >
          Close
        </button>
      </div>
    </div>
  );
}
