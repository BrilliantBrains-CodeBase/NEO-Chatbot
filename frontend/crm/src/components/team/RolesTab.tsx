"use client";

import { useEffect, useState } from "react";
import Loading from "@/components/crm/Loading";
import { useCrm } from "@/components/crm/CrmProvider";
import { api } from "@/lib/api";
import { Confirm, dateTime, message, ROLES, roleLabel, RowMenu, type Member } from "./shared";

// What each role can do. Super Admin edits the defaults for all clinics or one clinic's own rules; an Admin edits
// their clinic's Front Desk and Doctor columns, never above their own access. Super Admin always has everything.

type Level = "hidden" | "view" | "edit";
type Table = Record<string, Record<string, Level>>;
type Rules = {
  screens: { key: string; label: string; group: string }[];
  roles: string[];
  defaults: Table;
  effective: Table;
  own: Table;
  can_edit_defaults: boolean;
  can_edit_managers: boolean;
  grants: {
    id: string;
    user_id: string;
    name: string;
    screen: string;
    level: Level;
    until: string;
    given_by: string | null;
  }[];
};

const RANK: Level[] = ["hidden", "view", "edit"];
const LEVEL: Record<Level, string> = { hidden: "Hidden", view: "View", edit: "Edit" };

export default function RolesTab({
  clinicId,
  clinic,
  people,
}: {
  clinicId: string;
  clinic: string;
  people: Member[];
}) {
  const { toast, openModal, closeModal } = useCrm();
  const [r, setR] = useState<Rules | null>(null);
  const [scope, setScope] = useState<"clinic" | "defaults">("clinic");
  const [table, setTable] = useState<Table | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const url = `/v1/crm/permissions/${clinicId}`;

  useEffect(() => {
    let live = true;
    api<Rules>(url).then(
      (x) => {
        if (!live) return;
        setR(x);
        setTable(x.effective);
      },
      (e) => live && setError(message(e, "Could not load the permissions.")),
    );
    return () => {
      live = false;
    };
  }, [url]);

  if (error && !r) return <div className="warnbox">{error}</div>;
  if (!r || !table) return <Loading />;

  const base = scope === "defaults" ? r.defaults : r.effective;
  const dirty = JSON.stringify(table) !== JSON.stringify(base);
  const allowed = (role: string, screen: string, level: Level) => {
    if (role === "clinic_manager") return r.can_edit_managers;
    if (r.can_edit_defaults) return true;
    return RANK.indexOf(level) <= RANK.indexOf(r.effective.clinic_manager[screen] ?? "hidden");
  };

  async function save(next: Table | null) {
    setBusy(true);
    setError("");
    try {
      const x = await api<Rules>(
        scope === "defaults" ? `/v1/crm/permissions/defaults/${clinicId}` : url,
        { method: "PUT", body: JSON.stringify({ rules: next ?? {} }) },
      );
      setR(x);
      setTable(scope === "defaults" ? x.defaults : x.effective);
      toast(next ? "Permissions saved" : `${clinic} now follows the defaults`);
    } catch (e) {
      setError(message(e, "Could not save. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  const label = (key: string) => r.screens.find((s) => s.key === key)?.label ?? key;
  // Only a Super Admin gives an Admin extra access; Super Admins already have everything.
  const givable = people.filter(
    (p) => p.role !== "bb_admin" && (r.can_edit_managers || p.role !== "clinic_manager"),
  );

  return (
    <>
      <div className="tm-roles">
        {Object.entries(ROLES).map(([key, role]) => (
          <div key={key} className="tm-role">
            <span className={`badge ${role.badge}`}>{role.label}</span>
            <p>{role.about}</p>
          </div>
        ))}
      </div>

      <div className="tm-head">
        <div>
          <h2>Who sees what</h2>
          <p>
            Hidden: not shown. View: can look, not change. Edit: can change.
            {scope === "clinic" && Object.keys(r.own).length > 0 && ` ${clinic} has its own rules.`}
          </p>
        </div>
        {r.can_edit_defaults && (
          <select
            className="sel"
            aria-label="Which rules to edit"
            value={scope}
            disabled={dirty}
            title={dirty ? "Save or discard your changes first" : undefined}
            onChange={(e) => {
              const s = e.target.value as "clinic" | "defaults";
              setScope(s);
              setTable(s === "defaults" ? r.defaults : r.effective);
            }}
          >
            <option value="clinic">{clinic} only</option>
            <option value="defaults">Default for all clinics</option>
          </select>
        )}
      </div>

      <div className="tw">
        <table className="tm-table tm-matrix">
          <thead>
            <tr>
              <th>Screen</th>
              {r.roles.map((role) => (
                <th key={role}>{roleLabel(role)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {["CRM", "Dashboard"].map((g) => [
              <tr key={g} className="tm-group">
                <td colSpan={r.roles.length + 1}>{g}</td>
              </tr>,
              ...r.screens
                .filter((s) => s.group === g)
                .map((s) => (
                  <tr key={s.key}>
                    <td>{s.label}</td>
                    {r.roles.map((role) => {
                      const value = table[role][s.key];
                      return (
                        <td key={role}>
                          <select
                            className={`sel tm-level ${value}`}
                            aria-label={`${s.label} for ${roleLabel(role)}`}
                            disabled={busy || !allowed(role, s.key, "hidden")}
                            value={value}
                            onChange={(e) =>
                              setTable({
                                ...table,
                                [role]: { ...table[role], [s.key]: e.target.value as Level },
                              })
                            }
                          >
                            {RANK.map((lv) => (
                              <option key={lv} value={lv} disabled={!allowed(role, s.key, lv)}>
                                {LEVEL[lv]}
                              </option>
                            ))}
                          </select>
                        </td>
                      );
                    })}
                  </tr>
                )),
            ])}
          </tbody>
        </table>
      </div>

      {error && (
        <div className="warnbox" role="alert" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}
      <div className={`tm-savebar${dirty ? " on" : ""}`}>
        {dirty && <span>You have unsaved changes.</span>}
        {scope === "clinic" && !dirty && Object.keys(r.own).length > 0 && (
          <button
            type="button"
            className="btn g"
            disabled={busy}
            onClick={() =>
              openModal({
                title: "Use the defaults",
                body: (
                  <Confirm
                    text={`Drop ${clinic}'s own rules and follow the defaults?`}
                    action="Use the defaults"
                    onConfirm={() => save(null)}
                    onClose={closeModal}
                  />
                ),
              })
            }
          >
            Use the defaults
          </button>
        )}
        {dirty && (
          <>
            <button type="button" className="btn g" disabled={busy} onClick={() => setTable(base)}>
              Discard
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => void save(table)}>
              {busy ? "Saving…" : "Save changes"}
            </button>
          </>
        )}
      </div>

      <div className="tm-head" style={{ marginTop: 24 }}>
        <div>
          <h2>Temporary access</h2>
          <p>Give one person a screen until a date and time. It ends by itself.</p>
        </div>
        <button
          type="button"
          className="btn g"
          disabled={givable.length === 0}
          onClick={() =>
            openModal({
              title: "Give temporary access",
              body: (
                <GrantForm
                  url={url}
                  screens={r.screens}
                  people={givable}
                  onDone={(x) => {
                    setR(x);
                    toast("Access given");
                    closeModal();
                  }}
                  onClose={closeModal}
                />
              ),
            })
          }
        >
          Give access
        </button>
      </div>
      <div className="tw">
        <table className="tm-table">
          <thead>
            <tr>
              <th>Person</th>
              <th>Screen</th>
              <th>Level</th>
              <th>Ends</th>
              <th>Given by</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {r.grants.length === 0 && (
              <tr>
                <td colSpan={6} className="tm-none">
                  No temporary access right now.
                </td>
              </tr>
            )}
            {r.grants.map((g) => (
              <tr key={g.id}>
                <td className="nm">{g.name}</td>
                <td>{label(g.screen)}</td>
                <td>{LEVEL[g.level]}</td>
                <td className="tm-sub">{dateTime(g.until)}</td>
                <td className="tm-sub">{g.given_by ?? "—"}</td>
                <td className="tm-end">
                  <RowMenu
                    label={`Actions for ${g.name}'s access`}
                    items={[
                      {
                        label: "End now",
                        danger: true,
                        onClick: () =>
                          void api<Rules>(`${url}/grants/${g.id}`, { method: "DELETE" }).then(
                            (x) => {
                              setR(x);
                              toast("Access ended");
                            },
                            (e) => setError(message(e, "Could not end this access.")),
                          ),
                      },
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function GrantForm({
  url,
  screens,
  people,
  onDone,
  onClose,
}: {
  url: string;
  screens: Rules["screens"];
  people: Member[];
  onDone: (r: Rules) => void;
  onClose: () => void;
}) {
  const [userId, setUserId] = useState("");
  const [screen, setScreen] = useState("");
  const [level, setLevel] = useState("view");
  const [until, setUntil] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError("");
        try {
          onDone(
            await api<Rules>(`${url}/grants`, {
              method: "POST",
              body: JSON.stringify({
                user_id: userId,
                screen,
                level,
                until: new Date(until).toISOString(),
              }),
            }),
          );
        } catch (err) {
          setError(message(err, "Could not give access. Please try again."));
          setBusy(false);
        }
      }}
    >
      <div className="tm-form">
        <label className="tm-field full">
          Person
          <select className="f" value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="">Choose someone</option>
            {people.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({roleLabel(p.role)})
              </option>
            ))}
          </select>
        </label>
        <label className="tm-field">
          Screen
          <select className="f" value={screen} onChange={(e) => setScreen(e.target.value)}>
            <option value="">Choose a screen</option>
            {screens.map((s) => (
              <option key={s.key} value={s.key}>
                {s.group === "Dashboard" ? `Dashboard: ${s.label}` : s.label}
              </option>
            ))}
          </select>
        </label>
        <label className="tm-field">
          Level
          <select className="f" value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="view">View</option>
            <option value="edit">Edit</option>
          </select>
        </label>
        <label className="tm-field full">
          Ends
          <input
            className="f"
            type="datetime-local"
            value={until}
            onChange={(e) => setUntil(e.target.value)}
          />
          <span className="tm-hint">At most 90 days from now.</span>
        </label>
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
        <button type="submit" className="btn" disabled={busy || !userId || !screen || !until}>
          {busy ? "Giving…" : "Give access"}
        </button>
      </div>
    </form>
  );
}
