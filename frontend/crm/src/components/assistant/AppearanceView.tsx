"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError } from "@/lib/api";

// Dashboard → Appearance: Look, Colours, Widget style and Launcher, one draft with a live preview.
// Saving keeps a draft; patients see it only after Publish (backend: /v1/crm/console/{clinic}/...).

type Look = {
  name: string;
  status_line: string;
  enabled: boolean;
  logo: string;
  avatar_letter: string;
};
type Colours = { main: string; highlight: string };
type Widget = {
  size: string;
  radius: string;
  border: string;
  shadow: string;
  header_text: string;
  footer_on: boolean;
  footer_text: string;
  footer_link: string;
};
type Launcher = {
  position: string;
  offset_x: number;
  offset_y: number;
  shape: string;
  size: string;
  background: string;
  icon: string;
  icon_color: string;
  border: string;
  label_on: boolean;
  label_text: string;
  label_after_s: number;
  notification_dot: boolean;
  opens_as: string;
  open_on_first_visit: boolean;
};
export type Appearance = {
  look: Look;
  colours: Colours;
  widget: Widget;
  launcher: Launcher;
};
type Settings = {
  draft: { appearance: Appearance };
  published: { appearance?: Appearance };
  version: number;
  changed: boolean;
  published_at: string | null;
};

const TABS = [
  ["look", "Look"],
  ["colours", "Colours"],
  ["widget", "Widget style"],
  ["launcher", "Launcher"],
] as const;
type Tab = (typeof TABS)[number][0];

export default function AppearanceView() {
  const { clinic, me, toast } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const [loaded, setLoaded] = useState<{
    clinic: string;
    s?: Settings;
    error?: string;
  }>({ clinic: "" });
  const [form, setForm] = useState<Appearance | null>(null);
  const [tab, setTab] = useState<Tab>("look");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Settings>(`/v1/crm/console/${clinicId}/settings`).then(
      (s) => {
        if (!live) return;
        setLoaded({ clinic: clinicId, s });
        setForm(s.draft.appearance);
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
    !!form &&
    JSON.stringify(form) !== JSON.stringify(s.draft.appearance);

  // Warn before leaving the page with unsaved changes.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function call(
    path: string,
    method: string,
    body?: object,
    done?: string,
  ) {
    if (!clinicId) return;
    setBusy(true);
    setError("");
    try {
      const next = await api<Settings>(`/v1/crm/console/${clinicId}/${path}`, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      });
      setLoaded({ clinic: clinicId, s: next });
      setForm(next.draft.appearance);
      if (done) toast(done);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (loaded.clinic === clinicId && loaded.error)
    return <div className="warnbox">{loaded.error}</div>;
  if (!s || !form) return <p className="sub2">Loading…</p>;

  const set = <K extends keyof Appearance>(
    k: K,
    patch: Partial<Appearance[K]>,
  ) => setForm({ ...form, [k]: { ...form[k], ...patch } });
  return (
    <>
      <div className="ph">
        <div>
          <h1>Appearance</h1>
        </div>
        <div className="row">
          <button
            className="pill"
            disabled={busy || !dirty}
            onClick={() =>
              call("settings/appearance", "PUT", form, "Draft saved")
            }
          >
            Save changes
          </button>
          <button
            className="btn"
            disabled={busy || dirty || !s.changed}
            onClick={() => call("publish", "POST", undefined, "Published")}
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
        <div className="card">
          <div className="tabs">
            {TABS.map(([k, label]) => (
              <button
                key={k}
                className={tab === k ? "on" : ""}
                onClick={() => setTab(k)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="fg">
            {tab === "look" && (
              <>
                <Field
                  label="Assistant name"
                  hint='For example "Arya" or "Neo Follicle Assistant".'
                >
                  <input
                    className="f"
                    maxLength={40}
                    value={form.look.name}
                    onChange={(e) => set("look", { name: e.target.value })}
                  />
                </Field>
                <Field label="Chatbot status" group>
                  <div className="row">
                    {[true, false].map((on) => (
                      <label key={String(on)} className="opt">
                        <input
                          type="radio"
                          checked={form.look.enabled === on}
                          onChange={() => set("look", { enabled: on })}
                        />
                        {on ? "Enabled" : "Disabled"}
                      </label>
                    ))}
                  </div>
                </Field>
                <Field
                  label="Status line"
                  hint='Under the name, up to 13 characters, for example "Instant Reply".'
                >
                  <input
                    className="f"
                    maxLength={13}
                    value={form.look.status_line}
                    onChange={(e) =>
                      set("look", { status_line: e.target.value })
                    }
                  />
                </Field>
                <Field
                  label="Avatar letter"
                  hint="Used when no logo is uploaded."
                >
                  <input
                    className="f"
                    maxLength={2}
                    value={form.look.avatar_letter}
                    onChange={(e) =>
                      set("look", { avatar_letter: e.target.value })
                    }
                  />
                </Field>
                <Field
                  label="Logo"
                  hint="Square, at least 128×128 px, under 200 KB. Upload a file or paste an https:// address."
                  full
                >
                  <div className="row">
                    <input
                      className="f"
                      style={{ flex: 1 }}
                      placeholder="https://…"
                      value={
                        form.look.logo.startsWith("data:")
                          ? "(uploaded image)"
                          : form.look.logo
                      }
                      onChange={(e) => set("look", { logo: e.target.value })}
                    />
                    <label className="pill" style={{ cursor: "pointer" }}>
                      Choose file
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp,image/svg+xml"
                        hidden
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (!f) return;
                          if (f.size > 200_000)
                            return setError("The logo must be under 200 KB.");
                          const r = new FileReader();
                          r.onload = () =>
                            set("look", { logo: String(r.result) });
                          r.readAsDataURL(f);
                        }}
                      />
                    </label>
                    {form.look.logo && (
                      <button
                        className="pill"
                        onClick={() => set("look", { logo: "" })}
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </Field>
              </>
            )}
            {tab === "colours" && (
              <>
                <Colour
                  label="Main colour"
                  hint="Patient bubbles, the send button and links."
                  value={form.colours.main}
                  onChange={(v) => set("colours", { main: v })}
                />
                <Colour
                  label="Highlight colour"
                  hint="Small accents and badges."
                  value={form.colours.highlight}
                  onChange={(v) => set("colours", { highlight: v })}
                />
              </>
            )}
            {tab === "widget" && (
              <>
                <Choice
                  label="Size"
                  value={form.widget.size}
                  options={["small", "medium", "large"]}
                  onChange={(v) => set("widget", { size: v })}
                />
                <Choice
                  label="Corner radius"
                  value={form.widget.radius}
                  options={["square", "rounded", "round"]}
                  onChange={(v) => set("widget", { radius: v })}
                />
                <Choice
                  label="Border"
                  value={form.widget.border}
                  options={["none", "subtle", "strong"]}
                  onChange={(v) => set("widget", { border: v })}
                />
                <Choice
                  label="Shadow"
                  value={form.widget.shadow}
                  options={["none", "soft", "strong"]}
                  onChange={(v) => set("widget", { shadow: v })}
                />
                <Field label="Header text" full>
                  <input
                    className="f"
                    maxLength={80}
                    value={form.widget.header_text}
                    onChange={(e) =>
                      set("widget", { header_text: e.target.value })
                    }
                  />
                </Field>
                <Field label="Footer" full group>
                  <label className="opt">
                    <input
                      type="checkbox"
                      checked={form.widget.footer_on}
                      onChange={(e) =>
                        set("widget", { footer_on: e.target.checked })
                      }
                    />
                    Show the &quot;Powered by&quot; footer
                  </label>
                </Field>
                {form.widget.footer_on && (
                  <>
                    <Field label="Footer text">
                      <input
                        className="f"
                        maxLength={80}
                        value={form.widget.footer_text}
                        onChange={(e) =>
                          set("widget", { footer_text: e.target.value })
                        }
                      />
                    </Field>
                    <Field label="Footer link">
                      <input
                        className="f"
                        placeholder="https://…"
                        value={form.widget.footer_link}
                        onChange={(e) =>
                          set("widget", { footer_link: e.target.value })
                        }
                      />
                    </Field>
                  </>
                )}
              </>
            )}
            {tab === "launcher" && (
              <>
                <Choice
                  label="Position"
                  value={form.launcher.position}
                  options={["bottom_right", "bottom_left"]}
                  onChange={(v) => set("launcher", { position: v })}
                />
                <Choice
                  label="Shape"
                  value={form.launcher.shape}
                  options={["pill", "rounded", "circle"]}
                  onChange={(v) => set("launcher", { shape: v })}
                />
                <Field label="Horizontal offset (px)">
                  <input
                    className="f"
                    type="number"
                    min={0}
                    max={200}
                    value={form.launcher.offset_x}
                    onChange={(e) =>
                      set("launcher", { offset_x: Number(e.target.value) })
                    }
                  />
                </Field>
                <Field label="Vertical offset (px)">
                  <input
                    className="f"
                    type="number"
                    min={0}
                    max={200}
                    value={form.launcher.offset_y}
                    onChange={(e) =>
                      set("launcher", { offset_y: Number(e.target.value) })
                    }
                  />
                </Field>
                <Choice
                  label="Size"
                  value={form.launcher.size}
                  options={["small", "medium", "large"]}
                  onChange={(v) => set("launcher", { size: v })}
                />
                <Choice
                  label="Icon"
                  value={form.launcher.icon}
                  options={["chat", "logo"]}
                  onChange={(v) => set("launcher", { icon: v })}
                />
                <Colour
                  label="Background colour"
                  value={form.launcher.background}
                  onChange={(v) => set("launcher", { background: v })}
                />
                <Colour
                  label="Icon colour"
                  value={form.launcher.icon_color}
                  onChange={(v) => set("launcher", { icon_color: v })}
                />
                <Choice
                  label="Border"
                  value={form.launcher.border}
                  options={["none", "subtle", "strong"]}
                  onChange={(v) => set("launcher", { border: v })}
                />
                <Choice
                  label="Chat opens as"
                  value={form.launcher.opens_as}
                  options={["panel", "full"]}
                  onChange={(v) => set("launcher", { opens_as: v })}
                />
                <Field
                  label="Label text"
                  hint="Keep it under 32 characters so it fits on one line."
                >
                  <input
                    className="f"
                    maxLength={32}
                    value={form.launcher.label_text}
                    onChange={(e) =>
                      set("launcher", { label_text: e.target.value })
                    }
                  />
                </Field>
                <Field
                  label="Show label after (seconds)"
                  hint="0 shows it as soon as the page loads."
                >
                  <input
                    className="f"
                    type="number"
                    min={0}
                    max={120}
                    value={form.launcher.label_after_s}
                    onChange={(e) =>
                      set("launcher", { label_after_s: Number(e.target.value) })
                    }
                  />
                </Field>
                <Field label="Options" full group>
                  {(
                    [
                      ["label_on", "Show the label (pill shape)"],
                      [
                        "notification_dot",
                        "Notification dot until the chat is opened",
                      ],
                      [
                        "open_on_first_visit",
                        "Open automatically on first visit",
                      ],
                    ] as const
                  ).map(([k, label]) => (
                    <label key={k} className="opt">
                      <input
                        type="checkbox"
                        checked={form.launcher[k]}
                        onChange={(e) =>
                          set("launcher", { [k]: e.target.checked })
                        }
                      />
                      {label}
                    </label>
                  ))}
                </Field>
              </>
            )}
          </div>
        </div>
        <Preview a={form} />
      </div>
    </>
  );
}

function Field({
  label,
  hint,
  full,
  group,
  children,
}: {
  label: string;
  hint?: string;
  full?: boolean;
  group?: boolean; // holds its own checkboxes or radio buttons
  children: ReactNode;
}) {
  const Tag = group ? "div" : "label";
  return (
    <Tag
      className={
        [group ? "fld" : "", full ? "full" : ""].join(" ").trim() || undefined
      }
    >
      {label}
      {children}
      {hint && (
        <span className="sub2" style={{ fontWeight: 400 }}>
          {hint}
        </span>
      )}
    </Tag>
  );
}

const words = (v: string) =>
  (v.charAt(0).toUpperCase() + v.slice(1)).replace("_", " ");
function Choice({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <Field label={label}>
      <select
        className="f"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {words(o)}
          </option>
        ))}
      </select>
    </Field>
  );
}

function Colour({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Field label={label} hint={hint}>
      <div className="row">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          style={{ width: 48, height: 36, border: 0, background: "none" }}
        />
        <input
          className="f"
          style={{ width: 110 }}
          maxLength={7}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    </Field>
  );
}

const RADIUS: Record<string, number> = { square: 4, rounded: 14, round: 24 };
const BORDER: Record<string, string> = {
  none: "0",
  subtle: "1px solid #E3E8EF",
  strong: "2px solid #9AA3AF",
};
const SHADOW: Record<string, string> = {
  none: "none",
  soft: "0 10px 30px -12px rgba(22,32,46,.35)",
  strong: "0 18px 50px -14px rgba(22,32,46,.55)",
};
const WIDTH: Record<string, number> = { small: 260, medium: 300, large: 330 };
const BUTTON: Record<string, number> = { small: 44, medium: 52, large: 60 };

/** A live preview of the chat and its launcher from the unsaved form: chat open or closed, desktop or mobile. */
function Preview({ a }: { a: Appearance }) {
  const [open, setOpen] = useState(true);
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const mobile = device === "mobile";
  const l = a.launcher;
  const left = l.position === "bottom_left";
  const pill = l.shape === "pill" && l.label_on && l.icon !== "logo";
  // On a phone the chat covers the screen (as it does when it opens as full screen); the launcher is hidden then.
  const sheet = mobile || l.opens_as === "full";
  // As in the real widget: a white round avatar (logo or letter) with a dot in the highlight colour.
  const avatar = (
    <span style={{ position: "relative", flex: "0 0 auto" }}>
      {a.look.logo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={a.look.logo}
          alt=""
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            objectFit: "cover",
            background: "#fff",
            display: "block",
          }}
        />
      ) : (
        <span
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            background: "#fff",
            color: a.colours.main,
            display: "grid",
            placeItems: "center",
            fontWeight: 800,
            fontSize: 16,
          }}
        >
          {a.look.avatar_letter}
        </span>
      )}
      <i
        style={{
          position: "absolute",
          right: -1,
          bottom: -1,
          width: 11,
          height: 11,
          borderRadius: "50%",
          background: a.colours.highlight,
          border: "2px solid " + a.colours.main,
        }}
      />
    </span>
  );
  const seg = (on: boolean, label: string, click: () => void) => (
    <button className={on ? "on" : ""} onClick={click}>
      {label}
    </button>
  );
  return (
    <div className="card" style={{ position: "sticky", top: 70 }}>
      <h3>
        Live preview{" "}
        <small>
          {a.look.enabled ? "Enabled" : "Disabled: hidden on the website"}
        </small>
      </h3>
      <div className="row" style={{ marginBottom: 10 }}>
        <div className="seg" style={{ marginLeft: 0 }}>
          {seg(!mobile, "Desktop", () => setDevice("desktop"))}
          {seg(mobile, "Mobile", () => setDevice("mobile"))}
        </div>
        <div className="seg">
          {seg(open, "Chat open", () => setOpen(true))}
          {seg(!open, "Chat closed", () => setOpen(false))}
        </div>
      </div>
      <div
        style={{
          background: "#F3F5F9",
          borderRadius: mobile ? 28 : 12,
          border: mobile ? "8px solid #1F2937" : "1px solid #E3E8EF",
          width: mobile ? 250 : "100%",
          height: mobile ? 500 : 470,
          margin: "0 auto",
          position: "relative",
          overflow: "hidden",
          opacity: a.look.enabled ? 1 : 0.5,
        }}
      >
        {/* A sketch of the clinic's web page behind the chat. */}
        <div
          style={{
            padding: 14,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <i
            style={{
              height: 14,
              width: "55%",
              background: "#DDE3EC",
              borderRadius: 4,
            }}
          />
          <i style={{ height: 70, background: "#E6EBF2", borderRadius: 8 }} />
          <i
            style={{
              height: 10,
              width: "80%",
              background: "#E6EBF2",
              borderRadius: 4,
            }}
          />
          <i
            style={{
              height: 10,
              width: "65%",
              background: "#E6EBF2",
              borderRadius: 4,
            }}
          />
        </div>
        {open && (
          <div
            style={{
              position: "absolute",
              ...(sheet
                ? { inset: mobile ? "40px 0 0 0" : 8 }
                : {
                    bottom: BUTTON[l.size] + 24,
                    [left ? "left" : "right"]: 12,
                    width: Math.min(WIDTH[a.widget.size], 300),
                  }),
              background: "#fff",
              borderRadius: mobile ? "16px 16px 0 0" : RADIUS[a.widget.radius],
              border: BORDER[a.widget.border],
              boxShadow: SHADOW[a.widget.shadow],
              overflow: "hidden",
              fontSize: 12.5,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div
              style={{
                display: "flex",
                gap: 10,
                alignItems: "center",
                padding: "10px 12px",
                background: a.colours.main,
                color: "#fff",
              }}
            >
              {avatar}
              <div style={{ flex: 1, minWidth: 0 }}>
                <b style={{ display: "block" }}>{a.look.name || "Assistant"}</b>
                <span style={{ fontSize: 11, opacity: 0.9 }}>
                  {a.widget.header_text || a.look.status_line}
                </span>
              </div>
              <button
                aria-label="Close the preview chat"
                onClick={() => setOpen(false)}
                style={{
                  color: "#fff",
                  border: 0,
                  background: "none",
                  cursor: "pointer",
                  fontSize: 16,
                }}
              >
                ✕
              </button>
            </div>
            <div
              style={{
                padding: 12,
                display: "flex",
                flexDirection: "column",
                gap: 8,
                flex: 1,
              }}
            >
              <span
                style={{
                  alignSelf: "flex-start",
                  background: "#F1F3F7",
                  borderRadius: 12,
                  padding: "8px 10px",
                  maxWidth: "85%",
                }}
              >
                Hi, I&apos;m {a.look.name || "your assistant"}. How can I help
                you today?
              </span>
              <span
                style={{
                  alignSelf: "flex-start",
                  border: `1px solid ${a.colours.main}`,
                  color: a.colours.main,
                  borderRadius: 999,
                  padding: "5px 10px",
                  fontWeight: 600,
                }}
              >
                Book Consultation
              </span>
              <span
                style={{
                  alignSelf: "flex-end",
                  background: a.colours.main,
                  color: "#fff",
                  borderRadius: 12,
                  padding: "8px 10px",
                }}
              >
                I want to book
              </span>
              <span
                style={{
                  alignSelf: "flex-start",
                  background: a.colours.highlight,
                  borderRadius: 999,
                  padding: "2px 8px",
                  fontSize: 11,
                  fontWeight: 700,
                }}
              >
                4.8★ Google
              </span>
            </div>
            {a.widget.footer_on && (
              <div
                style={{
                  textAlign: "center",
                  fontSize: 10,
                  color: "#7A8494",
                  padding: "6px 8px",
                  borderTop: "1px solid #EEF1F5",
                }}
              >
                {a.widget.footer_text}
              </div>
            )}
          </div>
        )}
        {!(open && sheet) && (
          <button
            aria-label={
              open ? "Close the preview chat" : "Open the preview chat"
            }
            onClick={() => setOpen(!open)}
            style={{
              position: "absolute",
              bottom: Math.min(l.offset_y, 40) / 2 + 8,
              [left ? "left" : "right"]: Math.min(l.offset_x, 40) / 2 + 8,
              height: BUTTON[l.size],
              minWidth: BUTTON[l.size],
              padding: pill && !open ? "0 16px" : 0,
              borderRadius: l.shape === "rounded" ? 14 : 999,
              background: l.background,
              color: l.icon_color,
              border: BORDER[l.border],
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              fontWeight: 700,
              cursor: "pointer",
              boxShadow: "0 8px 20px -8px rgba(0,0,0,.4)",
            }}
          >
            {open ? (
              <span style={{ fontSize: 18 }}>✕</span>
            ) : l.icon === "logo" && a.look.logo ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={a.look.logo}
                alt=""
                style={{
                  width: BUTTON[l.size] - 14,
                  height: BUTTON[l.size] - 14,
                  borderRadius: "50%",
                }}
              />
            ) : (
              <svg
                viewBox="0 0 24 24"
                width="22"
                height="22"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M4 5h16v11H9l-5 4z" />
              </svg>
            )}
            {pill && !open && <span>{l.label_text}</span>}
            {l.notification_dot && !open && (
              <i
                style={{
                  position: "absolute",
                  top: 2,
                  right: 2,
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  background: "#E5484D",
                  border: "2px solid #fff",
                }}
              />
            )}
          </button>
        )}
      </div>
    </div>
  );
}
