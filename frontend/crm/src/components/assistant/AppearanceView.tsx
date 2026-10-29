"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError } from "@/lib/api";

// Dashboard → Appearance: Look (and header), Colours, Widget style (chat panel) and Launcher, one draft with a
// live preview. Saving keeps a draft; patients see it only after Publish (backend: /v1/crm/console/{clinic}).

type Look = {
  name: string;
  status_line: string;
  enabled: boolean;
  logo: string;
  avatar_letter: string;
  location: string;
  tagline: string;
  header_arc: boolean;
};
type Colours = {
  main: string;
  highlight: string;
  main_dark: string;
  accent: string;
  tint: string;
  surface: string;
  line: string;
  text: string;
  muted: string;
  whatsapp: string;
  dark_mode: boolean;
  dark_page: string;
  dark_card: string;
  dark_text: string;
  dark_line: string;
};
type Widget = {
  size: string;
  radius: string;
  border: string;
  shadow: string;
  font: string;
  header_text: string;
  footer_on: boolean;
  footer_text: string;
  footer_link: string;
  mobile_contact_row: boolean;
  contact_buttons: string[];
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
  mobile_offset_x: number;
  mobile_offset_y: number;
  mobile_label: boolean;
};
export type Appearance = {
  look: Look;
  colours: Colours;
  widget: Widget;
  launcher: Launcher;
};
type Settings = {
  draft: { appearance: Appearance };
  changed: boolean;
  version: number;
};

const TABS = [
  ["look", "Look"],
  ["colours", "Colours"],
  ["widget", "Widget style"],
  ["launcher", "Launcher"],
] as const;
type Tab = (typeof TABS)[number][0];

// ---------- colour helpers ----------
const rgb = (h: string) =>
  [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const hex = (c: number[]) =>
  "#" +
  c
    .map((v) =>
      Math.round(Math.max(0, Math.min(255, v)))
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")
    .toUpperCase();
const mix = (a: string, b: string, t: number) =>
  hex(rgb(a).map((v, i) => v + (rgb(b)[i] - v) * t));
function luminance(h: string) {
  const [r, g, b] = rgb(h).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
/** Contrast ratio of two colours (WCAG): 4.5 or more is AA for normal text. */
function contrast(a: string, b: string) {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}
const valid = (h: string) => /^#[0-9A-Fa-f]{6}$/.test(h);
/** The shades the designs use, worked out from the main colour. */
const fromMain = (main: string) => ({
  main_dark: mix(main, "#000000", 0.3),
  accent: mix(main, "#FFFFFF", 0.45),
  tint: mix(main, "#FFFFFF", 0.92),
});

const COLOUR_FIELDS: [keyof Colours, string, string][] = [
  ["main", "Main colour", "Header, filled buttons, patient bubbles."],
  [
    "highlight",
    "Highlight colour",
    "Online dot, unread badge, keyboard focus.",
  ],
  ["main_dark", "Main dark", "Hover, sub-button text, bold text."],
  ["accent", "Light accent", "Header arc, typing dots, focus rings."],
  ["tint", "Tint", "Icon wells, hover fills, the selected slot."],
  ["surface", "Surface", "Bot bubbles, home button."],
  ["line", "Lines", "Borders and dividers."],
  ["text", "Text", "Body text and tile labels."],
  ["muted", "Muted text", "Back / Main menu and small text."],
  ["whatsapp", "WhatsApp green", "The WhatsApp button's border."],
];
const DARK_FIELDS: [keyof Colours, string][] = [
  ["dark_page", "Page"],
  ["dark_card", "Chat panel"],
  ["dark_text", "Text"],
  ["dark_line", "Lines"],
];

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
  const c = form.colours;
  const ratio = valid(c.main) ? contrast("#FFFFFF", c.main) : 0;
  const textRatio =
    valid(c.text) && valid(c.surface) ? contrast(c.text, c.surface) : 0;
  const readable = ratio >= 4.5 && textRatio >= 4.5;

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
          gridTemplateColumns: "minmax(0, 1fr) 380px",
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
                  label="Location line"
                  hint='Under the name in the header, e.g. "Marathahalli, Whitefield".'
                >
                  <input
                    className="f"
                    maxLength={60}
                    value={form.look.location}
                    onChange={(e) => set("look", { location: e.target.value })}
                  />
                </Field>
                <Field
                  label="Tagline"
                  hint='E.g. "Best Fertility and IVF Clinic". Empty: the header text shows instead.'
                >
                  <input
                    className="f"
                    maxLength={60}
                    value={form.look.tagline}
                    onChange={(e) => set("look", { tagline: e.target.value })}
                  />
                </Field>
                <Field label="Header" group full>
                  <label className="opt">
                    <input
                      type="checkbox"
                      checked={form.look.header_arc}
                      onChange={(e) =>
                        set("look", { header_arc: e.target.checked })
                      }
                    />
                    Soft arc behind the header, in the light accent colour
                  </label>
                </Field>
                <Field
                  label="Logo"
                  hint="Square, at least 128×128 px, under 200 KB. Upload a file or paste an https:// address."
                  full
                  group
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
                <div
                  className="full row"
                  style={{ justifyContent: "space-between" }}
                >
                  <span className="sub2">
                    The same colour roles as the clinic designs; only the values
                    change.
                  </span>
                  <button
                    className="pill"
                    disabled={!valid(c.main)}
                    onClick={() => set("colours", fromMain(c.main))}
                  >
                    Fill shades from the main colour
                  </button>
                </div>
                {COLOUR_FIELDS.map(([k, label, hint]) => (
                  <Colour
                    key={k}
                    label={label}
                    hint={hint}
                    value={String(c[k])}
                    onChange={(v) => set("colours", { [k]: v })}
                  />
                ))}
                <div className={`full ${readable ? "okbox" : "warnbox"}`}>
                  White text on the main colour: <b>{ratio.toFixed(1)} : 1</b>.
                  Text on the surface: <b>{textRatio.toFixed(1)} : 1</b>.{" "}
                  {readable
                    ? "Easy to read (WCAG AA)."
                    : "Too light to read easily: WCAG AA needs 4.5 : 1. Choose a darker colour."}
                </div>
                <Field label="Dark mode" group full>
                  <label className="opt">
                    <input
                      type="checkbox"
                      checked={c.dark_mode}
                      onChange={(e) =>
                        set("colours", { dark_mode: e.target.checked })
                      }
                    />
                    Follow the visitor&apos;s dark setting
                  </label>
                </Field>
                {c.dark_mode &&
                  DARK_FIELDS.map(([k, label]) => (
                    <Colour
                      key={k}
                      label={`Dark: ${label}`}
                      value={String(c[k])}
                      onChange={(v) => set("colours", { [k]: v })}
                    />
                  ))}
              </>
            )}

            {tab === "widget" && (
              <>
                <Choice
                  label="Panel size (desktop)"
                  value={form.widget.size}
                  options={[
                    ["small", "Small (340 × 540)"],
                    ["medium", "Medium (380 × 580)"],
                    ["large", "Large (420 × 640)"],
                  ]}
                  onChange={(v) => set("widget", { size: v })}
                />
                <Choice
                  label="Corner radius"
                  value={form.widget.radius}
                  options={[
                    ["square", "Square (8 px)"],
                    ["rounded", "Rounded (20 px)"],
                    ["round", "Round (28 px)"],
                  ]}
                  onChange={(v) => set("widget", { radius: v })}
                />
                <Choice
                  label="Border"
                  value={form.widget.border}
                  options={["none", "subtle", "strong"]}
                  onChange={(v) => set("widget", { border: v })}
                />
                <Choice
                  label="Shadow (tinted with the main colour)"
                  value={form.widget.shadow}
                  options={["none", "soft", "strong"]}
                  onChange={(v) => set("widget", { shadow: v })}
                />
                <Choice
                  label="Font"
                  value={form.widget.font}
                  options={["Figtree", "Inter", "System"]}
                  onChange={(v) => set("widget", { font: v })}
                />
                <Field label="Header text" hint="Shown when no tagline is set.">
                  <input
                    className="f"
                    maxLength={80}
                    value={form.widget.header_text}
                    onChange={(e) =>
                      set("widget", { header_text: e.target.value })
                    }
                  />
                </Field>
                <Field label="On mobile" group full>
                  <span className="sub2" style={{ fontWeight: 400 }}>
                    The chat covers the whole screen (no corners), so nothing
                    behind it can be tapped.
                  </span>
                  <label className="opt">
                    <input
                      type="checkbox"
                      checked={form.widget.mobile_contact_row}
                      onChange={(e) =>
                        set("widget", { mobile_contact_row: e.target.checked })
                      }
                    />
                    Contact row at the bottom of the chat
                  </label>
                  {form.widget.mobile_contact_row && (
                    <div className="row">
                      {(
                        [
                          ["call", "Call"],
                          ["book", "Book"],
                          ["whatsapp", "WhatsApp"],
                        ] as const
                      ).map(([k, label]) => (
                        <label key={k} className="opt">
                          <input
                            type="checkbox"
                            checked={form.widget.contact_buttons.includes(k)}
                            onChange={(e) =>
                              set("widget", {
                                contact_buttons: e.target.checked
                                  ? ["call", "book", "whatsapp"].filter(
                                      (x) =>
                                        x === k ||
                                        form.widget.contact_buttons.includes(x),
                                    )
                                  : form.widget.contact_buttons.filter(
                                      (x) => x !== k,
                                    ),
                              })
                            }
                          />
                          {label}
                        </label>
                      ))}
                    </div>
                  )}
                </Field>
                <Field label="Footer" group full>
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
                  options={[
                    ["bottom_right", "Bottom right"],
                    ["bottom_left", "Bottom left"],
                  ]}
                  onChange={(v) => set("launcher", { position: v })}
                />
                <Choice
                  label="Shape"
                  value={form.launcher.shape}
                  options={["circle", "rounded", "pill"]}
                  onChange={(v) => set("launcher", { shape: v })}
                />
                <Choice
                  label="Size"
                  value={form.launcher.size}
                  options={[
                    ["small", "Small (48 px)"],
                    ["medium", "Medium (54 px)"],
                    ["large", "Large (60 px)"],
                  ]}
                  onChange={(v) => set("launcher", { size: v })}
                />
                <Choice
                  label="Icon"
                  value={form.launcher.icon}
                  options={[
                    ["chat", "Chat icon"],
                    ["logo", "Your logo"],
                  ]}
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
                  options={[
                    ["panel", "Panel"],
                    ["full", "Full screen"],
                  ]}
                  onChange={(v) => set("launcher", { opens_as: v })}
                />
                <div
                  className="full sub2"
                  style={{ fontWeight: 700, marginTop: 6 }}
                >
                  Desktop
                </div>
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
                <Field
                  label="Label text"
                  hint="Under 32 characters so it fits on one line."
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
                  hint="The designs use 8. 0 shows it as soon as the page loads."
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
                <Field label="Desktop options" group full>
                  {(
                    [
                      ["label_on", "Show the label beside the button"],
                      [
                        "notification_dot",
                        "Dot in the highlight colour until the chat is opened",
                      ],
                      [
                        "open_on_first_visit",
                        "Open the chat automatically on the first visit",
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
                <div
                  className="full sub2"
                  style={{ fontWeight: 700, marginTop: 6 }}
                >
                  Mobile
                </div>
                <Field label="From the side (px)">
                  <input
                    className="f"
                    type="number"
                    min={0}
                    max={200}
                    value={form.launcher.mobile_offset_x}
                    onChange={(e) =>
                      set("launcher", {
                        mobile_offset_x: Number(e.target.value),
                      })
                    }
                  />
                </Field>
                <Field
                  label="From the bottom (px)"
                  hint="Keep it above the website's own sticky Call / Book / WhatsApp bar."
                >
                  <input
                    className="f"
                    type="number"
                    min={0}
                    max={300}
                    value={form.launcher.mobile_offset_y}
                    onChange={(e) =>
                      set("launcher", {
                        mobile_offset_y: Number(e.target.value),
                      })
                    }
                  />
                </Field>
                <Field label="Mobile options" group full>
                  <label className="opt">
                    <input
                      type="checkbox"
                      checked={form.launcher.mobile_label}
                      onChange={(e) =>
                        set("launcher", { mobile_label: e.target.checked })
                      }
                    />
                    Show the label on mobile too (the designs: button only)
                  </label>
                  <span className="sub2" style={{ fontWeight: 400 }}>
                    On mobile the chat never opens by itself.
                  </span>
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
  group?: boolean;
  children: ReactNode;
}) {
  const Tag = group ? "div" : "label"; // a group holds its own checkboxes or radio buttons
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
  options: (string | [string, string])[];
  onChange: (v: string) => void;
}) {
  return (
    <Field label={label}>
      <select
        className="f"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => {
          const [v, text] = typeof o === "string" ? [o, words(o)] : o;
          return (
            <option key={v} value={v}>
              {text}
            </option>
          );
        })}
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
          value={valid(value) ? value : "#000000"}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          style={{ width: 44, height: 34, border: 0, background: "none" }}
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

// Sizes from the clinic designs (desktop panel 380 × 580, radius 20; launcher 60 px).
const PANEL: Record<string, [number, number]> = {
  small: [340, 540],
  medium: [380, 580],
  large: [420, 640],
};
const RADIUS: Record<string, number> = { square: 8, rounded: 20, round: 28 };
const BUTTON: Record<string, number> = { small: 48, medium: 54, large: 60 };
const FONT: Record<string, string> = {
  Figtree: "Figtree, system-ui, sans-serif",
  Inter: "Inter, system-ui, sans-serif",
  System: "system-ui, sans-serif",
};

/** A live preview from the unsaved form: desktop or mobile, chat open or closed, light or dark. Drawn at 80%. */
function Preview({ a }: { a: Appearance }) {
  const [open, setOpen] = useState(true);
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [dark, setDark] = useState(false);
  const mobile = device === "mobile";
  const c = a.colours;
  const night = dark && c.dark_mode;
  const card = night ? c.dark_card : "#FFFFFF";
  const ink = night ? c.dark_text : c.text;
  const line = night ? c.dark_line : c.line;
  const l = a.launcher;
  const left = l.position === "bottom_left";
  const sheet = mobile || l.opens_as === "full"; // on a phone the chat covers the screen
  const showLabel = mobile ? l.mobile_label : l.label_on;
  const button = BUTTON[l.size] * 0.8;
  const [w, h] = PANEL[a.widget.size];
  const panelBorder =
    a.widget.border === "none"
      ? "0"
      : `${a.widget.border === "strong" ? 2 : 1}px solid ${line}`;
  const shadow =
    a.widget.shadow === "none"
      ? "none"
      : `0 ${a.widget.shadow === "strong" ? 22 : 12}px ${a.widget.shadow === "strong" ? 50 : 30}px -14px ${c.main}66`;
  const offX = (mobile ? l.mobile_offset_x : l.offset_x) * 0.5 + 6;
  const offY = (mobile ? l.mobile_offset_y : l.offset_y) * 0.5 + 6;
  const seg = (on: boolean, label: string, click: () => void) => (
    <button className={on ? "on" : ""} onClick={click}>
      {label}
    </button>
  );
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
            color: c.main,
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
          background: c.highlight,
          border: `2px solid ${c.main}`,
        }}
      />
    </span>
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
        <div className="seg" style={{ marginLeft: 0 }}>
          {seg(open, "Open", () => setOpen(true))}
          {seg(!open, "Closed", () => setOpen(false))}
        </div>
        {c.dark_mode && (
          <div className="seg" style={{ marginLeft: 0 }}>
            {seg(!dark, "Light", () => setDark(false))}
            {seg(dark, "Dark", () => setDark(true))}
          </div>
        )}
      </div>
      <div
        style={{
          background: night ? c.dark_page : "#F4F1F2",
          borderRadius: mobile ? 28 : 12,
          border: mobile ? "8px solid #1F2937" : "1px solid #E3E8EF",
          width: mobile ? 250 : "100%",
          height: mobile ? 500 : Math.round(h * 0.8) + 90,
          margin: "0 auto",
          position: "relative",
          overflow: "hidden",
          opacity: a.look.enabled ? 1 : 0.5,
          fontFamily: FONT[a.widget.font],
          color: ink,
        }}
      >
        {/* A sketch of the clinic's web page behind the chat. */}
        <div
          style={{
            padding: 14,
            display: "flex",
            flexDirection: "column",
            gap: 8,
            opacity: night ? 0.3 : 1,
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
        </div>
        {open && (
          <div
            style={{
              position: "absolute",
              ...(sheet
                ? { inset: mobile ? "0" : 8 }
                : {
                    bottom: button + 24,
                    [left ? "left" : "right"]: 10,
                    width: Math.round(w * 0.8),
                    height: Math.round(h * 0.8),
                  }),
              background: card,
              borderRadius: mobile ? 0 : RADIUS[a.widget.radius],
              border: mobile ? 0 : panelBorder,
              boxShadow: mobile ? "none" : shadow,
              overflow: "hidden",
              fontSize: 12,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div
              style={{
                position: "relative",
                background: c.main,
                color: "#fff",
                padding: "10px 12px",
                overflow: "hidden",
              }}
            >
              {a.look.header_arc && (
                <i
                  style={{
                    position: "absolute",
                    right: -40,
                    top: -50,
                    width: 140,
                    height: 140,
                    borderRadius: "50%",
                    background: c.accent,
                    opacity: 0.35,
                  }}
                />
              )}
              <div
                style={{
                  position: "relative",
                  display: "flex",
                  gap: 10,
                  alignItems: "center",
                }}
              >
                {avatar}
                <div style={{ flex: 1, minWidth: 0, lineHeight: 1.25 }}>
                  <b style={{ display: "block", fontSize: 13.5 }}>
                    {a.look.name || "Assistant"}
                  </b>
                  {a.look.location && (
                    <span
                      style={{ display: "block", fontSize: 10.5, opacity: 0.9 }}
                    >
                      {a.look.location}
                    </span>
                  )}
                  <span
                    style={{ display: "block", fontSize: 10.5, opacity: 0.9 }}
                  >
                    {a.look.tagline || a.widget.header_text}
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
            </div>
            <div
              style={{
                padding: 10,
                display: "flex",
                flexDirection: "column",
                gap: 7,
                flex: 1,
              }}
            >
              <span
                style={{
                  alignSelf: "flex-start",
                  background: night ? c.dark_line : c.surface,
                  borderRadius: 12,
                  padding: "7px 9px",
                  maxWidth: "85%",
                }}
              >
                Hi, I&apos;m {a.look.name || "your assistant"}. How can I help
                you today?
              </span>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 6,
                }}
              >
                <span
                  style={{
                    background: c.main,
                    color: "#fff",
                    borderRadius: 12,
                    padding: 8,
                    fontWeight: 600,
                  }}
                >
                  Book Consultation
                </span>
                <span
                  style={{
                    border: `1px solid ${line}`,
                    borderRadius: 12,
                    padding: 8,
                    fontWeight: 600,
                    display: "flex",
                    gap: 6,
                    alignItems: "center",
                  }}
                >
                  <i
                    style={{
                      width: 16,
                      height: 16,
                      borderRadius: 6,
                      background: night ? c.dark_line : c.tint,
                    }}
                  />
                  Explore
                </span>
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <span
                  style={{
                    border: `1.5px solid ${c.main}`,
                    color: night ? ink : c.main_dark,
                    borderRadius: 999,
                    padding: "4px 10px",
                    fontWeight: 600,
                  }}
                >
                  IVF
                </span>
                <span
                  style={{
                    border: `1.5px solid ${c.whatsapp}`,
                    borderRadius: 999,
                    padding: "4px 10px",
                    fontWeight: 600,
                  }}
                >
                  WhatsApp us
                </span>
              </div>
              <span
                style={{
                  alignSelf: "flex-end",
                  background: c.main,
                  color: "#fff",
                  borderRadius: 12,
                  padding: "7px 9px",
                }}
              >
                I want to book
              </span>
              <span
                style={{
                  color: night ? ink : c.muted,
                  fontSize: 11,
                  fontWeight: 600,
                }}
              >
                ‹ Back · Main menu
              </span>
            </div>
            {mobile &&
              a.widget.mobile_contact_row &&
              a.widget.contact_buttons.length > 0 && (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: `repeat(${a.widget.contact_buttons.length}, 1fr)`,
                    gap: 6,
                    padding: "6px 8px",
                    borderTop: `1px solid ${line}`,
                  }}
                >
                  {a.widget.contact_buttons.map((b) => (
                    <span
                      key={b}
                      style={{
                        textAlign: "center",
                        padding: "6px 0",
                        borderRadius: 10,
                        fontWeight: 700,
                        background: b === "book" ? c.main : "transparent",
                        color: b === "book" ? "#fff" : ink,
                        border:
                          b === "book"
                            ? 0
                            : `1px solid ${b === "whatsapp" ? c.whatsapp : line}`,
                      }}
                    >
                      {b === "call"
                        ? "Call"
                        : b === "book"
                          ? "Book"
                          : "WhatsApp"}
                    </span>
                  ))}
                </div>
              )}
            {a.widget.footer_on && (
              <div
                style={{
                  textAlign: "center",
                  fontSize: 9.5,
                  color: night ? ink : c.muted,
                  padding: "5px 8px",
                  borderTop: `1px solid ${line}`,
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
              bottom: offY,
              [left ? "left" : "right"]: offX,
              height: button,
              minWidth: button,
              padding: l.shape === "pill" && showLabel && !open ? "0 14px" : 0,
              borderRadius: l.shape === "rounded" ? 14 : 999,
              background: l.background,
              color: l.icon_color,
              border:
                l.border === "none"
                  ? 0
                  : `${l.border === "strong" ? 2 : 1}px solid ${c.line}`,
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
                  width: button - 12,
                  height: button - 12,
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
            {l.shape === "pill" && showLabel && !open && (
              <span>{l.label_text}</span>
            )}
            {l.notification_dot && !open && (
              <i
                style={{
                  position: "absolute",
                  top: 1,
                  right: 1,
                  width: 11,
                  height: 11,
                  borderRadius: "50%",
                  background: c.highlight,
                  border: "2px solid #fff",
                }}
              />
            )}
          </button>
        )}
        {/* The label pill beside a round or rounded button (desktop; mobile only if turned on). */}
        {!open && showLabel && l.shape !== "pill" && (
          <span
            style={{
              position: "absolute",
              bottom: offY + button / 2 - 14,
              [left ? "left" : "right"]: offX + button + 8,
              background: "#fff",
              color: c.text,
              borderRadius: 999,
              padding: "6px 12px",
              fontSize: 12,
              fontWeight: 700,
              boxShadow: "0 6px 16px -8px rgba(0,0,0,.35)",
              whiteSpace: "nowrap",
            }}
          >
            {l.label_text}
          </span>
        )}
      </div>
    </div>
  );
}
