"use client";

import Loading from "@/components/crm/Loading";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";
import {
  HoursEditor,
  LeaveEditor,
  overlap,
  type Hours,
  type Leave,
} from "@/components/crm/ScheduleEditors";

// Dashboard → Doctors: every doctor with all settings (profile, slot lengths, in-clinic and online hours, leave)
// and the clinic's default slot lengths. In-clinic and online hours may overlap (a booking in one hides that time
// in the other); two rows of the same kind may not.

type Figure = { label: string; value: string };
type Doctor = {
  id: string;
  name: string;
  role_title: string;
  qualifications: string;
  photo: string;
  about: string;
  stats: Figure[];
  active: boolean;
  in_clinic_minutes: number | null;
  online_minutes: number | null;
  in_clinic: Hours[];
  online: Hours[];
  leave: Leave[];
  calcom: boolean;
};
type Defaults = { slot_minutes: number; online_slot_minutes: number };
type Data = { defaults: Defaults; doctors: Doctor[]; problems: string[] };

const LENGTHS = [5, 10, 15, 20, 30, 45, 60];
const row = {
  display: "flex",
  gap: 6,
  alignItems: "center",
  flexWrap: "wrap" as const,
  marginTop: 4,
};
const EMPTY: Doctor = {
  id: "",
  name: "",
  role_title: "Doctor",
  qualifications: "",
  photo: "",
  about: "",
  stats: [],
  active: true,
  in_clinic_minutes: null,
  online_minutes: null,
  in_clinic: [],
  online: [],
  leave: [],
  calcom: false,
};

const clashOf = (d: Doctor) => overlap(d.in_clinic, d.online);

const lengthText = (own: number | null, clinic: number) =>
  own ? `${own} min` : `${clinic} min (clinic)`;

export default function DoctorsSetupView() {
  const { me, clinic, toast } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const [data, setData] = useState<Data | null>(null);
  const [defaults, setDefaults] = useState<Defaults | null>(null);
  const [edit, setEdit] = useState<Doctor | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const url = `/v1/crm/console/${clinicId}`;

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Data>(`/v1/crm/console/${clinicId}/doctors`).then(
      (d) => {
        if (!live) return;
        setData(d);
        setDefaults(d.defaults);
      },
      (e) =>
        live &&
        setError(
          e instanceof ApiError ? e.message : "Could not load the doctors.",
        ),
    );
    return () => {
      live = false;
    };
  }, [clinicId]);

  async function call(
    path: string,
    method: string,
    body: object,
    done: string,
  ) {
    setBusy(true);
    setError("");
    try {
      const d = await api<Data>(`${url}${path}`, {
        method,
        body: JSON.stringify(body),
      });
      setData(d);
      setDefaults(d.defaults);
      toast(d.problems.length ? "Saved, with problems from Cal.com" : done);
      return true;
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function saveDoctor() {
    if (!edit) return;
    const body = {
      ...edit,
      stats: edit.stats.filter((s) => s.label.trim() && s.value.trim()),
    };
    const ok = edit.id
      ? await call(`/doctors/${edit.id}`, "PUT", body, "Doctor saved")
      : await call("/doctors", "POST", body, "Doctor added");
    if (ok) setEdit(null);
  }

  const header = (
    <div className="ph">
      <div>
        <h1>Doctors</h1>
        <p>
          {clinic} · Each doctor&apos;s profile, slot lengths, in-clinic and
          online hours, and leave. The chatbot and the CRM use these.
        </p>
      </div>
    </div>
  );

  if (!data || !defaults)
    return (
      <>
        {header}
        {error ? (
          <p className="warnbox">{error}</p>
        ) : (
          <Loading />
        )}
      </>
    );

  if (edit)
    return (
      <>
        {header}
        <DoctorForm
          doctor={edit}
          defaults={data.defaults}
          onChange={setEdit}
          busy={busy}
          error={error}
          onSave={() => void saveDoctor()}
          onCancel={() => {
            setEdit(null);
            setError("");
          }}
        />
      </>
    );

  return (
    <>
      {header}
      {error && <p className="warnbox">{error}</p>}
      {data.problems.map((p) => (
        <p key={p} className="warnbox">
          {p}
        </p>
      ))}

      <div className="card" style={{ padding: 16, marginBottom: 16 }}>
        <b>Clinic slot lengths</b>
        <p className="sub2" style={{ margin: "4px 0 10px" }}>
          Used by every doctor who has no length of their own.
        </p>
        <div style={row}>
          <LengthSelect
            label="In-clinic visit"
            value={defaults.slot_minutes}
            onChange={(v) =>
              setDefaults({ ...defaults, slot_minutes: v ?? 15 })
            }
          />
          <LengthSelect
            label="Online consult"
            value={defaults.online_slot_minutes}
            onChange={(v) =>
              setDefaults({ ...defaults, online_slot_minutes: v ?? 30 })
            }
          />
          <button
            className="btn"
            disabled={
              busy ||
              (defaults.slot_minutes === data.defaults.slot_minutes &&
                defaults.online_slot_minutes ===
                  data.defaults.online_slot_minutes)
            }
            onClick={() =>
              void call(
                "/doctors-defaults",
                "PUT",
                defaults,
                "Slot lengths saved",
              )
            }
          >
            Save
          </button>
        </div>
      </div>

      <div
        className="row"
        style={{ justifyContent: "space-between", marginBottom: 8 }}
      >
        <b>
          {data.doctors.length} doctor{data.doctors.length === 1 ? "" : "s"}
        </b>
        <button className="btn" onClick={() => setEdit({ ...EMPTY })}>
          + Add doctor
        </button>
      </div>
      {data.doctors.map((d) => {
        const clash = clashOf(d);
        return (
          <div
            key={d.id}
            className="card"
            style={{ padding: 12, marginBottom: 8 }}
          >
            <div
              className="row"
              style={{ gap: 12, justifyContent: "space-between" }}
            >
              <div style={{ minWidth: 0 }}>
                <b>{d.name}</b>
                {!d.active && <span className="sub2"> · Inactive</span>}
                {d.calcom && <span className="sub2"> · Cal.com</span>}
                <div className="sub2">{d.role_title}</div>
                <div className="sub2" style={{ fontSize: "var(--fs-small)" }}>
                  In-clinic{" "}
                  {lengthText(d.in_clinic_minutes, data.defaults.slot_minutes)}{" "}
                  · {d.in_clinic.length} time
                  {d.in_clinic.length === 1 ? "" : "s"} a week · Online{" "}
                  {lengthText(
                    d.online_minutes,
                    data.defaults.online_slot_minutes,
                  )}{" "}
                  · {d.online.length} time{d.online.length === 1 ? "" : "s"} a
                  week
                  {d.leave.length ? ` · ${d.leave.length} leave` : ""}
                </div>
              </div>
              <button
                className="btn g"
                onClick={() => setEdit(structuredClone(d))}
              >
                Edit
              </button>
            </div>
            {clash && (
              <p className="warnbox" style={{ margin: "8px 0 0" }}>
                {clash}
              </p>
            )}
          </div>
        );
      })}
    </>
  );
}

function LengthSelect({
  label,
  value,
  clinic,
  onChange,
}: {
  label: string;
  value: number | null;
  clinic?: number; // given: the first choice is "Clinic default"
  onChange: (v: number | null) => void;
}) {
  return (
    <label className="row" style={{ gap: 6 }}>
      <span className="sub2">{label}</span>
      <select
        className="sel"
        value={value ?? ""}
        onChange={(e) =>
          onChange(e.target.value ? Number(e.target.value) : null)
        }
      >
        {clinic !== undefined && (
          <option value="">Clinic default ({clinic} min)</option>
        )}
        {LENGTHS.map((m) => (
          <option key={m} value={m}>
            {m} min
          </option>
        ))}
      </select>
    </label>
  );
}

function DoctorForm({
  doctor: d,
  defaults,
  onChange,
  busy,
  error,
  onSave,
  onCancel,
}: {
  doctor: Doctor;
  defaults: Defaults;
  onChange: (d: Doctor) => void;
  busy: boolean;
  error: string;
  onSave: () => void;
  onCancel: () => void;
}) {
  const set = (patch: Partial<Doctor>) => onChange({ ...d, ...patch });
  const text = (
    key: "name" | "role_title" | "qualifications" | "photo",
    label: string,
    max: number,
  ) => (
    <label style={{ display: "grid", gap: 4 }}>
      <span className="sub2">{label}</span>
      <input
        className="f"
        maxLength={max}
        value={d[key]}
        onChange={(e) => set({ [key]: e.target.value })}
      />
    </label>
  );
  const clash = clashOf(d);

  return (
    <div className="card" style={{ padding: 16, maxWidth: 760 }}>
      <b>{d.id ? `Edit ${d.name}` : "Add a doctor"}</b>

      <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
        {text("name", "Name, e.g. Dr. Asha Rao", 100)}
        {text("role_title", "Title, e.g. Senior Consultant", 100)}
        {text(
          "qualifications",
          "Qualifications, e.g. MBBS, MD (Dermatology)",
          300,
        )}
        {text("photo", "Photo link (https://…, optional)", 300)}
        <label style={{ display: "grid", gap: 4 }}>
          <span className="sub2">About (optional)</span>
          <textarea
            className="f"
            rows={3}
            maxLength={1000}
            value={d.about}
            onChange={(e) => set({ about: e.target.value })}
          />
        </label>
        <div>
          <span className="sub2">
            Figures shown on the doctor&apos;s card (up to 6)
          </span>
          {d.stats.map((s, j) => (
            <div key={j} style={row}>
              <input
                className="f"
                placeholder="Value, e.g. 20+"
                maxLength={20}
                value={s.value}
                onChange={(e) =>
                  set({
                    stats: d.stats.map((x, k) =>
                      k === j ? { ...x, value: e.target.value } : x,
                    ),
                  })
                }
              />
              <input
                className="f"
                placeholder="Label, e.g. Years experience"
                maxLength={40}
                value={s.label}
                onChange={(e) =>
                  set({
                    stats: d.stats.map((x, k) =>
                      k === j ? { ...x, label: e.target.value } : x,
                    ),
                  })
                }
              />
              <button
                className="btn g"
                aria-label="Remove"
                onClick={() =>
                  set({ stats: d.stats.filter((_, k) => k !== j) })
                }
              >
                ✕
              </button>
            </div>
          ))}
          {d.stats.length < 6 && (
            <button
              className="pill"
              style={{ marginTop: 6 }}
              onClick={() =>
                set({ stats: [...d.stats, { label: "", value: "" }] })
              }
            >
              + Add figure
            </button>
          )}
        </div>
        <label className="row" style={{ gap: 8 }}>
          <input
            type="checkbox"
            checked={d.active}
            onChange={(e) => set({ active: e.target.checked })}
          />
          Active (shown to patients and bookable)
        </label>
      </div>

      <p className="sub2" style={{ margin: "16px 0 0" }}>
        <b>Slot lengths</b>
      </p>
      <div style={row}>
        <LengthSelect
          label="In-clinic visit"
          value={d.in_clinic_minutes}
          clinic={defaults.slot_minutes}
          onChange={(v) => set({ in_clinic_minutes: v })}
        />
        <LengthSelect
          label="Online consult"
          value={d.online_minutes}
          clinic={defaults.online_slot_minutes}
          onChange={(v) => set({ online_minutes: v })}
        />
      </div>

      <HoursEditor
        title="In-clinic hours"
        hours={d.in_clinic}
        onChange={(h) => set({ in_clinic: h })}
      />
      <HoursEditor
        title="Online hours"
        hours={d.online}
        onChange={(h) => set({ online: h })}
      />
      <p className="sub2" style={{ margin: "6px 0 0", fontSize: "var(--fs-small)" }}>
        In-clinic and online hours can be the same. When a time is booked for
        one, it is no longer offered for the other.
      </p>
      {d.calcom && (
        <p className="sub2" style={{ margin: "6px 0 0", fontSize: "var(--fs-small)" }}>
          Connected to Cal.com: online hours, leave and the online length are
          sent there when you save.
        </p>
      )}

      <LeaveEditor leave={d.leave} onChange={(l) => set({ leave: l })} />

      {clash && (
        <p className="warnbox" style={{ marginTop: 12 }}>
          {clash}
        </p>
      )}
      {error && error !== clash && (
        <p role="alert" style={{ color: "var(--err)", margin: "12px 0 0" }}>
          {error}
        </p>
      )}
      <div className="row" style={{ gap: 8, marginTop: 16 }}>
        <button
          className="btn"
          disabled={busy || d.name.trim().length < 2}
          onClick={onSave}
        >
          {busy ? "Saving…" : d.id ? "Save doctor" : "Add doctor"}
        </button>
        <button className="btn g" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
