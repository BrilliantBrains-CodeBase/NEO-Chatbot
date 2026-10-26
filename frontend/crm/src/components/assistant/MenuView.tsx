"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError } from "@/lib/api";
import { CHAT_ICONS, ICON_GROUPS } from "./chatIcons";

// Dashboard → Menu buttons: the chat's opening (welcome message, trust figures) and its main buttons with
// their sub-buttons, plus buttons per row and the filled button. Saved as a draft; live after Publish.
// Typed example phrases per button come in the next step (they need staff approval and the button tests).

type Sub = { label: string; action: string; value: string; visible: boolean };
type Main = Sub & {
  icon: string;
  message: string;
  variant: string;
  sub: Sub[];
};
type Menu = {
  welcome: string;
  show_figures: boolean;
  figures: { value: string; label: string }[];
  fallback: string;
  buttons: Main[];
};
type Template = { id: string; columns: number; filled_button: string };
type Settings = {
  draft: {
    menu: Menu;
    template: Template;
    appearance: {
      look: { name: string };
      colours: { main: string; highlight: string };
    };
  };
  changed: boolean;
};

// What a button can do, and what its value means.
const ACTIONS: [string, string, string][] = [
  ["submenu", "Show sub-buttons", ""],
  ["book", "Start booking (in-clinic)", ""],
  ["online", "Start online consultation", ""],
  ["cancel", "Start cancel appointment", ""],
  ["reschedule", "Start reschedule", ""],
  [
    "callback",
    "Start call back",
    "Topic (optional), e.g. International patient",
  ],
  ["treatments", "Show all treatments", ""],
  ["treatment", "One treatment", "Treatment name, e.g. Beard Transplant"],
  [
    "page",
    "Existing chat page",
    "Page name from today's chat, e.g. doc_sandeep",
  ],
  ["answer", "Show a message", "The message"],
  ["link", "Open a link", "https://…"],
  ["whatsapp", "Open WhatsApp", "https://wa.me/91… with the message"],
  ["call", "Call", "Phone number, e.g. +919731207940"],
  ["emergency", "Emergency", ""],
];
const ACTION_HINT = Object.fromEntries(ACTIONS.map(([k, , hint]) => [k, hint]));
// Older icon names in the clinic's content file, as names in the icon set.
const ALIAS: Record<string, string> = {
  cal: "calendar",
  steth: "stetho",
  sos: "alert",
};
const iconKey = (name: string) => ALIAS[name] ?? name;

/** One icon of the chat's icon set (static SVG shapes from the approved design). */
function ChatIcon({ name, size = 18 }: { name: string; size?: number }) {
  const shapes = CHAT_ICONS[iconKey(name)];
  if (!shapes) return null;
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: shapes }}
    />
  );
}

/** The icon picker: the chosen icon on a button; it opens a small grid of the icon set, grouped as in the
 * design. Closes with ✕, Esc, a click outside, or by choosing. */
function IconPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (e: MouseEvent) =>
      !box.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  const cell = (k: string) => {
    const on = iconKey(value) === k;
    return (
      <button
        key={k || "none"}
        type="button"
        title={k || "No icon"}
        aria-label={k || "No icon"}
        aria-pressed={on}
        onClick={() => {
          onChange(k);
          setOpen(false);
        }}
        style={{
          width: 30,
          height: 30,
          display: "grid",
          placeItems: "center",
          borderRadius: 8,
          cursor: "pointer",
          color: "var(--ink)",
          fontSize: 11,
          background: on ? "var(--tint)" : "#fff",
          border: `1px solid ${on ? "var(--brand)" : "var(--line)"}`,
        }}
      >
        {k ? <ChatIcon name={k} size={16} /> : "✕"}
      </button>
    );
  };
  return (
    <div ref={box} className="fld" style={{ position: "relative" }}>
      Icon
      <button
        type="button"
        className="f"
        onClick={() => setOpen(!open)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          textAlign: "left",
          cursor: "pointer",
        }}
      >
        {value ? <ChatIcon name={value} size={18} /> : null}
        <span>{value ? "Change icon" : "Choose an icon"}</span>
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Choose an icon"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            zIndex: 20,
            width: 330,
            marginTop: 4,
            background: "#fff",
            border: "1px solid var(--line)",
            borderRadius: 12,
            boxShadow: "0 14px 30px -16px rgba(22,32,46,.45)",
            fontWeight: 400,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              padding: "8px 10px",
              borderBottom: "1px solid var(--line)",
            }}
          >
            <b style={{ flex: 1, fontSize: 13 }}>Choose an icon</b>
            <button
              type="button"
              aria-label="Close"
              onClick={() => setOpen(false)}
              style={{
                border: 0,
                background: "none",
                cursor: "pointer",
                fontSize: 15,
              }}
            >
              ✕
            </button>
          </div>
          <div
            style={{ maxHeight: 280, overflowY: "auto", padding: "8px 10px" }}
          >
            {ICON_GROUPS.map(([group, keys]) => (
              <div key={group} style={{ marginBottom: 8 }}>
                <div
                  className="sub2"
                  style={{
                    fontWeight: 700,
                    fontSize: 10.5,
                    letterSpacing: ".06em",
                    margin: "0 0 4px",
                  }}
                >
                  {group.toUpperCase()}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {keys.map(cell)}
                </div>
              </div>
            ))}
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              {cell("")}
              <span className="sub2">No icon</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function move<T>(list: T[], i: number, by: number): T[] {
  const j = i + by;
  if (j < 0 || j >= list.length) return list;
  const out = [...list];
  [out[i], out[j]] = [out[j], out[i]];
  return out;
}

export default function MenuView() {
  const { clinic, me, toast } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const [loaded, setLoaded] = useState<{
    clinic: string;
    s?: Settings;
    error?: string;
  }>({ clinic: "" });
  const [menu, setMenu] = useState<Menu | null>(null);
  const [tpl, setTpl] = useState<Template | null>(null);
  const [openBtn, setOpenBtn] = useState<number | null>(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Settings>(`/v1/crm/console/${clinicId}/settings`).then(
      (s) => {
        if (!live) return;
        setLoaded({ clinic: clinicId, s });
        setMenu(s.draft.menu);
        setTpl(s.draft.template);
      },
      (e) =>
        live &&
        setLoaded({
          clinic: clinicId,
          error: e instanceof ApiError ? e.message : "Could not load.",
        }),
    );
    return () => {
      live = false;
    };
  }, [clinicId]);

  const s = loaded.clinic === clinicId ? loaded.s : undefined;
  const dirty =
    !!s &&
    !!menu &&
    !!tpl &&
    (JSON.stringify(menu) !== JSON.stringify(s.draft.menu) ||
      JSON.stringify(tpl) !== JSON.stringify(s.draft.template));

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function save() {
    if (!clinicId || !menu || !tpl) return;
    setBusy(true);
    setError("");
    try {
      await api<Settings>(`/v1/crm/console/${clinicId}/settings/template`, {
        method: "PUT",
        body: JSON.stringify(tpl),
      });
      const next = await api<Settings>(
        `/v1/crm/console/${clinicId}/settings/menu`,
        { method: "PUT", body: JSON.stringify(menu) },
      );
      setLoaded({ clinic: clinicId, s: next });
      setMenu(next.draft.menu);
      setTpl(next.draft.template);
      toast("Draft saved");
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (!clinicId) return;
    setBusy(true);
    try {
      const next = await api<Settings>(`/v1/crm/console/${clinicId}/publish`, {
        method: "POST",
      });
      setLoaded({ clinic: clinicId, s: next });
      toast("Published");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not publish.");
    } finally {
      setBusy(false);
    }
  }

  if (loaded.clinic === clinicId && loaded.error)
    return <div className="warnbox">{loaded.error}</div>;
  if (!s || !menu || !tpl) return <p className="sub2">Loading…</p>;

  const setBtn = (i: number, patch: Partial<Main>) =>
    setMenu({
      ...menu,
      buttons: menu.buttons.map((b, k) => (k === i ? { ...b, ...patch } : b)),
    });
  const setSub = (i: number, j: number, patch: Partial<Sub>) =>
    setBtn(i, {
      sub: menu.buttons[i].sub.map((x, k) =>
        k === j ? { ...x, ...patch } : x,
      ),
    });

  return (
    <>
      <div className="ph">
        <div>
          <h1>Menu buttons</h1>
        </div>
        <div className="row">
          <button className="pill" disabled={busy || !dirty} onClick={save}>
            Save changes
          </button>
          <button
            className="btn"
            disabled={busy || dirty || !s.changed}
            onClick={publish}
          >
            Publish
          </button>
        </div>
      </div>
      {error && <div className="warnbox">{error}</div>}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) 360px",
          gap: 16,
          alignItems: "start",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card fg">
            <h3 className="full" style={{ margin: 0 }}>
              Welcome
            </h3>
            <label className="full">
              Welcome message
              <textarea
                className="f"
                rows={2}
                maxLength={500}
                value={menu.welcome}
                onChange={(e) => setMenu({ ...menu, welcome: e.target.value })}
              />
            </label>
            <div className="fld full">
              Trust figures under the greeting (up to 3)
              <label className="opt">
                <input
                  type="checkbox"
                  checked={menu.show_figures}
                  onChange={(e) =>
                    setMenu({ ...menu, show_figures: e.target.checked })
                  }
                />
                Show the figures
              </label>
              {menu.figures.map((f, i) => (
                <div key={i} className="row">
                  <input
                    className="f"
                    style={{ width: 110 }}
                    maxLength={12}
                    placeholder="4.8★"
                    value={f.value}
                    onChange={(e) =>
                      setMenu({
                        ...menu,
                        figures: menu.figures.map((x, k) =>
                          k === i ? { ...x, value: e.target.value } : x,
                        ),
                      })
                    }
                  />
                  <input
                    className="f"
                    style={{ flex: 1 }}
                    maxLength={24}
                    placeholder="Google rating"
                    value={f.label}
                    onChange={(e) =>
                      setMenu({
                        ...menu,
                        figures: menu.figures.map((x, k) =>
                          k === i ? { ...x, label: e.target.value } : x,
                        ),
                      })
                    }
                  />
                  <button
                    className="pill"
                    onClick={() =>
                      setMenu({
                        ...menu,
                        figures: menu.figures.filter((_, k) => k !== i),
                      })
                    }
                  >
                    Remove
                  </button>
                </div>
              ))}
              {menu.figures.length < 3 && (
                <button
                  className="pill"
                  style={{ alignSelf: "flex-start" }}
                  onClick={() =>
                    setMenu({
                      ...menu,
                      figures: [...menu.figures, { value: "", label: "" }],
                    })
                  }
                >
                  + Add a figure
                </button>
              )}
            </div>
            <label className="full">
              Fallback message
              <textarea
                className="f"
                rows={2}
                maxLength={300}
                value={menu.fallback}
                onChange={(e) => setMenu({ ...menu, fallback: e.target.value })}
              />
              <span className="sub2" style={{ fontWeight: 400 }}>
                Shown with a call-back button when no answer is found.
              </span>
            </label>
          </div>

          <div className="card fg">
            <h3 className="full" style={{ margin: 0 }}>
              Layout
            </h3>
            <label>
              Buttons per row (Tiles and Cards)
              <select
                className="f"
                value={tpl.columns}
                onChange={(e) =>
                  setTpl({ ...tpl, columns: Number(e.target.value) })
                }
              >
                <option value={3}>3 per row (Neo Follicle today)</option>
                <option value={2}>2 per row (Neo Fertility design)</option>
              </select>
            </label>
            <label>
              Filled button (stands out, the designs: Book)
              <select
                className="f"
                value={tpl.filled_button}
                onChange={(e) =>
                  setTpl({ ...tpl, filled_button: e.target.value })
                }
              >
                <option value="">None</option>
                {menu.buttons
                  .filter((b) => !b.variant)
                  .map((b) => (
                    <option key={b.label}>{b.label}</option>
                  ))}
              </select>
            </label>
          </div>

          <div className="card">
            <h3>
              Main buttons{" "}
              <small>
                {menu.buttons.filter((b) => b.visible).length} shown
              </small>
            </h3>
            <div className="list">
              {menu.buttons.map((b, i) => (
                <div
                  key={i}
                  className="li"
                  style={{
                    flexDirection: "column",
                    alignItems: "stretch",
                    gap: 8,
                  }}
                >
                  <div className="row">
                    <Arrows
                      onUp={() =>
                        setMenu({ ...menu, buttons: move(menu.buttons, i, -1) })
                      }
                      onDown={() =>
                        setMenu({ ...menu, buttons: move(menu.buttons, i, 1) })
                      }
                    />
                    <span
                      style={{
                        width: 20,
                        height: 20,
                        display: "inline-flex",
                        color: "var(--brand)",
                      }}
                    >
                      <ChatIcon name={b.icon} />
                    </span>
                    <b style={{ flex: 1, opacity: b.visible ? 1 : 0.5 }}>
                      {b.label}
                      {b.sub.length > 0 && (
                        <span className="sub2">
                          {" "}
                          · {b.sub.length} sub-buttons
                        </span>
                      )}
                    </b>
                    <Toggle
                      on={b.visible}
                      onChange={(v) => setBtn(i, { visible: v })}
                    />
                    <button
                      className="pill"
                      onClick={() => setOpenBtn(openBtn === i ? null : i)}
                    >
                      {openBtn === i ? "Close" : "Configure"}
                    </button>
                  </div>
                  {openBtn === i && (
                    <div
                      className="fg"
                      style={{
                        background: "var(--panel)",
                        borderRadius: 10,
                        padding: 12,
                      }}
                    >
                      <label>
                        Label
                        <input
                          className="f"
                          maxLength={40}
                          value={b.label}
                          onChange={(e) => setBtn(i, { label: e.target.value })}
                        />
                      </label>
                      <IconPicker
                        value={b.icon}
                        onChange={(v) => setBtn(i, { icon: v })}
                      />
                      <ActionFields
                        action={b.action}
                        value={b.value}
                        onChange={(patch) => setBtn(i, patch)}
                      />
                      <label>
                        Style
                        <select
                          className="f"
                          value={b.variant}
                          onChange={(e) =>
                            setBtn(i, { variant: e.target.value })
                          }
                        >
                          <option value="">Normal</option>
                          <option value="wa">WhatsApp (green)</option>
                          <option value="sos">
                            Emergency (red, full width)
                          </option>
                        </select>
                      </label>
                      {b.action === "submenu" && (
                        <>
                          <label className="full">
                            Message above the sub-buttons
                            <input
                              className="f"
                              maxLength={500}
                              value={b.message}
                              onChange={(e) =>
                                setBtn(i, { message: e.target.value })
                              }
                            />
                          </label>
                          <div className="fld full">
                            Sub-buttons
                            {b.sub.map((x, j) => (
                              <div
                                key={j}
                                className="row"
                                style={{
                                  background: "#fff",
                                  borderRadius: 8,
                                  padding: 6,
                                }}
                              >
                                <Arrows
                                  onUp={() =>
                                    setBtn(i, { sub: move(b.sub, j, -1) })
                                  }
                                  onDown={() =>
                                    setBtn(i, { sub: move(b.sub, j, 1) })
                                  }
                                />
                                <input
                                  className="f"
                                  style={{ flex: "1 1 160px" }}
                                  maxLength={40}
                                  value={x.label}
                                  onChange={(e) =>
                                    setSub(i, j, { label: e.target.value })
                                  }
                                />
                                <select
                                  className="f"
                                  style={{ flex: "1 1 150px" }}
                                  value={x.action}
                                  onChange={(e) =>
                                    setSub(i, j, {
                                      action: e.target.value,
                                      value: "",
                                    })
                                  }
                                >
                                  {ACTIONS.filter(([k]) => k !== "submenu").map(
                                    ([k, label]) => (
                                      <option key={k} value={k}>
                                        {label}
                                      </option>
                                    ),
                                  )}
                                </select>
                                {ACTION_HINT[x.action] && (
                                  <input
                                    className="f"
                                    style={{ flex: "2 1 200px" }}
                                    maxLength={500}
                                    placeholder={ACTION_HINT[x.action]}
                                    value={x.value}
                                    onChange={(e) =>
                                      setSub(i, j, { value: e.target.value })
                                    }
                                  />
                                )}
                                <Toggle
                                  on={x.visible}
                                  onChange={(v) => setSub(i, j, { visible: v })}
                                />
                                <button
                                  className="pill"
                                  onClick={() =>
                                    setBtn(i, {
                                      sub: b.sub.filter((_, k) => k !== j),
                                    })
                                  }
                                >
                                  ✕
                                </button>
                              </div>
                            ))}
                            {b.sub.length < 12 && (
                              <button
                                className="pill"
                                style={{ alignSelf: "flex-start" }}
                                onClick={() =>
                                  setBtn(i, {
                                    sub: [
                                      ...b.sub,
                                      {
                                        label: "New button",
                                        action: "answer",
                                        value: "",
                                        visible: true,
                                      },
                                    ],
                                  })
                                }
                              >
                                + Add sub-button
                              </button>
                            )}
                          </div>
                        </>
                      )}
                      <div
                        className="full row"
                        style={{ justifyContent: "flex-end" }}
                      >
                        <button
                          className="pill"
                          style={{ color: "var(--err)" }}
                          onClick={() => {
                            setMenu({
                              ...menu,
                              buttons: menu.buttons.filter((_, k) => k !== i),
                            });
                            setOpenBtn(null);
                          }}
                        >
                          Delete this button
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
            {menu.buttons.length < 12 && (
              <button
                className="btn"
                style={{ marginTop: 10 }}
                onClick={() => {
                  setMenu({
                    ...menu,
                    buttons: [
                      ...menu.buttons,
                      {
                        label: "New button",
                        icon: "",
                        action: "submenu",
                        value: "",
                        message: "",
                        variant: "",
                        visible: true,
                        sub: [],
                      },
                    ],
                  });
                  setOpenBtn(menu.buttons.length);
                }}
              >
                + Create button
              </button>
            )}
          </div>
        </div>
        <Preview
          menu={menu}
          tpl={tpl}
          name={s.draft.appearance.look.name}
          colours={s.draft.appearance.colours}
        />
      </div>
    </>
  );
}

function ActionFields({
  action,
  value,
  onChange,
}: {
  action: string;
  value: string;
  onChange: (p: { action?: string; value?: string }) => void;
}) {
  return (
    <>
      <label>
        When a patient taps it
        <select
          className="f"
          value={action}
          onChange={(e) => onChange({ action: e.target.value, value: "" })}
        >
          {ACTIONS.map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {ACTION_HINT[action] && (
        <label>
          Connect to
          <input
            className="f"
            maxLength={500}
            placeholder={ACTION_HINT[action]}
            value={value}
            onChange={(e) => onChange({ value: e.target.value })}
          />
        </label>
      )}
    </>
  );
}

function Toggle({
  on,
  onChange,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      style={{
        border: 0,
        cursor: "pointer",
        width: 40,
        height: 22,
        borderRadius: 999,
        background: on ? "var(--brand)" : "#C9D0DA",
        position: "relative",
      }}
      title={on ? "ON" : "OFF"}
    >
      <i
        style={{
          position: "absolute",
          top: 3,
          left: on ? 21 : 3,
          width: 16,
          height: 16,
          borderRadius: "50%",
          background: "#fff",
          transition: "left .15s",
        }}
      />
    </button>
  );
}

function Arrows({ onUp, onDown }: { onUp: () => void; onDown: () => void }) {
  return (
    <span style={{ display: "inline-flex", flexDirection: "column" }}>
      <button
        aria-label="Move up"
        onClick={onUp}
        style={{
          border: 0,
          background: "none",
          cursor: "pointer",
          lineHeight: 1,
          fontSize: 11,
        }}
      >
        ▲
      </button>
      <button
        aria-label="Move down"
        onClick={onDown}
        style={{
          border: 0,
          background: "none",
          cursor: "pointer",
          lineHeight: 1,
          fontSize: 11,
        }}
      >
        ▼
      </button>
    </span>
  );
}

/** What patients see: the welcome, the figures and the buttons; tapping a button with sub-buttons opens them. */
function Preview({
  menu,
  tpl,
  name,
  colours,
}: {
  menu: Menu;
  tpl: Template;
  name: string;
  colours: { main: string; highlight: string };
}) {
  const [at, setAt] = useState<number | null>(null);
  const shown = menu.buttons.filter((b) => b.visible);
  const opened = at !== null ? shown[at] : null;
  const bubble = (children: ReactNode) => (
    <span
      style={{
        alignSelf: "flex-start",
        background: "#F1F3F7",
        borderRadius: 12,
        padding: "7px 9px",
        fontSize: 12,
        maxWidth: "88%",
      }}
    >
      {children}
    </span>
  );
  const tile = (b: Main, i: number) => {
    const filled = b.label === tpl.filled_button;
    const wide = b.variant === "sos";
    return (
      <button
        key={i}
        onClick={() => b.action === "submenu" && setAt(i)}
        style={{
          gridColumn: wide ? "1 / -1" : undefined,
          display: "flex",
          flexDirection: tpl.id === "tiles" && !wide ? "column" : "row",
          alignItems: "center",
          justifyContent: wide ? "center" : undefined,
          gap: 5,
          padding: "8px 6px",
          borderRadius: tpl.id === "pills" ? 999 : 10,
          border:
            tpl.id === "tiles"
              ? 0
              : `1px solid ${b.variant === "sos" ? "#E5484D" : b.variant === "wa" ? "#1F9D55" : "#E3E8EF"}`,
          background: filled
            ? colours.main
            : b.variant === "sos"
              ? "#FDECEC"
              : b.variant === "wa"
                ? "#E8F7EE"
                : tpl.id === "tiles"
                  ? "#F1F5FD"
                  : "#fff",
          color: filled
            ? "#fff"
            : b.variant === "sos"
              ? "#B42318"
              : b.variant === "wa"
                ? "#1F7A45"
                : "#1F2937",
          fontSize: 11,
          fontWeight: 600,
          cursor: b.action === "submenu" ? "pointer" : "default",
          textAlign: "center",
          minWidth: 0,
        }}
      >
        {b.icon && (
          <span
            style={{
              width: 16,
              height: 16,
              display: "inline-flex",
              color: filled ? "#fff" : b.variant ? undefined : colours.main,
            }}
          >
            <ChatIcon name={b.icon} />
          </span>
        )}
        {b.label}
      </button>
    );
  };
  return (
    <div className="card" style={{ position: "sticky", top: 70 }}>
      <h3>
        Live preview <small>tap a button to see its sub-buttons</small>
      </h3>
      <div style={{ background: "#F3F5F9", borderRadius: 12, padding: 10 }}>
        <div
          style={{
            background: "#fff",
            borderRadius: 14,
            overflow: "hidden",
            boxShadow: "0 8px 22px -12px rgba(22,32,46,.4)",
          }}
        >
          <div
            style={{
              background: colours.main,
              color: "#fff",
              padding: "9px 12px",
              fontWeight: 700,
              fontSize: 13,
            }}
          >
            {name}
          </div>
          <div
            style={{
              padding: 10,
              display: "flex",
              flexDirection: "column",
              gap: 8,
              minHeight: 380,
            }}
          >
            {opened ? (
              <>
                {bubble(opened.message || opened.label)}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {opened.sub
                    .filter((x) => x.visible)
                    .map((x, j) => (
                      <span
                        key={j}
                        style={{
                          border: `1.5px solid ${colours.main}`,
                          color: colours.main,
                          borderRadius: 999,
                          padding: "5px 10px",
                          fontSize: 11.5,
                          fontWeight: 600,
                        }}
                      >
                        {x.label}
                      </span>
                    ))}
                </div>
                <button
                  onClick={() => setAt(null)}
                  style={{
                    alignSelf: "flex-start",
                    border: 0,
                    background: "none",
                    color: "#6B5F63",
                    fontWeight: 600,
                    cursor: "pointer",
                    fontSize: 11.5,
                  }}
                >
                  ‹ Back · Main menu
                </button>
              </>
            ) : (
              <>
                {bubble(menu.welcome || "…")}
                {menu.show_figures && menu.figures.length > 0 && (
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: `repeat(${menu.figures.length}, 1fr)`,
                      gap: 6,
                    }}
                  >
                    {menu.figures.map((f, i) => (
                      <span
                        key={i}
                        style={{
                          textAlign: "center",
                          background: "#FAF6F7",
                          borderRadius: 10,
                          padding: "6px 4px",
                        }}
                      >
                        <b style={{ display: "block", fontSize: 13 }}>
                          {f.value}
                        </b>
                        <span style={{ fontSize: 10.5, color: "#6B5F63" }}>
                          {f.label}
                        </span>
                      </span>
                    ))}
                  </div>
                )}
                {tpl.id === "pills" ? (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {shown.map(tile)}
                  </div>
                ) : (
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: `repeat(${tpl.columns}, minmax(0, 1fr))`,
                      gap: 6,
                    }}
                  >
                    {shown
                      .filter((b) => b.variant !== "sos")
                      .map((b) => tile(b, shown.indexOf(b)))}
                    {shown
                      .filter((b) => b.variant === "sos")
                      .map((b) => tile(b, shown.indexOf(b)))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
