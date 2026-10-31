"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import Live, { Today } from "@/components/crm/Live";
import { api, ApiError } from "@/lib/api";
import { type Board, type Day, spans, useDoctors } from "@/lib/availability";

// CRM → Doctors Availability. All doctors: a card per doctor with today's hours, booked, pending and free.
// One doctor (?doc=<id>): their week (built in the next step). Reads ?doc= from the address, so the page renders
// it inside a Suspense boundary.

/** Today's line for a doctor's card. */
function status(d: Day): string {
  if (d.holiday !== null)
    return `Clinic holiday${d.holiday ? `: ${d.holiday}` : ""}`;
  if (d.leave !== null) return `On leave${d.leave ? `: ${d.leave}` : ""}`;
  const parts = [
    !d.closed && d.in_clinic.length ? `In-clinic ${spans(d.in_clinic)}` : "",
    d.online.length ? `Online ${spans(d.online)}` : "",
  ].filter(Boolean);
  if (parts.length) return parts.join(" · ");
  return d.closed ? "Clinic closed today" : "Not working today";
}

export default function DoctorsView() {
  const doc = useSearchParams().get("doc") ?? "";
  const { me, clinic } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const doctors = useDoctors(clinicId);
  const [board, setBoard] = useState<{ clinic: string; data: Board }>();
  const [error, setError] = useState("");

  useEffect(() => {
    if (!clinicId || doc) return;
    let live = true;
    api<Board>(`/v1/crm/availability?clinic=${clinicId}`).then(
      (data) => live && setBoard({ clinic: clinicId, data }),
      (e) =>
        live &&
        setError(
          e instanceof ApiError ? e.message : "Could not load the doctors.",
        ),
    );
    return () => {
      live = false;
    };
  }, [clinicId, doc]);

  if (doc) {
    const d = doctors.find((x) => x.id === doc);
    return (
      <>
        <div className="ph">
          <div>
            <h1>{d?.name ?? "Doctor"}</h1>
            <p>Week schedule, leave and slot settings</p>
          </div>
        </div>
        <div className="empty">
          <h2>Week view comes in the next step</h2>
          <Link href="/doctors">Back to all doctors</Link>
        </div>
      </>
    );
  }

  const data = board?.clinic === clinicId ? board?.data : undefined;
  return (
    <>
      <div className="ph">
        <div>
          <h1>Doctors Availability</h1>
          <p>
            Today,{" "}
            <Live>
              <Today />
            </Live>
            {data ? ` · Clinic ${data.open_time}–${data.close_time}` : ""}
          </p>
        </div>
      </div>
      {error && <p className="warnbox">{error}</p>}
      {!data && !error && <p className="sub2">Loading…</p>}
      {data && data.doctors.length === 0 && (
        <div className="empty">
          <h2>No doctors yet</h2>
          Add doctors in Dashboard → Doctors.
        </div>
      )}
      {data && (
        <div className="dgrid">
          {data.doctors.map(({ doctor: d, today: t }) => {
            const booked = t.bookings.filter(
              (b) => b.status !== "pending",
            ).length;
            const pending = t.bookings.filter(
              (b) => b.status === "pending",
            ).length;
            return (
              <Link
                key={d.id}
                href={`/doctors?doc=${d.id}`}
                className="card dcard2"
                style={{
                  padding: 14,
                  display: "block",
                  color: "inherit",
                  textDecoration: "none",
                }}
              >
                <b>{d.name}</b>
                <div className="sub2">{d.role_title}</div>
                <p style={{ margin: "8px 0", fontSize: 13 }}>{status(t)}</p>
                <div className="row" style={{ gap: 14, fontSize: 13 }}>
                  <span>
                    <span className="av-busy">{booked}</span> booked
                  </span>
                  <span>
                    <span className="av-pend">{pending}</span> pending
                  </span>
                  <span>
                    <span className="av-free">{t.free_in_clinic.length}</span>{" "}
                    free in-clinic
                  </span>
                  <span>
                    <span className="av-free">{t.free_online.length}</span> free
                    online
                  </span>
                </div>
                <div className="sub2" style={{ marginTop: 6 }}>
                  Slots: in-clinic {d.in_clinic_minutes} min · online{" "}
                  {d.online_minutes} min
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
