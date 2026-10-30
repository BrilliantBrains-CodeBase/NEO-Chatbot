"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";

// Login & security → Clinics (BB Admin): every clinic in the one project, Add clinic (the next free code, a copy
// of another clinic's setup and chat, an optional first manager invite) and Deactivate / Activate.

type Clinic = {
  id: string;
  name: string;
  bot_name: string;
  active: boolean;
  is_test: boolean;
  members: number;
};

const EMPTY = {
  name: "",
  bot_name: "",
  copy_from: "CL01",
  phone: "",
  whatsapp: "",
  website: "",
  manager_name: "",
  manager_email: "",
};

export default function ClinicsCard() {
  const { toast } = useCrm();
  const [list, setList] = useState<Clinic[] | null>(null);
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [members, setMembers] = useState<string | null>(null); // the clinic whose members are open

  useEffect(() => {
    let live = true;
    api<Clinic[]>("/v1/crm/clinics").then(
      (x) => live && setList(x),
      (e) =>
        live && setError(e instanceof ApiError ? e.message : "Could not load."),
    );
    return () => {
      live = false;
    };
  }, []);

  async function call(
    path: string,
    method: string,
    body: object | undefined,
    done: string,
  ) {
    setBusy(true);
    setError("");
    try {
      setList(
        await api<Clinic[]>(`/v1/crm/clinics${path}`, {
          method,
          body: body ? JSON.stringify(body) : undefined,
        }),
      );
      toast(done);
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

  const set = (k: keyof typeof EMPTY) => (e: { target: { value: string } }) =>
    setForm({ ...form, [k]: e.target.value });
  const ready =
    form.name.trim().length >= 2 && form.bot_name.trim().length >= 2;

  return (
    <section className="card" style={{ margin: "14px 0" }}>
      <div className="row" style={{ gap: 10, alignItems: "center" }}>
        <h3 style={{ margin: 0, flex: 1 }}>
          Clinics {list ? `(${list.length})` : ""}
        </h3>
        {open && !adding && (
          <button className="btn" onClick={() => setAdding(true)}>
            Add clinic
          </button>
        )}
        <button className="btn g" onClick={() => setOpen(!open)}>
          {open ? "Close" : "Open"}
        </button>
      </div>
      {open && adding && (
        <div className="card" style={{ marginTop: 10, padding: 12 }}>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <input
              className="f"
              style={{ flex: "1 1 200px" }}
              placeholder="Clinic name"
              maxLength={80}
              value={form.name}
              onChange={set("name")}
            />
            <input
              className="f"
              style={{ flex: "1 1 160px" }}
              placeholder="Bot name, e.g. Mira"
              maxLength={40}
              value={form.bot_name}
              onChange={set("bot_name")}
            />
            <select
              className="sel"
              value={form.copy_from}
              onChange={set("copy_from")}
              title="Copy setup and chat from"
            >
              {(list ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  Copy from {c.name} ({c.id})
                </option>
              ))}
            </select>
          </div>
          <div
            className="row"
            style={{ gap: 8, flexWrap: "wrap", marginTop: 8 }}
          >
            <input
              className="f"
              style={{ flex: "1 1 160px" }}
              placeholder="Phone, e.g. +919876543210"
              value={form.phone}
              onChange={set("phone")}
            />
            <input
              className="f"
              style={{ flex: "1 1 160px" }}
              placeholder="WhatsApp, e.g. +919876543210"
              value={form.whatsapp}
              onChange={set("whatsapp")}
            />
            <input
              className="f"
              style={{ flex: "1 1 200px" }}
              placeholder="https://clinic-website.com"
              value={form.website}
              onChange={set("website")}
            />
          </div>
          <div
            className="row"
            style={{ gap: 8, flexWrap: "wrap", marginTop: 8 }}
          >
            <input
              className="f"
              style={{ flex: "1 1 160px" }}
              placeholder="First manager's name (optional)"
              maxLength={100}
              value={form.manager_name}
              onChange={set("manager_name")}
            />
            <input
              className="f"
              style={{ flex: "1 1 200px" }}
              type="email"
              placeholder="First manager's email (optional)"
              value={form.manager_email}
              onChange={set("manager_email")}
            />
          </div>
          <p className="sub2" style={{ margin: "8px 0" }}>
            Copies the clinic&apos;s hours, slots, canvas, Appearance, Templates
            and Menu wording (not its contact details, services, doctors,
            websites or keys). The new clinic gets the next free code; edit its
            Dashboard after.
          </p>
          <div className="row" style={{ gap: 8 }}>
            <button
              className="btn"
              disabled={busy || !ready}
              onClick={async () => {
                const body = Object.fromEntries(
                  Object.entries(form).map(([k, v]) => [k, v.trim() || null]),
                );
                if (await call("", "POST", body, `${form.name} added`)) {
                  setForm(EMPTY);
                  setAdding(false);
                }
              }}
            >
              {busy ? "Adding…" : "Add clinic"}
            </button>
            <button className="btn g" onClick={() => setAdding(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {open &&
        list?.map((c) => (
          <div
            key={c.id}
            className="row"
            style={{
              gap: 10,
              alignItems: "center",
              flexWrap: "wrap",
              borderTop: "1px solid var(--line)",
              padding: "10px 0",
            }}
          >
            <b style={{ minWidth: 56 }}>{c.id}</b>
            <span style={{ flex: "1 1 200px" }}>
              {c.name}{" "}
              <span className="sub2">
                · bot {c.bot_name} · {c.members} members
              </span>
            </span>
            {c.is_test && <span className="badge b-bk">Test</span>}
            <span className={`badge ${c.active ? "b-vi" : "b-in"}`}>
              {c.active ? "Active" : "Inactive"}
            </span>
            <button
              className="btn g"
              onClick={() => setMembers(members === c.id ? null : c.id)}
            >
              {members === c.id ? "Hide members" : "Members"}
            </button>
            {!c.is_test && c.id !== "CL01" && (
              <button
                className="btn g"
                disabled={busy}
                onClick={() => {
                  const typed = window.prompt(
                    `Delete ${c.name} for good? Only a clinic with no leads, chats, doctors or integrations can be deleted. Type ${c.id} to confirm.`,
                  );
                  if (typed?.trim().toUpperCase() === c.id)
                    void call(
                      `/${c.id}`,
                      "DELETE",
                      undefined,
                      `${c.name} deleted`,
                    );
                }}
              >
                Delete
              </button>
            )}
            {!c.is_test && (
              <button
                className="btn g"
                disabled={busy}
                onClick={() => {
                  if (
                    c.active &&
                    !window.confirm(
                      `Deactivate ${c.name}? Its chat and CRM stop; nothing is deleted.`,
                    )
                  )
                    return;
                  void call(
                    `/${c.id}`,
                    "PUT",
                    { active: !c.active },
                    c.active ? "Deactivated" : "Activated",
                  );
                }}
              >
                {c.active ? "Deactivate" : "Activate"}
              </button>
            )}
          </div>
        ))}
      {open && members && <Members clinic={members} />}
      {error && (
        <p className="warnbox" style={{ marginTop: 6 }}>
          {error}
        </p>
      )}
    </section>
  );
}

type Member = {
  id: string;
  name: string;
  email: string;
  role_label: string;
  active: boolean;
};
const ROLES: [string, string][] = [
  ["clinic_manager", "Clinic Manager"],
  ["front_desk", "Front Desk"],
  ["doctor", "Doctor"],
];

/** One clinic's members, and Add member (an invite email; someone with a login gets the role at once). BB Admins
 * always have full access to every clinic, so they are not listed per clinic. */
function Members({ clinic }: { clinic: string }) {
  const { me, toast } = useCrm();
  const [list, setList] = useState<Member[] | null>(null);
  const [form, setForm] = useState({
    name: "",
    email: "",
    role: "clinic_manager",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    api<{ members: Member[] }>(`/v1/crm/team/${clinic}`).then(
      (t) => live && setList(t.members),
      (e) =>
        live && setError(e instanceof ApiError ? e.message : "Could not load."),
    );
    return () => {
      live = false;
    };
  }, [clinic]);

  async function add() {
    setBusy(true);
    setError("");
    try {
      const t = await api<{ members: Member[] }>(
        `/v1/crm/team/${clinic}/invite`,
        {
          method: "POST",
          body: JSON.stringify({
            full_name: form.name.trim(),
            email: form.email.trim(),
            role: form.role,
            clinics: [clinic],
          }),
        },
      );
      setList(t.members);
      setForm({ name: "", email: "", role: "clinic_manager" });
      toast(`${form.email.trim()} added: a new person gets an invite email; an existing login has access now`);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not add. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ marginTop: 8, padding: 12 }}>
      <b>Members of {clinic}</b>
      <p className="sub2" style={{ margin: "4px 0 8px" }}>
        {me?.name} (you, BB Admin) and every BB Admin: full access to this
        clinic.
      </p>
      {list?.length === 0 && <p className="sub2">No members yet.</p>}
      {list?.map((m) => (
        <p key={m.id} style={{ margin: "3px 0", fontSize: 13 }}>
          <b>{m.name}</b> · {m.email} · {m.role_label}
          {!m.active && (
            <span className="badge b-in" style={{ marginLeft: 6 }}>
              Disabled
            </span>
          )}
        </p>
      ))}
      <div className="row" style={{ gap: 8, flexWrap: "wrap", marginTop: 8 }}>
        <input
          className="f"
          style={{ flex: "1 1 160px" }}
          placeholder="Full name"
          maxLength={100}
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <input
          className="f"
          style={{ flex: "1 1 200px" }}
          type="email"
          placeholder="name@clinic.com"
          maxLength={120}
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />
        <select
          className="sel"
          value={form.role}
          onChange={(e) => setForm({ ...form, role: e.target.value })}
        >
          {ROLES.map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <button
          className="btn"
          disabled={
            busy || form.name.trim().length < 2 || !form.email.includes("@")
          }
          onClick={() => void add()}
        >
          Add member
        </button>
      </div>
      {error && (
        <p className="warnbox" style={{ marginTop: 6 }}>
          {error}
        </p>
      )}
    </div>
  );
}
