"use client";

import type { ReactNode } from "react";
import type { Service } from "./WorkflowView";
import {
  BUTTON_ACTIONS,
  buttonsOf,
  KINDS,
  MENUS,
  type FlowButton,
  type FlowNode,
} from "./blocks";

// The selected block's settings (right side of the canvas). Appointment blocks get their full field settings
// in step W4; here: mode, which fields, final message.

const FIELDS: [string, string][] = [
  ["name", "Name"],
  ["phone", "Mobile"],
  ["email", "Email"],
  ["treatment", "Treatment"],
  ["doctor", "Doctor"],
  ["date", "Date"],
  ["time", "Time"],
  ["booked_date", "Booked date"],
  ["reason", "Reason"],
];
const LEAD = new Set(["book", "online", "cancel", "reschedule", "callback"]);

export default function BlockSettings({
  block,
  onChange,
  onButtons,
  services,
}: {
  services: Service[];
  block: FlowNode;
  onChange: (patch: Partial<FlowNode>) => void;
  onButtons: (buttons: FlowButton[]) => void;
}) {
  const s = block.settings;
  const set = (patch: Record<string, unknown>) =>
    onChange({ settings: { ...s, ...patch } });
  const kind = KINDS[block.type];
  const text = (key: string, label: string, rows = 1, max = 1500) => (
    <Row label={label}>
      {rows > 1 ? (
        <textarea
          rows={rows}
          maxLength={max}
          value={String(s[key] ?? "")}
          onChange={(e) => set({ [key]: e.target.value })}
        />
      ) : (
        <input
          maxLength={max}
          value={String(s[key] ?? "")}
          onChange={(e) => set({ [key]: e.target.value })}
        />
      )}
    </Row>
  );

  return (
    <div className="wf-form">
      <div className="wf-kind" style={{ color: kind?.color }}>
        {kind?.label}
      </div>
      <span className="sub2">{kind?.hint}</span>
      <Row label="Name on the canvas">
        <input
          maxLength={60}
          value={block.title}
          onChange={(e) => onChange({ title: e.target.value })}
        />
      </Row>

      {block.type === "opening" && text("welcome", "Welcome message", 3, 500)}
      {MENUS.has(block.type) &&
        block.type !== "opening" &&
        text("message", "Message above the buttons", 3)}
      {(block.type === "answer" || block.type === "emergency") &&
        text("text", "Text", 4, 2000)}
      {block.type === "typed" &&
        text(
          "topic",
          "Topic (its typed phrases are approved in step W7)",
          1,
          40,
        )}
      {(block.type === "link" || block.type === "whatsapp") &&
        text(
          "url",
          block.type === "whatsapp"
            ? "WhatsApp link (https://wa.me/…)"
            : "Web address (https://…)",
          1,
          600,
        )}
      {block.type === "call" && text("number", "Phone number", 1, 16)}
      {block.type === "treatment_list" && (
        <Row label="Category (its treatments come live from Clinic info → Services)">
          <select
            value={String(s.category ?? "")}
            onChange={(e) => set({ category: e.target.value })}
          >
            <option value="">Choose…</option>
            {[...new Set(services.map((t) => t.category).filter(Boolean))].map(
              (c) => (
                <option key={c}>{c}</option>
              ),
            )}
          </select>
          <span className="sub2" style={{ fontWeight: 400 }}>
            {services
              .filter((t) => t.show && t.category === s.category)
              .map((t) => t.name)
              .join(" · ") || "No treatments shown in this category."}{" "}
            To change them, edit Clinic info → Services.
          </span>
        </Row>
      )}
      {block.type === "treatment_card" &&
        text("treatment", "Treatment (from Clinic info → Services)", 1, 80)}
      {block.type === "doctor_card" && (
        <>
          {text("doctor", "Doctor's name", 1, 80)}
          {text("title", "Title (e.g. Founder and Director)", 1, 120)}
          {text("qualifications", "Qualifications", 2, 300)}
          {text("photo", "Photo (https://…, optional)", 1, 300)}
          {text("about", "About (optional)", 3, 1000)}
          <Row label="Figures on the card (up to 6, e.g. 20+ Years experience)">
            {((s.stats as { value: string; label: string }[]) ?? []).map(
              (f, i, all) => (
                <div key={i} className="wf-btn">
                  <input
                    style={{ maxWidth: 80 }}
                    maxLength={12}
                    value={f.value}
                    onChange={(e) =>
                      set({
                        stats: all.map((x, k) =>
                          k === i ? { ...x, value: e.target.value } : x,
                        ),
                      })
                    }
                  />
                  <input
                    maxLength={24}
                    value={f.label}
                    onChange={(e) =>
                      set({
                        stats: all.map((x, k) =>
                          k === i ? { ...x, label: e.target.value } : x,
                        ),
                      })
                    }
                  />
                  <button
                    aria-label="Remove"
                    onClick={() =>
                      set({ stats: all.filter((_, k) => k !== i) })
                    }
                  >
                    ✕
                  </button>
                </div>
              ),
            )}
            {((s.stats as unknown[]) ?? []).length < 6 && (
              <button
                className="pill"
                style={{ alignSelf: "flex-start" }}
                onClick={() =>
                  set({
                    stats: [
                      ...((s.stats as unknown[]) ?? []),
                      { value: "", label: "" },
                    ],
                  })
                }
              >
                + Add a figure
              </button>
            )}
          </Row>
          {text(
            "book_label",
            "Book button text (empty: no button; draw its line to a booking block)",
            1,
            40,
          )}
          {text(
            "profile_url",
            "Full profile link (https://…, optional)",
            1,
            600,
          )}
        </>
      )}

      {LEAD.has(block.type) && (
        <>
          <Row label="How the questions are asked">
            <div className="wf-seg">
              {(
                [
                  ["steps", "Step by step"],
                  ["form", "Form"],
                ] as const
              ).map(([m, label]) => (
                <button
                  key={m}
                  className={s.mode === m ? "on" : ""}
                  onClick={() => set({ mode: m })}
                >
                  {label}
                </button>
              ))}
            </div>
          </Row>
          <Row label="Questions asked (in this order)">
            <div className="wf-checks">
              {FIELDS.map(([f, label]) => {
                const fields = (s.fields as string[]) ?? [];
                return (
                  <label key={f}>
                    <input
                      type="checkbox"
                      checked={fields.includes(f)}
                      onChange={(e) =>
                        set({
                          fields: e.target.checked
                            ? FIELDS.map(([k]) => k).filter(
                                (k) => k === f || fields.includes(k),
                              )
                            : fields.filter((k) => k !== f),
                        })
                      }
                    />
                    {label}
                  </label>
                );
              })}
            </div>
          </Row>
          {block.type === "book" &&
            text("treatment", "Treatment filled in (optional)", 1, 80)}
          {block.type === "callback" &&
            text("topic", "What the call back is about (optional)", 1, 120)}
          {text("final_message", "Final message (optional)", 2, 500)}
        </>
      )}

      {(MENUS.has(block.type) ||
        ["answer", "emergency"].includes(block.type)) && (
        <Buttons
          list={buttonsOf(block)}
          onChange={onButtons}
          prefix={block.type === "opening" ? "m" : "b"}
        />
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="wf-row">
      <span>{label}</span>
      {children}
    </label>
  );
}

function Buttons({
  list,
  onChange,
  prefix,
}: {
  list: FlowButton[];
  onChange: (b: FlowButton[]) => void;
  prefix: string;
}) {
  const set = (i: number, patch: Partial<FlowButton>) =>
    onChange(list.map((b, k) => (k === i ? { ...b, ...patch } : b)));
  const move = (i: number, by: number) => {
    const j = i + by;
    if (j < 0 || j >= list.length) return;
    const out = [...list];
    [out[i], out[j]] = [out[j], out[i]];
    onChange(out);
  };
  const nextId = () => {
    let i = list.length + 1;
    while (list.some((b) => b.id === `${prefix}${i}`)) i++;
    return `${prefix}${i}`;
  };
  return (
    <div className="wf-row">
      <span>Buttons (each has its own dot on the canvas)</span>
      {list.map((b, i) => (
        <div key={b.id} className="wf-btnbox">
          <div className="wf-btn">
            <button aria-label="Move up" onClick={() => move(i, -1)}>
              ▲
            </button>
            <button aria-label="Move down" onClick={() => move(i, 1)}>
              ▼
            </button>
            <input
              maxLength={40}
              value={b.label}
              onChange={(e) => set(i, { label: e.target.value })}
              style={{ opacity: b.visible === false ? 0.5 : 1 }}
            />
            <label title="Shown in the chat">
              <input
                type="checkbox"
                checked={b.visible !== false}
                onChange={(e) => set(i, { visible: e.target.checked })}
              />
            </label>
            <button
              aria-label="Remove"
              onClick={() => onChange(list.filter((_, k) => k !== i))}
            >
              ✕
            </button>
          </div>
          <div className="wf-btn">
            <select
              value={b.action ?? ""}
              onChange={(e) => set(i, { action: e.target.value, value: "" })}
            >
              {BUTTON_ACTIONS.map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
            {b.action && (
              <input
                maxLength={600}
                placeholder={BUTTON_ACTIONS.find(([k]) => k === b.action)?.[2]}
                value={b.value ?? ""}
                onChange={(e) => set(i, { value: e.target.value })}
              />
            )}
          </div>
        </div>
      ))}
      {list.length < 12 && (
        <button
          className="pill"
          style={{ alignSelf: "flex-start" }}
          onClick={() =>
            onChange([
              ...list,
              { id: nextId(), label: "New button", visible: true },
            ])
          }
        >
          + Add button
        </button>
      )}
    </div>
  );
}
