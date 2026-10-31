"use client";

// A doctor's weekly hours and leave, edited the same way in Dashboard → Doctors and CRM → Doctors Availability.

export type Hours = { weekday: number; start: string; end: string };
export type Leave = { from_date: string; to_date: string; reason: string };

export const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const row = {
  display: "flex",
  gap: 6,
  alignItems: "center",
  flexWrap: "wrap" as const,
  marginTop: 4,
};

/** Two rows of the same kind that overlap, as the backend words it; "" when none. In-clinic and online may
 * overlap: a time booked in one is not offered in the other. */
export function overlap(inClinic: Hours[], online: Hours[]): string {
  for (const [kind, rows] of [
    ["in-clinic", inClinic],
    ["online", online],
  ] as const)
    for (let i = 0; i < rows.length; i++)
      for (const b of rows.slice(i + 1)) {
        const a = rows[i];
        if (a.weekday === b.weekday && a.start < b.end && b.start < a.end)
          return `${DAYS[a.weekday]}: ${kind} hours ${a.start}–${a.end} and ${b.start}–${b.end} overlap. Join them into one row.`;
      }
  return "";
}

export function HoursEditor({
  title,
  hours,
  onChange,
}: {
  title: string;
  hours: Hours[];
  onChange: (h: Hours[]) => void;
}) {
  const set = (j: number, patch: Partial<Hours>) =>
    onChange(hours.map((x, k) => (k === j ? { ...x, ...patch } : x)));
  return (
    <>
      <p className="sub2" style={{ margin: "12px 0 0" }}>
        <b>{title}</b>
      </p>
      {hours.length === 0 && (
        <p className="sub2" style={{ margin: "4px 0 0", fontSize: 12.5 }}>
          None.
        </p>
      )}
      {hours.map((h, j) => (
        <div key={j} style={row}>
          <select
            className="sel"
            aria-label="Day"
            value={h.weekday}
            onChange={(e) => set(j, { weekday: Number(e.target.value) })}
          >
            {DAYS.map((day, n) => (
              <option key={day} value={n}>
                {day}
              </option>
            ))}
          </select>
          <input
            className="f"
            type="time"
            aria-label="From"
            value={h.start}
            onChange={(e) => set(j, { start: e.target.value })}
          />
          <span className="sub2">to</span>
          <input
            className="f"
            type="time"
            aria-label="To"
            value={h.end}
            onChange={(e) => set(j, { end: e.target.value })}
          />
          <button
            className="btn g"
            aria-label="Remove"
            onClick={() => onChange(hours.filter((_, k) => k !== j))}
          >
            ✕
          </button>
        </div>
      ))}
      <button
        className="pill"
        style={{ marginTop: 6 }}
        onClick={() =>
          onChange([...hours, { weekday: 1, start: "10:00", end: "13:00" }])
        }
      >
        + Add hours
      </button>
    </>
  );
}

export function LeaveEditor({
  leave,
  onChange,
}: {
  leave: Leave[];
  onChange: (l: Leave[]) => void;
}) {
  const set = (j: number, patch: Partial<Leave>) =>
    onChange(leave.map((y, k) => (k === j ? { ...y, ...patch } : y)));
  return (
    <>
      <p className="sub2" style={{ margin: "12px 0 0" }}>
        <b>Leave (no bookings, in-clinic or online)</b>
      </p>
      {leave.map((x, j) => (
        <div key={j} style={row}>
          {(["from_date", "to_date"] as const).map((f) => (
            <input
              key={f}
              className="f"
              type="date"
              aria-label={f === "from_date" ? "From" : "To"}
              value={x[f]}
              onChange={(e) => set(j, { [f]: e.target.value })}
            />
          ))}
          <input
            className="f"
            placeholder="Reason (optional)"
            maxLength={200}
            value={x.reason}
            onChange={(e) => set(j, { reason: e.target.value })}
          />
          <button
            className="btn g"
            aria-label="Remove"
            onClick={() => onChange(leave.filter((_, k) => k !== j))}
          >
            ✕
          </button>
        </div>
      ))}
      <button
        className="pill"
        style={{ marginTop: 6 }}
        onClick={() => {
          const today = new Date().toISOString().slice(0, 10);
          onChange([
            ...leave,
            { from_date: today, to_date: today, reason: "" },
          ]);
        }}
      >
        + Add leave
      </button>
    </>
  );
}
