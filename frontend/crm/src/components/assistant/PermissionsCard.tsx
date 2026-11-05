"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";

// Dashboard → Team & access → Who sees what: hidden, view or edit for each screen and role. BB Admin edits the
// defaults for all clinics or this clinic's own rules; a Clinic Manager edits this clinic's Front Desk and
// Doctor columns (never above their own access). BB Admin always has everything.

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
type Person = { id: string; name: string; role: string };

const ROLE: Record<string, string> = {
  clinic_manager: "Clinic Manager",
  front_desk: "Front Desk",
  doctor: "Doctor",
};
const RANK: Level[] = ["hidden", "view", "edit"];

export default function PermissionsCard({
  clinicId,
  clinic,
  people,
}: {
  clinicId: string;
  clinic: string;
  people: Person[];
}) {
  const { toast } = useCrm();
  const [r, setR] = useState<Rules | null>(null);
  const [scope, setScope] = useState<"clinic" | "defaults">("clinic");
  const [open, setOpen] = useState(false);
  const [table, setTable] = useState<Table | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [grant, setGrant] = useState({
    user_id: "",
    screen: "",
    level: "view",
    until: "",
  });

  useEffect(() => {
    let live = true;
    api<Rules>(`/v1/crm/permissions/${clinicId}`).then(
      (x) => {
        if (!live) return;
        setR(x);
        setTable(x.effective);
      },
      (e) =>
        live && setError(e instanceof ApiError ? e.message : "Could not load."),
    );
    return () => {
      live = false;
    };
  }, [clinicId]);

  if (error && !r) return <div className="warnbox">{error}</div>;
  if (!r || !table) return null;

  const pick = (s: "clinic" | "defaults") => {
    setScope(s);
    setTable(s === "defaults" ? r.defaults : r.effective);
  };
  const editable = (role: string, screen: string, level: Level) => {
    if (role === "clinic_manager") return r.can_edit_managers;
    if (r.can_edit_defaults) return true;
    return (
      RANK.indexOf(level) <=
      RANK.indexOf(r.effective.clinic_manager[screen] ?? "hidden")
    );
  };

  async function save(next: Table | null) {
    setBusy(true);
    setError("");
    try {
      const url =
        scope === "defaults"
          ? `/v1/crm/permissions/defaults/${clinicId}`
          : `/v1/crm/permissions/${clinicId}`;
      const x = await api<Rules>(url, {
        method: "PUT",
        body: JSON.stringify({ rules: next ?? {} }),
      });
      setR(x);
      setTable(scope === "defaults" ? x.defaults : x.effective);
      toast(next ? "Saved" : `${clinic} now follows the defaults`);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function give() {
    setBusy(true);
    setError("");
    try {
      const x = await api<Rules>(`/v1/crm/permissions/${clinicId}/grants`, {
        method: "POST",
        body: JSON.stringify({
          ...grant,
          until: new Date(grant.until).toISOString(),
        }),
      });
      setR(x);
      setGrant({ user_id: "", screen: "", level: "view", until: "" });
      toast("Access given");
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function takeBack(id: string) {
    setBusy(true);
    try {
      setR(
        await api<Rules>(`/v1/crm/permissions/${clinicId}/grants/${id}`, {
          method: "DELETE",
        }),
      );
      toast("Access ended");
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const label = (key: string) =>
    r.screens.find((x) => x.key === key)?.label ?? key;
  // Only BB Admin gives a Clinic Manager extra access; BB Admins already have everything.
  const givable = people.filter(
    (p) =>
      p.role !== "bb_admin" &&
      (r.can_edit_managers || p.role !== "clinic_manager"),
  );
  const groups = ["CRM", "Dashboard"];
  return (
    <section className="card" style={{ marginBottom: 14 }}>
      <div
        className="row"
        style={{ gap: 10, alignItems: "center", flexWrap: "wrap" }}
      >
        <h3 style={{ margin: 0, flex: 1 }}>Who sees what</h3>
        {open && r.can_edit_defaults && (
          <select
            className="sel"
            value={scope}
            onChange={(e) => pick(e.target.value as "clinic" | "defaults")}
          >
            <option value="clinic">{clinic} only</option>
            <option value="defaults">Default for all clinics</option>
          </select>
        )}
        <button className="btn g" onClick={() => setOpen(!open)}>
          {open ? "Close" : "Open"}
        </button>
      </div>
      {open && (
        <>
          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "var(--fs-sec)",
              }}
            >
              <thead>
                <tr className="sub2" style={{ textAlign: "left" }}>
                  <th style={{ padding: "4px 6px 4px 0" }}>Screen</th>
                  {r.roles.map((role) => (
                    <th key={role}>{ROLE[role]}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {groups.map((g) => [
                  <tr key={g}>
                    <td
                      colSpan={4}
                      style={{ padding: "10px 0 4px", fontWeight: 700 }}
                    >
                      {g}
                    </td>
                  </tr>,
                  ...r.screens
                    .filter((s) => s.group === g)
                    .map((s) => (
                      <tr
                        key={s.key}
                        style={{ borderTop: "1px solid var(--line)" }}
                      >
                        <td style={{ padding: "4px 6px 4px 0" }}>{s.label}</td>
                        {r.roles.map((role) => (
                          <td key={role} style={{ padding: "3px 4px" }}>
                            <select
                              className="sel"
                              disabled={
                                busy || !editable(role, s.key, "hidden")
                              }
                              value={table[role][s.key]}
                              onChange={(e) =>
                                setTable({
                                  ...table,
                                  [role]: {
                                    ...table[role],
                                    [s.key]: e.target.value as Level,
                                  },
                                })
                              }
                            >
                              {RANK.map((lv) => (
                                <option
                                  key={lv}
                                  value={lv}
                                  disabled={!editable(role, s.key, lv)}
                                >
                                  {lv === "hidden"
                                    ? "Hidden"
                                    : lv === "view"
                                      ? "View"
                                      : "Edit"}
                                </option>
                              ))}
                            </select>
                          </td>
                        ))}
                      </tr>
                    )),
                ])}
              </tbody>
            </table>
          </div>
          <div className="row" style={{ gap: 8, marginTop: 10 }}>
            <button
              className="btn"
              disabled={busy}
              onClick={() => void save(table)}
            >
              Save
            </button>
            {scope === "clinic" && Object.keys(r.own).length > 0 && (
              <button
                className="btn g"
                disabled={busy}
                onClick={() => {
                  if (
                    window.confirm(
                      `Drop ${clinic}'s own rules and follow the defaults?`,
                    )
                  )
                    void save(null);
                }}
              >
                Use the defaults
              </button>
            )}
          </div>
          <h4 style={{ margin: "16px 0 4px" }}>Access for a limited time</h4>
          <p className="sub2" style={{ margin: "0 0 8px" }}>
            Give one person a screen until a date and time; it ends by itself
            (their role&apos;s rule applies again).
          </p>
          {r.grants.map((g) => (
            <p key={g.id} style={{ margin: "3px 0", fontSize: "var(--fs-sec)" }}>
              <b>{g.name}</b> · {label(g.screen)} ·{" "}
              {g.level === "edit" ? "Edit" : "View"} · until{" "}
              {new Date(g.until).toLocaleString("en-IN")}
              {g.given_by ? ` · given by ${g.given_by}` : ""}{" "}
              <button
                className="btn g"
                disabled={busy}
                onClick={() => void takeBack(g.id)}
              >
                End now
              </button>
            </p>
          ))}
          <div
            className="row"
            style={{ gap: 8, flexWrap: "wrap", marginTop: 6 }}
          >
            <select
              className="sel"
              value={grant.user_id}
              onChange={(e) => setGrant({ ...grant, user_id: e.target.value })}
            >
              <option value="">Person…</option>
              {givable.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <select
              className="sel"
              value={grant.screen}
              onChange={(e) => setGrant({ ...grant, screen: e.target.value })}
            >
              <option value="">Screen…</option>
              {r.screens.map((x) => (
                <option key={x.key} value={x.key}>
                  {x.group === "Dashboard" ? `Dashboard: ${x.label}` : x.label}
                </option>
              ))}
            </select>
            <select
              className="sel"
              value={grant.level}
              onChange={(e) => setGrant({ ...grant, level: e.target.value })}
            >
              <option value="view">View</option>
              <option value="edit">Edit</option>
            </select>
            <input
              className="f"
              type="datetime-local"
              value={grant.until}
              onChange={(e) => setGrant({ ...grant, until: e.target.value })}
            />
            <button
              className="btn"
              disabled={busy || !grant.user_id || !grant.screen || !grant.until}
              onClick={() => void give()}
            >
              Give access
            </button>
          </div>
          {error && (
            <p className="warnbox" style={{ marginTop: 6 }}>
              {error}
            </p>
          )}
        </>
      )}
    </section>
  );
}
