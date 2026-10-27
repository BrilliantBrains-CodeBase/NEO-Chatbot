"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
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
const QUESTION_KINDS: Record<string, string> = {
  text: "Text",
  number: "Number",
  email: "Email",
  phone: "Phone",
  date: "Date",
  time: "Time",
  choice: "Choice (buttons)",
  picture_choice: "Picture choice",
  rating: "Rating",
  yes_no: "Yes / No (two exits)",
  file: "File upload",
};
// The chat's usual wording (backend: DEFAULT_QUESTIONS in app/crm/flow.py), shown when a block keeps it.
const DEFAULT_QUESTIONS: Record<string, string> = {
  name: "May I know your full name?",
  phone: "Thanks, {name}. What is your contact number?",
  email: "What is your email address?",
  treatment: "Which treatment are you looking for?",
  doctor: "Which doctor would you like to see?",
  date: "Which date works for you?",
  time: "What time would you prefer?",
  booked_date: "Which date is your appointment booked for?",
  reason: "What would you like us to call you about?",
};

type Live = {
  doctors: { id: string; name: string }[];
  days: Record<string, string[]>;
};

/** Live doctors and free slots from the CRM (doctors' hours, leave and appointments), next 7 days. */
function useLive(
  clinicId: string | undefined,
  mode: string,
  on: boolean,
): Live {
  const [live, setLive] = useState<{ key: string; v: Live }>({
    key: "",
    v: { doctors: [], days: {} },
  });
  const key = `${clinicId}|${mode}`;
  useEffect(() => {
    if (!on || !clinicId) return;
    let alive = true;
    api<Live>(`/v1/crm/slots?clinic=${clinicId}&mode=${mode}&days=7`).then(
      (v) => alive && setLive({ key, v }),
      () => {},
    );
    return () => {
      alive = false;
    };
  }, [clinicId, mode, on, key]);
  return live.key === key ? live.v : { doctors: [], days: {} };
}

function LiveSlots({ live }: { live: Live }) {
  const days = Object.keys(live.days).sort().slice(0, 4);
  return (
    <Row label="Free slots now (live from the CRM)">
      {days.length === 0 ? (
        <span style={{ fontWeight: 400 }}>
          No free slots in the next 7 days.
        </span>
      ) : (
        days.map((d) => (
          <span key={d} style={{ fontWeight: 400 }}>
            <b>
              {new Date(d + "T00:00:00").toLocaleDateString("en-IN", {
                weekday: "short",
                day: "numeric",
                month: "short",
              })}
            </b>
            : {live.days[d].length} free, from {live.days[d][0]}
          </span>
        ))
      )}
    </Row>
  );
}

export default function BlockSettings({
  block,
  onChange,
  onButtons,
  services,
  fields,
  clinicId,
}: {
  clinicId: string | undefined;
  services: Service[];
  fields: string[]; // built-in and the clinic's own
  block: FlowNode;
  onChange: (patch: Partial<FlowNode>) => void;
  onButtons: (buttons: FlowButton[]) => void;
}) {
  const s = block.settings;
  const live = useLive(
    clinicId,
    block.type === "online" ? "online" : "in_clinic",
    LEAD.has(block.type),
  );
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
      {block.type !== "opening" && (
        <Row label="Shown to patients">
          <div className="wf-seg">
            <button
              className={block.enabled !== false ? "on" : ""}
              onClick={() => onChange({ enabled: true })}
            >
              ON
            </button>
            <button
              className={block.enabled === false ? "on" : ""}
              onClick={() => onChange({ enabled: false })}
            >
              OFF
            </button>
          </div>
          {block.enabled !== false && (
            <>
              <span style={{ fontWeight: 400 }}>
                Schedule (optional): show only
              </span>
              <div className="wf-btn">
                <span style={{ fontWeight: 400 }}>from</span>
                <input
                  type="date"
                  value={block.show_from ?? ""}
                  onChange={(e) =>
                    onChange({ show_from: e.target.value || null })
                  }
                />
                <span style={{ fontWeight: 400 }}>to</span>
                <input
                  type="date"
                  value={block.show_until ?? ""}
                  onChange={(e) =>
                    onChange({ show_until: e.target.value || null })
                  }
                />
              </div>
              <label
                style={{
                  fontWeight: 400,
                  display: "flex",
                  gap: 6,
                  alignItems: "center",
                }}
              >
                <input
                  type="checkbox"
                  checked={!!block.clinic_hours_only}
                  onChange={(e) =>
                    onChange({ clinic_hours_only: e.target.checked })
                  }
                />
                only while the clinic is open
              </label>
            </>
          )}
        </Row>
      )}

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
      {block.type === "set_field" && (
        <>
          <Row label="Field">
            <select
              value={String(s.field ?? "")}
              onChange={(e) => set({ field: e.target.value })}
            >
              <option value="">Choose…</option>
              {fields.map((f) => (
                <option key={f}>{f}</option>
              ))}
            </select>
          </Row>
          {text(
            "value",
            "Value (may use other fields, e.g. {treatment})",
            1,
            200,
          )}
        </>
      )}
      {block.type === "question" && (
        <>
          {text("question", "Question", 2, 300)}
          <Row label="Answer type">
            <select
              value={String(s.kind ?? "text")}
              onChange={(e) => set({ kind: e.target.value })}
            >
              {Object.entries(QUESTION_KINDS).map(([k, l]) => (
                <option key={k} value={k}>
                  {l}
                </option>
              ))}
            </select>
          </Row>
          <Row label="Save the answer in">
            <select
              value={String(s.field ?? "")}
              onChange={(e) => set({ field: e.target.value })}
            >
              <option value="">Choose…</option>
              {fields.map((f) => (
                <option key={f}>{f}</option>
              ))}
            </select>
          </Row>
          {(s.kind === "choice" || s.kind === "picture_choice") && (
            <Row label="Options (2 to 12)">
              {((s.options as { label: string; image?: string }[]) ?? []).map(
                (o, i, all) => (
                  <div key={i} style={{ display: "flex", gap: 4 }}>
                    <input
                      value={o.label}
                      maxLength={40}
                      placeholder="Label"
                      onChange={(e) =>
                        set({
                          options: all.map((x, j) =>
                            j === i ? { ...x, label: e.target.value } : x,
                          ),
                        })
                      }
                    />
                    {s.kind === "picture_choice" && (
                      <input
                        value={o.image ?? ""}
                        maxLength={300}
                        placeholder="Picture https://…"
                        onChange={(e) =>
                          set({
                            options: all.map((x, j) =>
                              j === i ? { ...x, image: e.target.value } : x,
                            ),
                          })
                        }
                      />
                    )}
                    <button
                      type="button"
                      onClick={() =>
                        set({ options: all.filter((_, j) => j !== i) })
                      }
                    >
                      ×
                    </button>
                  </div>
                ),
              )}
              {((s.options as unknown[]) ?? []).length < 12 && (
                <button
                  type="button"
                  onClick={() =>
                    set({
                      options: [
                        ...((s.options as unknown[]) ?? []),
                        { label: "", image: "" },
                      ],
                    })
                  }
                >
                  + Add option
                </button>
              )}
            </Row>
          )}
          {(s.kind === "number" || s.kind === "rating") && (
            <Row label="Lowest and highest">
              <div style={{ display: "flex", gap: 4 }}>
                {(["minimum", "maximum"] as const).map((k) => (
                  <input
                    key={k}
                    type="number"
                    placeholder={k}
                    value={s[k] == null ? "" : String(s[k])}
                    onChange={(e) =>
                      set({
                        [k]:
                          e.target.value === "" ? null : Number(e.target.value),
                      })
                    }
                  />
                ))}
              </div>
            </Row>
          )}
          {s.kind === "file" &&
            text("consent_text", "Consent shown before upload", 2, 300)}
          <Row label="If the answer is not understood, ask again">
            <select
              value={String(s.retries ?? 2)}
              onChange={(e) => set({ retries: Number(e.target.value) })}
            >
              {[0, 1, 2, 3].map((n) => (
                <option key={n} value={n}>
                  {n} times
                </option>
              ))}
            </select>
          </Row>
          <label style={{ display: "flex", gap: 6, fontSize: 12 }}>
            <input
              type="checkbox"
              checked={s.required !== false}
              onChange={(e) => set({ required: e.target.checked })}
            />
            answer required (no skip)
          </label>
        </>
      )}
      <span className="sub2" style={{ fontSize: 11 }}>
        Messages can use fields, e.g. Thanks {"{name}"}:{" "}
        {fields.map((f) => `{${f}}`).join(" ")}
      </span>
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
          {text(
            "treatments_label",
            "View treatments button text (empty: no button)",
            1,
            40,
          )}
          {String(s.treatments_label ?? "").trim() && (
            <Row label="This doctor's treatments (each opens its card)">
              <div className="wf-checks">
                {services.map((t) => {
                  const picked = (s.treatments as string[]) ?? [];
                  return (
                    <label key={t.name}>
                      <input
                        type="checkbox"
                        checked={picked.includes(t.name)}
                        onChange={(e) =>
                          set({
                            treatments: e.target.checked
                              ? [...picked, t.name]
                              : picked.filter((x) => x !== t.name),
                          })
                        }
                      />
                      {t.name}
                    </label>
                  );
                })}
              </div>
            </Row>
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
          <Row label="Wording of each question (empty: the usual wording)">
            {((s.fields as string[]) ?? []).map((f) => {
              const questions = (s.questions as Record<string, string>) ?? {};
              return (
                <input
                  key={f}
                  maxLength={200}
                  placeholder={DEFAULT_QUESTIONS[f] ?? f}
                  value={questions[f] ?? ""}
                  onChange={(e) => {
                    const next = { ...questions, [f]: e.target.value };
                    if (!e.target.value.trim()) delete next[f];
                    set({ questions: next });
                  }}
                />
              );
            })}
            <span style={{ fontWeight: 400 }}>
              Answers are checked (Indian mobile, email, a bookable day, a free
              slot).
            </span>
          </Row>
          <Row label="Wrong answer: ask again">
            <select
              value={Number(s.retries ?? 2)}
              onChange={(e) => set({ retries: Number(e.target.value) })}
            >
              {[0, 1, 2, 3].map((n) => (
                <option key={n} value={n}>
                  {n === 0
                    ? "No, offer a call back"
                    : `Up to ${n} time${n > 1 ? "s" : ""}, then offer a call back`}
                </option>
              ))}
            </select>
          </Row>
          {((s.fields as string[]) ?? []).includes("doctor") ||
          block.type === "book" ||
          block.type === "online" ? (
            <Row label="Doctor">
              <select
                value={String(s.doctor ?? "")}
                onChange={(e) => set({ doctor: e.target.value })}
              >
                <option value="">Ask the patient, or any free doctor</option>
                {live.doctors.map((d) => (
                  <option key={d.id} value={d.name}>
                    Always {d.name}
                  </option>
                ))}
              </select>
            </Row>
          ) : null}
          {(block.type === "book" ||
            block.type === "online" ||
            block.type === "reschedule") && <LiveSlots live={live} />}
          <Row label="Consent before saving the lead">
            <label
              style={{
                display: "flex",
                gap: 6,
                alignItems: "center",
                fontWeight: 400,
              }}
            >
              <input
                type="checkbox"
                checked={s.consent !== false}
                onChange={(e) => set({ consent: e.target.checked })}
              />
              Ask for consent
            </label>
            {s.consent !== false && (
              <textarea
                rows={2}
                maxLength={300}
                value={String(s.consent_text ?? "")}
                onChange={(e) => set({ consent_text: e.target.value })}
              />
            )}
          </Row>
          {text("final_message", "Final message (optional)", 2, 500)}
        </>
      )}

      {(MENUS.has(block.type) ||
        ["answer", "emergency", "doctor_card"].includes(block.type)) && (
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
