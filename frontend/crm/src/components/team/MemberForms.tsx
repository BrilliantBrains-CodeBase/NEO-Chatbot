"use client";

import { useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { givableRoles, message, ROLES, roleLabel, type Member, type Team } from "./shared";

// The pop-ups that add or change a member. Front Desk works in one clinic, so it picks one clinic; a Super Admin
// has every clinic and picks none.

type Change = (path: string, method: string, body?: object, at?: string) => Promise<void>;

function ClinicPicker({
  team,
  role,
  value,
  onChange,
}: {
  team: Team;
  role: string;
  value: string[];
  onChange: (clinics: string[]) => void;
}) {
  const clinics = Object.entries(team.managed);
  if (role === "bb_admin")
    return <p className="tm-note full">A Super Admin has every clinic.</p>;
  if (clinics.length < 2) return null;
  if (role === "front_desk")
    return (
      <label className="tm-field full">
        Clinic
        <select
          className="f"
          value={value.length === 1 ? value[0] : ""}
          onChange={(e) => onChange([e.target.value])}
        >
          {value.length !== 1 && <option value="">Choose one clinic</option>}
          {clinics.map(([id, name]) => (
            <option key={id} value={id}>
              {name} ({id})
            </option>
          ))}
        </select>
        <span className="tm-hint">Front Desk works in one clinic only, so patients reach the right one.</span>
      </label>
    );
  return (
    <fieldset className="tm-field full tm-boxes">
      <legend>Clinics</legend>
      {clinics.map(([id, name]) => (
        <label key={id}>
          <input
            type="checkbox"
            checked={value.includes(id)}
            onChange={(e) =>
              onChange(e.target.checked ? [...value, id] : value.filter((c) => c !== id))
            }
          />
          {name} ({id})
        </label>
      ))}
    </fieldset>
  );
}

const RoleField = ({
  roles,
  value,
  onChange,
}: {
  roles: string[];
  value: string;
  onChange: (role: string) => void;
}) => (
  <label className="tm-field full">
    Role
    <select className="f" value={value} onChange={(e) => onChange(e.target.value)}>
      {roles.map((r) => (
        <option key={r} value={r}>
          {roleLabel(r)}
        </option>
      ))}
    </select>
    <span className="tm-hint">{ROLES[value]?.about}</span>
  </label>
);

export function InviteForm({
  team,
  clinicId,
  superAdmin,
  change,
  onClose,
}: {
  team: Team;
  clinicId: string;
  superAdmin: boolean;
  change: Change;
  onClose: () => void;
}) {
  const { toast } = useCrm();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("front_desk");
  const [clinics, setClinics] = useState([clinicId]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ready =
    name.trim().length >= 2 && /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email.trim()) && clinics.length > 0;

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError("");
        try {
          await change("/invite", "POST", {
            full_name: name.trim(),
            email: email.trim(),
            role,
            clinics,
          });
          toast(`${email.trim()} added`);
          onClose();
        } catch (err) {
          setError(message(err, "Could not invite. Please try again."));
          setBusy(false);
        }
      }}
    >
      <div className="tm-form">
        <label className="tm-field">
          Full name
          <input
            className="f"
            autoFocus
            maxLength={100}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="tm-field">
          Email
          <input
            className="f"
            type="email"
            maxLength={120}
            placeholder="name@clinic.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <RoleField
          roles={givableRoles(team, superAdmin)}
          value={role}
          onChange={(r) => {
            setRole(r);
            if (r === "front_desk" && clinics.length !== 1) setClinics([clinics[0] ?? clinicId]);
          }}
        />
        <ClinicPicker team={team} role={role} value={clinics} onChange={setClinics} />
        <p className="tm-note full">
          They get an email to set their password. Someone who already has a login gets access straight away, and
          keeps any role they already have.
        </p>
      </div>
      {error && (
        <div className="warnbox" role="alert" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}
      <div className="tm-actions" style={{ marginTop: 16 }}>
        <button type="button" className="btn g" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="btn" disabled={busy || !ready}>
          {busy ? "Sending…" : "Send invite"}
        </button>
      </div>
    </form>
  );
}

export function EditForm({
  member,
  team,
  clinic,
  clinicId,
  superAdmin,
  change,
  onClose,
}: {
  member: Member;
  team: Team;
  clinic: string;
  clinicId: string;
  superAdmin: boolean;
  change: Change;
  onClose: () => void;
}) {
  const { toast } = useCrm();
  const [role, setRole] = useState(member.role);
  const [clinics, setClinics] = useState(member.clinics);
  const [doctor, setDoctor] = useState(member.doctor_id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const roles = [...new Set([...givableRoles(team, superAdmin), member.role])];
  const sameClinics =
    clinics.length === member.clinics.length && clinics.every((c) => member.clinics.includes(c));
  const records = team.doctors.filter((d) => !d.linked_to || d.linked_to === member.id);
  const unchanged =
    role === member.role && sameClinics && doctor === (member.doctor_id ?? "");
  const tooMany = role === "front_desk" && clinics.length > 1;

  async function save() {
    setBusy(true);
    setError("");
    // The clinic to address them in once this is saved.
    const at = clinics.includes(clinicId) ? clinicId : (clinics[0] ?? clinicId);
    const member_ = `/members/${member.id}`;
    try {
      // Becoming Front Desk: first down to one clinic. Otherwise the role first, so new clinics get it.
      if (role === "front_desk" && !sameClinics) await change(`${member_}/clinics`, "PUT", { clinics });
      if (role !== member.role)
        await change(member_, "PUT", { role }, role === "front_desk" ? at : clinicId);
      if (role !== "front_desk" && role !== "bb_admin" && !sameClinics)
        await change(`${member_}/clinics`, "PUT", { clinics });
      if (role === "doctor" && doctor !== (member.doctor_id ?? "") && at === clinicId)
        await change(`${member_}/doctor`, "PUT", { doctor_id: doctor || null });
      toast("Saved");
      onClose();
    } catch (e) {
      setError(message(e, "Could not save. Please try again."));
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <p style={{ margin: "0 0 14px" }}>
        <b>{member.name}</b> · {member.email}
      </p>
      <div className="tm-form">
        <RoleField
          roles={roles}
          value={role}
          onChange={(r) => {
            setRole(r);
            if (r === "front_desk" && clinics.length > 1)
              setClinics([clinics.includes(clinicId) ? clinicId : clinics[0]]);
          }}
        />
        <ClinicPicker team={team} role={role} value={clinics} onChange={setClinics} />
        {role === "doctor" && (
          <label className="tm-field full">
            Doctor record in {clinic}
            <select className="f" value={doctor} onChange={(e) => setDoctor(e.target.value)}>
              <option value="">Not linked</option>
              {records.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
            <span className="tm-hint">
              Their appointments, patients and own hours come from this record. Without it they see none.
            </span>
          </label>
        )}
      </div>
      {tooMany && (
        <div className="warnbox" style={{ marginTop: 12 }}>
          Front Desk works in one clinic only. Keep one clinic.
        </div>
      )}
      {error && (
        <div className="warnbox" role="alert" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}
      <div className="tm-actions" style={{ marginTop: 16 }}>
        <button type="button" className="btn g" onClick={onClose}>
          Cancel
        </button>
        <button
          type="submit"
          className="btn"
          disabled={busy || unchanged || tooMany || clinics.length === 0}
        >
          {busy ? "Saving…" : "Save changes"}
        </button>
      </div>
    </form>
  );
}
