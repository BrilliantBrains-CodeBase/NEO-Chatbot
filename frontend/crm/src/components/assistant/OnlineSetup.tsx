"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";

// Integrations → Cal.com → Set up online consults. Which doctors do online consults, their online hours, leave
// and the clinic's holidays: saved in the CRM (the one source the chatbot also uses) and sent to the clinic's
// Cal.com as one schedule and one event per doctor. The clinic sets up nothing in Cal.com.

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
  const [newDoctor, setNewDoctor] = useState("");
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

  async function call(
    path: string,
    method: string,
    body: object,
    done: string,
  ) {
    setBusy(true);
    setError("");
    try {
      const s = await api<Setup>(`${url}${path}`, {
        method,
        body: JSON.stringify(body),
      });
      setSetup(s);
      toast(s.problems.length ? "Saved, with problems from Cal.com" : done);
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
  const put = (i: number, patch: Partial<Doctor>) =>
    setSetup({
      ...setup,
      doctors: setup.doctors.map((d, k) => (k === i ? { ...d, ...patch } : d)),
    });

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
        Tick the doctors who do online consults and set their online hours and
        leave. Saved in the CRM (the chatbot uses the same hours) and created in
        Cal.com for you: one consult per doctor, with Google Meet.
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
              onChange={(e) => put(i, { online: e.target.checked })}
            />
            {d.name}
            {d.online && (
              <select
                className="sel"
                value={d.consult_minutes}
                onChange={(e) =>
                  put(i, { consult_minutes: Number(e.target.value) })
                }
              >
                {[15, 30, 45, 60].map((m) => (
                  <option key={m} value={m}>
                    {m} min consult
                  </option>
                ))}
              </select>
            )}
          </label>
          {d.online && (
            <>
              <p className="sub2" style={{ margin: "8px 0 0", fontSize: 12 }}>
                Online hours
              </p>
              {d.hours.map((h, j) => (
                <div key={j} style={row}>
                  <select
                    className="sel"
                    value={h.weekday}
                    onChange={(e) =>
                      put(i, {
                        hours: d.hours.map((x, k) =>
                          k === j
                            ? { ...x, weekday: Number(e.target.value) }
                            : x,
                        ),
                      })
                    }
                  >
                    {DAYS.map((day, n) => (
                      <option key={day} value={n}>
                        {day}
                      </option>
                    ))}
                  </select>
                  {(["start", "end"] as const).map((f) => (
                    <input
                      key={f}
                      type="time"
                      value={h[f]}
                      onChange={(e) =>
                        put(i, {
                          hours: d.hours.map((x, k) =>
                            k === j ? { ...x, [f]: e.target.value } : x,
                          ),
                        })
                      }
                    />
                  ))}
                  <button
                    aria-label="Remove"
                    onClick={() =>
                      put(i, { hours: d.hours.filter((_, k) => k !== j) })
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
                  put(i, {
                    hours: [
                      ...d.hours,
                      { weekday: 1, start: "10:00", end: "13:00" },
                    ],
                  })
                }
              >
                + Add hours
              </button>
              <p className="sub2" style={{ margin: "8px 0 0", fontSize: 12 }}>
                Leave (no online consults)
              </p>
              {d.leave.map((x, j) => (
                <div key={j} style={row}>
                  {(["from_date", "to_date"] as const).map((f) => (
                    <input
                      key={f}
                      type="date"
                      value={x[f]}
                      onChange={(e) =>
                        put(i, {
                          leave: d.leave.map((y, k) =>
                            k === j ? { ...y, [f]: e.target.value } : y,
                          ),
                        })
                      }
                    />
                  ))}
                  <input
                    placeholder="Reason (optional)"
                    maxLength={200}
                    value={x.reason}
                    onChange={(e) =>
                      put(i, {
                        leave: d.leave.map((y, k) =>
                          k === j ? { ...y, reason: e.target.value } : y,
                        ),
                      })
                    }
                  />
                  <button
                    aria-label="Remove"
                    onClick={() =>
                      put(i, { leave: d.leave.filter((_, k) => k !== j) })
                    }
                  >
                    ✕
                  </button>
                </div>
              ))}
              <button
                className="pill"
                style={{ marginTop: 4 }}
                onClick={() => {
                  const today = new Date().toISOString().slice(0, 10);
                  put(i, {
                    leave: [
                      ...d.leave,
                      { from_date: today, to_date: today, reason: "" },
                    ],
                  });
                }}
              >
                + Add leave
              </button>
            </>
          )}
        </div>
      ))}
      <div style={row}>
        <input
          className="f"
          placeholder="New doctor's name, e.g. Dr Asha Rao"
          maxLength={100}
          value={newDoctor}
          onChange={(e) => setNewDoctor(e.target.value)}
        />
        <button
          className="btn g"
          disabled={busy || newDoctor.trim().length < 2}
          onClick={async () => {
            await call(
              "/doctors",
              "POST",
              { name: newDoctor.trim() },
              "Doctor added",
            );
            setNewDoctor("");
          }}
        >
          Add a doctor
        </button>
      </div>
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
        <button
          className="btn"
          disabled={busy}
          onClick={() =>
            call(
              "/setup",
              "PUT",
              { doctors: setup.doctors, holidays: setup.holidays },
              "Saved and sent to Cal.com",
            )
          }
        >
          {busy ? "Saving and sending to Cal.com…" : "Save and send to Cal.com"}
        </button>
      </div>
    </div>
  );
}
