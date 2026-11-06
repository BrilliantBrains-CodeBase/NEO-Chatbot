"use client";

import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import SlotPicker, { type Pick } from "@/components/inbox/SlotPicker";
import {
  api,
  ApiError,
  type Appointment,
  type LeadDetail,
  type LeadOptions,
} from "@/lib/api";

const when = (a: Appointment) => {
  const day = new Date(a.day + "T00:00:00").toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  const time = a.start
    ? new Date(a.start).toLocaleTimeString("en-IN", {
        hour: "numeric",
        minute: "2-digit",
      })
    : "any time";
  return `${day}, ${time}`;
};

/** The lead's upcoming appointments: a confirmed one is rescheduled here; with none (and no booking
 * waiting), one is booked here, held for confirmation as from the calendar. */
export default function LeadAppointments({
  lead,
  clinicId,
  options,
  canChange,
  bookingWaiting,
  version,
  onChanged,
}: {
  lead: LeadDetail;
  clinicId: string | undefined;
  options: LeadOptions | null;
  canChange: boolean; // the lead has an owner and this person may change appointments
  bookingWaiting: boolean; // a booking request is waiting: it is changed in Pending requests
  version: number;
  onChanged: (message: string) => void;
}) {
  const { refreshInbox } = useCrm();
  const [items, setItems] = useState<{ key: string; list: Appointment[] }>({
    key: "",
    list: [],
  });
  const [moving, setMoving] = useState<string | null>(null); // the appointment being rescheduled
  const [booking, setBooking] = useState(false);
  const [pick, setPick] = useState<Pick | null>(null);
  const [type, setType] = useState(
    lead.type === "online" ? "online" : "in_clinic",
  );
  const [treatment, setTreatment] = useState(lead.treatment ?? "");
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = `${lead.code}|${version}`;

  useEffect(() => {
    let live = true;
    api<Appointment[]>(
      `/v1/crm/leads/${encodeURIComponent(lead.code)}/appointments`,
    ).then(
      (list) => live && setItems({ key, list }),
      () => live && setItems({ key, list: [] }),
    );
    return () => {
      live = false;
    };
  }, [lead.code, key]);

  const list = items.key === key ? items.list : [];
  const confirmed = list.filter((a) => a.status === "confirmed");

  function reset() {
    setMoving(null);
    setBooking(false);
    setPick(null);
    setNote("");
    setError("");
  }

  async function run(path: string, body: object, done: string) {
    setBusy(true);
    setError("");
    try {
      await api(path, { method: "POST", body: JSON.stringify(body) });
      reset();
      refreshInbox();
      onChanged(done);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!list.length && (!canChange || bookingWaiting)) return null;
  const needEmail = type === "online" && !lead.email;
  return (
    <div className="sec">
      <h4>APPOINTMENTS</h4>
      {error && <div className="warnbox">{error}</div>}
      <div className="rq-list">
        {list.map((a) => (
          <div className="rq" key={a.id}>
            <div className="rq-h">
              <b>{when(a)}</b>
              <span
                className={`badge ${a.status === "confirmed" ? "b-vi" : "b-fu"}`}
              >
                {a.status === "confirmed"
                  ? "Confirmed"
                  : "Waiting for confirmation"}
              </span>
            </div>
            <span className="sub2">
              {[
                a.doctor ?? "Any doctor",
                a.type === "online" ? "Online" : "In-clinic",
              ].join(" · ")}
              {a.status === "pending" &&
                " · confirm or change it under Pending requests"}
            </span>
            {canChange && a.status === "confirmed" && moving !== a.id && (
              <button
                className="lnk"
                style={{ alignSelf: "flex-start" }}
                onClick={() => (reset(), setMoving(a.id))}
              >
                Reschedule
              </button>
            )}
            {moving === a.id && clinicId && (
              <div className="rq-act">
                <SlotPicker
                  clinicId={clinicId}
                  mode={a.type}
                  doctorId={a.doctor_id}
                  value={pick}
                  onChange={setPick}
                />
                <div className="row">
                  <button
                    className="btn"
                    disabled={busy || !pick}
                    onClick={() =>
                      pick &&
                      run(
                        `/v1/crm/appointments/${a.id}/move`,
                        {
                          date: pick.date,
                          time: pick.time,
                          doctor_id: pick.doctorId || null,
                        },
                        a.type === "online"
                          ? "Rescheduled: the patient gets the new time by email"
                          : "Rescheduled",
                      )
                    }
                  >
                    Move to this time
                  </button>
                  <button className="btn g" onClick={reset} disabled={busy}>
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {canChange && !bookingWaiting && confirmed.length === 0 && !booking && (
        <button
          className="btn g"
          style={{ alignSelf: "flex-start" }}
          onClick={() => (reset(), setBooking(true))}
        >
          Book appointment
        </button>
      )}
      {booking && clinicId && (
        <div className="rq">
          <div className="rq-act" style={{ borderTop: 0, paddingTop: 0 }}>
            <div className="row">
              <select
                className="f"
                aria-label="Consultation"
                value={type}
                onChange={(e) => (setType(e.target.value), setPick(null))}
              >
                <option value="in_clinic">In-clinic</option>
                <option value="online">Online</option>
              </select>
              <select
                className="f"
                aria-label="Treatment"
                value={treatment}
                onChange={(e) => setTreatment(e.target.value)}
              >
                <option value="">Not decided</option>
                {(options?.treatments ?? []).map((t) => (
                  <option key={t}>{t}</option>
                ))}
                {treatment &&
                  !(options?.treatments ?? []).includes(treatment) && (
                    <option>{treatment}</option>
                  )}
              </select>
            </div>
            <SlotPicker
              key={type}
              clinicId={clinicId}
              mode={type}
              doctorId={lead.doctor_id ?? null}
              value={pick}
              onChange={setPick}
            />
            {pick && !pick.doctorId && (
              <p className="sub2" style={{ margin: 0 }}>
                Choose a doctor above to book this time.
              </p>
            )}
            {needEmail && (
              <input
                className="f"
                type="email"
                placeholder="Patient's email, for the Meet link"
                aria-label="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                maxLength={200}
              />
            )}
            <input
              className="f"
              placeholder="Note for the team (optional)"
              aria-label="Note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={2000}
            />
            <div className="row">
              <button
                className="btn"
                disabled={
                  busy ||
                  !pick ||
                  !pick.doctorId ||
                  (needEmail && !email.trim())
                }
                onClick={() =>
                  pick &&
                  run(
                    `/v1/crm/availability/${pick.doctorId}/book?clinic=${clinicId}`,
                    {
                      date: pick.date,
                      time: pick.time,
                      type,
                      lead_code: lead.code,
                      treatment: treatment || null,
                      email: needEmail ? email.trim() : null,
                      note,
                    },
                    "Booked: confirm it under Pending requests",
                  )
                }
              >
                Book this time
              </button>
              <button className="btn g" onClick={reset} disabled={busy}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
