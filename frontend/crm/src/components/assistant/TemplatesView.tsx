"use client";

import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import Icon, { type IconName } from "@/components/crm/Icon";
import { api, ApiError } from "@/lib/api";

// Dashboard → Templates: how the chat menu looks (Tiles, Pills or Cards), previewed with the clinic's own
// buttons. Choosing one saves the draft; patients see it after Publish.

type MenuItem = { label: string; icon: string | null; variant: string | null };
type Settings = {
  draft: {
    template: { id: string; columns: number; filled_button: string };
    appearance: {
      look: { name: string };
      colours: { main: string; highlight: string };
    };
  };
  published: { template?: { id: string } };
  changed: boolean;
  version: number;
  menu: MenuItem[];
};

const TEMPLATES = [
  {
    id: "tiles",
    name: "Tiles",
    desc: "Colourful tiles, three per row, with a full-width emergency bar. Big, easy taps.",
    best: "six or more options, and patients who prefer big buttons.",
    main: "#3E74D9",
    highlight: "#FFCC70",
  },
  {
    id: "pills",
    name: "Pills",
    desc: "Rounded quick-reply buttons that wrap under the greeting. Light and conversational.",
    best: "a short menu of 4 to 7 actions and a chat-first feel.",
    main: "#481E0B", // Derma Solutions design
    highlight: "#FFCC70",
  },
  {
    id: "cards",
    name: "Cards",
    desc: "Two-column cards with an icon and a label. Calm and easy to scan.",
    best: "longer button names and a clean, professional look.",
    main: "#3D203F", // Neo Fertility design
    highlight: "#FFCC70",
  },
] as const;

// The chat's icon names, drawn with the closest CRM icon.
const ICON: Record<string, IconName> = {
  cal: "cal",
  search: "search",
  steth: "doc",
  globe: "info",
  phone: "ph",
  chat: "wa",
  sos: "alert",
};

export default function TemplatesView() {
  const { clinic, me, toast } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const [loaded, setLoaded] = useState<{
    clinic: string;
    s?: Settings;
    error?: string;
  }>({ clinic: "" });
  const [ownColours, setOwnColours] = useState(true); // preview in the clinic's colours, or each template's
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Settings>(`/v1/crm/console/${clinicId}/settings`).then(
      (s) => live && setLoaded({ clinic: clinicId, s }),
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

  async function call(
    path: string,
    method: string,
    body: object | undefined,
    done: string,
  ) {
    if (!clinicId) return;
    setBusy(true);
    try {
      const s = await api<Settings>(`/v1/crm/console/${clinicId}/${path}`, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      });
      setLoaded({ clinic: clinicId, s });
      toast(done);
    } catch (e) {
      toast(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const s = loaded.clinic === clinicId ? loaded.s : undefined;
  if (loaded.clinic === clinicId && loaded.error)
    return <div className="warnbox">{loaded.error}</div>;
  if (!s) return <p className="sub2">Loading…</p>;
  const current = s.draft.template.id;
  const tpl = s.draft.template;
  const saveTpl = (
    patch: Partial<Settings["draft"]["template"]>,
    done: string,
  ) => call("settings/template", "PUT", { ...tpl, ...patch }, done);
  const live = s.published.template?.id;

  return (
    <>
      <div className="ph">
        <div>
          <h1>Templates</h1>
        </div>
        <button
          className="btn"
          disabled={busy || !s.changed}
          onClick={() => call("publish", "POST", undefined, "Published")}
        >
          Publish
        </button>
      </div>
      <label
        className="row"
        style={{ gap: 8, marginBottom: 14, cursor: "pointer" }}
      >
        <input
          type="checkbox"
          checked={!ownColours}
          onChange={(e) => setOwnColours(!e.target.checked)}
        />
        Use each template&apos;s own colours{" "}
        <span className="sub2">
          (off: every template in {clinic}&apos;s colours)
        </span>
      </label>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
          gap: 16,
        }}
      >
        {TEMPLATES.map((t) => {
          const colours = ownColours
            ? s.draft.appearance.colours
            : { main: t.main, highlight: t.highlight };
          return (
            <section
              key={t.id}
              className="card"
              style={{
                borderColor: current === t.id ? "var(--brand)" : undefined,
                borderWidth: current === t.id ? 2 : 1,
              }}
            >
              <MiniChat
                template={t.id}
                name={s.draft.appearance.look.name}
                colours={colours}
                menu={s.menu}
                columns={tpl.columns}
                filled={tpl.filled_button}
              />
              <h3 style={{ marginTop: 12 }}>
                {t.name}
                <small>
                  {current === t.id && (
                    <span className="badge b-bk">Chosen</span>
                  )}{" "}
                  {live === t.id && <span className="badge b-vi">Live</span>}
                </small>
              </h3>
              <p className="sub2" style={{ margin: "0 0 6px" }}>
                {t.desc}
              </p>
              <p className="sub2" style={{ margin: "0 0 12px" }}>
                <b>Best for</b> {t.best}
              </p>
              {current === t.id ? (
                <button className="pill" disabled>
                  ✓ Chosen
                </button>
              ) : (
                <button
                  className="btn"
                  disabled={busy}
                  onClick={() =>
                    saveTpl(
                      { id: t.id },
                      `${t.name} chosen. Publish to show it to patients.`,
                    )
                  }
                >
                  Use {t.name}
                </button>
              )}
            </section>
          );
        })}
      </div>
    </>
  );
}

/** The opening of the chat in one template, with the clinic's own menu buttons. */
function MiniChat({
  template,
  name,
  colours,
  menu,
  columns,
  filled,
}: {
  template: string;
  name: string;
  colours: { main: string; highlight: string };
  menu: MenuItem[];
  columns: number;
  filled: string;
}) {
  const sos = menu.filter((m) => m.variant === "sos");
  const rest = menu.filter((m) => m.variant !== "sos");
  const tile = (m: MenuItem, wide = false) => (
    <span
      key={m.label}
      style={{
        gridColumn: wide ? "1 / -1" : undefined,
        display: "flex",
        flexDirection: template === "tiles" && !wide ? "column" : "row",
        alignItems: "center",
        gap: 6,
        padding: template === "tiles" ? "8px 4px" : "8px 10px",
        borderRadius: 10,
        background:
          m.label === filled
            ? colours.main
            : m.variant === "sos"
              ? "#FDECEC"
              : m.variant === "wa"
                ? "#E8F7EE"
                : template === "tiles"
                  ? "#F1F5FD"
                  : "#fff",
        border: template === "cards" ? "1px solid #E3E8EF" : 0,
        color:
          m.label === filled
            ? "#fff"
            : m.variant === "sos"
              ? "#B42318"
              : m.variant === "wa"
                ? "#1F7A45"
                : "#1F2937",
        fontSize: 11,
        fontWeight: 600,
        textAlign: template === "tiles" && !wide ? "center" : "left",
        justifyContent: wide ? "center" : undefined,
      }}
    >
      <span
        style={{
          color:
            m.label === filled ? "#fff" : m.variant ? undefined : colours.main,
          width: 16,
          height: 16,
          display: "inline-flex",
        }}
      >
        <Icon name={ICON[m.icon ?? ""] ?? "info"} />
      </span>
      {m.label}
    </span>
  );
  return (
    <div style={{ background: "#F3F5F9", borderRadius: 12, padding: 10 }}>
      <div
        style={{
          background: "#fff",
          borderRadius: 12,
          overflow: "hidden",
          boxShadow: "0 6px 18px -10px rgba(22,32,46,.35)",
        }}
      >
        <div
          style={{
            background: colours.main,
            color: "#fff",
            padding: "8px 10px",
            display: "flex",
            gap: 8,
            alignItems: "center",
            fontSize: 12,
          }}
        >
          <span
            style={{
              position: "relative",
              width: 26,
              height: 26,
              borderRadius: "50%",
              background: "#fff",
              color: colours.main,
              display: "grid",
              placeItems: "center",
              fontWeight: 800,
            }}
          >
            {name.charAt(0)}
            <i
              style={{
                position: "absolute",
                right: -1,
                bottom: -1,
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: colours.highlight,
                border: `2px solid ${colours.main}`,
              }}
            />
          </span>
          <b>{name}</b>
        </div>
        <div
          style={{
            padding: 10,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <span
            style={{
              background: "#F1F3F7",
              borderRadius: 10,
              padding: "6px 8px",
              fontSize: 11.5,
              alignSelf: "flex-start",
            }}
          >
            How can I help you today?
          </span>
          {template === "pills" ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {menu.map((m) => (
                <span
                  key={m.label}
                  style={{
                    border: `1px solid ${m.variant === "sos" ? "#E5484D" : colours.main}`,
                    color: m.variant === "sos" ? "#B42318" : colours.main,
                    borderRadius: 999,
                    padding: "4px 9px",
                    fontSize: 11,
                    fontWeight: 600,
                  }}
                >
                  {m.label}
                </span>
              ))}
            </div>
          ) : (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: `repeat(${columns}, 1fr)`,
                gap: 6,
              }}
            >
              {rest.map((m) => tile(m))}
              {sos.map((m) => tile(m, true))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
