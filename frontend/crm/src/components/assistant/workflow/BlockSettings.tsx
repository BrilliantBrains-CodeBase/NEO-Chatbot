"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { fitImage, ImageError } from "@/lib/image";
import type { Service } from "./WorkflowView";
import {
  BUTTON_ACTIONS,
  buttonsOf,
  KINDS,
  MENUS,
  type FlowButton,
  type FlowNode,
  type Phrase,
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
const LEAD = new Set([
  "book",
  "online",
  "cancel",
  "reschedule",
  "callback",
  "follow_up",
]);
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
        <span style={{ fontWeight: 450 }}>
          No free slots in the next 7 days.
        </span>
      ) : (
        days.map((d) => (
          <span key={d} style={{ fontWeight: 450 }}>
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
  phrases,
  onPhrases,
  onApprove,
  dirty,
  services,
  fields,
  clinicId,
  blocks,
}: {
  clinicId: string | undefined;
  services: Service[];
  blocks: FlowNode[]; // for Go to

  fields: string[]; // built-in and the clinic's own
  block: FlowNode;
  onChange: (patch: Partial<FlowNode>) => void;
  onButtons: (buttons: FlowButton[]) => void;
  phrases: Phrase[]; // the whole flow's
  onPhrases: (p: Phrase[]) => void;
  onApprove: (ids: string[]) => void;
  dirty: boolean;
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
  const [photoError, setPhotoError] = useState("");
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
              <span style={{ fontWeight: 450 }}>
                Schedule (optional): show only
              </span>
              <div className="wf-btn">
                <span style={{ fontWeight: 450 }}>from</span>
                <input
                  type="date"
                  value={block.show_from ?? ""}
                  onChange={(e) =>
                    onChange({ show_from: e.target.value || null })
                  }
                />
                <span style={{ fontWeight: 450 }}>to</span>
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
                  fontWeight: 450,
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

      {!["typed", "set_field", "goto", "condition", "clinic_open"].includes(
        block.type,
      ) && (
        <Row label="Typing dots before the message">
          <select
            value={Number(block.typing ?? 0)}
            onChange={(e) => onChange({ typing: Number(e.target.value) })}
          >
            {[0, 0.5, 1, 1.5, 2, 3, 5].map((n) => (
              <option key={n} value={n}>
                {n === 0 ? "None" : `${n} s`}
              </option>
            ))}
          </select>
        </Row>
      )}
      {block.type === "media" && (
        <>
          <Row label="Kind">
            <select
              value={String(s.kind ?? "image")}
              onChange={(e) => set({ kind: e.target.value })}
            >
              <option value="image">Image</option>
              <option value="video">Video</option>
              <option value="file">File (PDF)</option>
              <option value="map">Map (Google Maps link)</option>
            </select>
          </Row>
          {text("url", "Web address (https://…)", 1, 600)}
          {text("caption", "Caption (optional)", 2, 300)}
        </>
      )}
      {block.type === "carousel" && (
        <>
          {text("message", "Message above the cards (optional)", 2, 500)}
          <Row label="Cards">
            <select
              value={String(s.source ?? "treatments")}
              onChange={(e) => set({ source: e.target.value })}
            >
              <option value="treatments">
                Treatments, live from Clinic info → Services
              </option>
              <option value="custom">My own cards</option>
            </select>
          </Row>
          {s.source !== "custom" ? (
            <Row label="Category (empty: all shown treatments)">
              <select
                value={String(s.category ?? "")}
                onChange={(e) => set({ category: e.target.value })}
              >
                <option value="">All</option>
                {[
                  ...new Set(services.map((t) => t.category).filter(Boolean)),
                ].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </Row>
          ) : (
            <Cards
              cards={(s.cards as CardT[]) ?? []}
              onChange={(cards) => set({ cards })}
            />
          )}
        </>
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
      {["location", "reviews", "faq", "knowledge"].includes(block.type) &&
        text(
          "message",
          block.type === "knowledge"
            ? "Message asking for the question"
            : "Message (optional)",
          2,
          block.type === "knowledge" ? 300 : 500,
        )}
      {block.type === "location" && (
        <Row label="Shown with the address (live from Contact & hours)">
          {(
            [
              ["map", "Map link"],
              ["hours", "Today's hours, open / closed now"],
            ] as const
          ).map(([k, label]) => (
            <label key={k} style={{ display: "flex", gap: 6, fontWeight: 450 }}>
              <input
                type="checkbox"
                checked={s[k] !== false}
                onChange={(e) => set({ [k]: e.target.checked })}
              />
              {label}
            </label>
          ))}
        </Row>
      )}
      {block.type === "knowledge" && (
        <Row label="Answer only from these Knowledge base topics (none ticked: all)">
          {(
            [
              ["clinic_info", "Clinic info"],
              ["treatment", "Treatments"],
              ["cost", "Costs"],
              ["doctor", "Doctors"],
              ["policy", "Policies"],
              ["other", "Other"],
            ] as const
          ).map(([k, label]) => {
            const topics = (s.topics as string[] | undefined) ?? [];
            return (
              <label
                key={k}
                style={{ display: "flex", gap: 6, fontWeight: 450 }}
              >
                <input
                  type="checkbox"
                  checked={topics.includes(k)}
                  onChange={(e) =>
                    set({
                      topics: e.target.checked
                        ? [...topics, k]
                        : topics.filter((x) => x !== k),
                    })
                  }
                />
                {label}
              </label>
            );
          })}
        </Row>
      )}
      {block.type === "reviews" && (
        <Row label="How many reviews (newest first, from Clinic info → Reviews)">
          <select
            value={Number(s.count ?? 3)}
            onChange={(e) => set({ count: Number(e.target.value) })}
          >
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </Row>
      )}
      {block.type === "faq" && (
        <Row label="Questions (each a button; a tap shows its answer)">
          {((s.items as { question: string; answer: string }[]) ?? []).map(
            (f, i, all) => (
              <div
                key={i}
                style={{ display: "flex", flexDirection: "column", gap: 4 }}
              >
                <div style={{ display: "flex", gap: 4 }}>
                  <input
                    maxLength={120}
                    placeholder="Question"
                    value={f.question}
                    onChange={(e) =>
                      set({
                        items: all.map((x, k) =>
                          k === i ? { ...x, question: e.target.value } : x,
                        ),
                      })
                    }
                  />
                  <button
                    aria-label="Remove"
                    onClick={() =>
                      set({ items: all.filter((_, k) => k !== i) })
                    }
                  >
                    ✕
                  </button>
                </div>
                <textarea
                  rows={2}
                  maxLength={1500}
                  placeholder="Answer"
                  value={f.answer}
                  onChange={(e) =>
                    set({
                      items: all.map((x, k) =>
                        k === i ? { ...x, answer: e.target.value } : x,
                      ),
                    })
                  }
                />
              </div>
            ),
          )}
          {((s.items as unknown[]) ?? []).length < 20 && (
            <button
              className="pill"
              style={{ alignSelf: "flex-start" }}
              onClick={() =>
                set({
                  items: [
                    ...((s.items as unknown[]) ?? []),
                    { question: "", answer: "" },
                  ],
                })
              }
            >
              + Add a question
            </button>
          )}
        </Row>
      )}
      {block.type === "knowledge" && (
        <span className="sub2" style={{ fontSize: "var(--fs-tiny)" }}>
          Answers come only from the Knowledge base&apos;s approved answers (no
          AI writing, no self-learning). Draw &quot;not found&quot; to a call
          back or a menu.
        </span>
      )}
      {block.type === "check_appointment" &&
        text("message", "Message asking for the phone number", 2, 300)}
      {block.type === "check_appointment" && (
        <Row label="Shows upcoming appointments from CRM → Appointments, matched by phone">
          <label style={{ display: "flex", gap: 6, fontWeight: 450 }}>
            <input
              type="checkbox"
              checked={!!s.otp}
              onChange={(e) => set({ otp: e.target.checked })}
            />
            Ask for an OTP first (sent on WhatsApp through Interakt)
          </label>
          {!!s.otp && (
            <select
              value={Number(s.otp_retries ?? 2)}
              onChange={(e) => set({ otp_retries: Number(e.target.value) })}
            >
              {[0, 1, 2, 3].map((n) => (
                <option key={n} value={n}>
                  {n === 0
                    ? "Wrong code: go to code failed"
                    : `Wrong code: ask again up to ${n} time${n > 1 ? "s" : ""}`}
                </option>
              ))}
            </select>
          )}
        </Row>
      )}
      {block.type === "note" && (
        <>
          {text("text", "Note (for staff; patients never see it)", 5, 1000)}
          <Row label="Colour">
            <select
              value={String(s.color ?? "yellow")}
              onChange={(e) => set({ color: e.target.value })}
            >
              {["yellow", "blue", "green", "pink"].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </Row>
        </>
      )}
      {block.type === "lead_tag" &&
        text("campaign", "Campaign saved on the lead (CRM → Leads)", 1, 60)}
      {block.type === "known_patient" && (
        <span className="sub2" style={{ fontSize: "var(--fs-tiny)" }}>
          Known: a lead with the phone given in this chat already exists (one
          lead per phone). Put it after the phone question.
        </span>
      )}
      {block.type === "clinic_open" && (
        <Row label="Hours to check (Clinic info → Contact & hours)">
          <select
            value={String(s.hours ?? "in_clinic")}
            onChange={(e) => set({ hours: e.target.value })}
          >
            <option value="in_clinic">Clinic hours</option>
            <option value="online">Online consult hours</option>
          </select>
        </Row>
      )}
      {block.type === "condition" && (
        <Conditions
          branches={(s.branches as Branch[]) ?? []}
          fields={fields}
          onChange={(branches) => set({ branches })}
        />
      )}
      {block.type === "goto" && (
        <Row label="Go to block">
          <select
            value={String(s.target ?? "")}
            onChange={(e) => set({ target: e.target.value })}
          >
            <option value="">Choose…</option>
            {blocks
              .filter((b) => b.id !== block.id && b.type !== "goto")
              .map((b) => (
                <option key={b.id} value={b.id}>
                  {b.title || b.id}
                </option>
              ))}
          </select>
        </Row>
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
          <label
            style={{ display: "flex", gap: 6, fontSize: "var(--fs-small)" }}
          >
            <input
              type="checkbox"
              checked={s.required !== false}
              onChange={(e) => set({ required: e.target.checked })}
            />
            answer required (no skip)
          </label>
        </>
      )}
      <span className="sub2" style={{ fontSize: "var(--fs-tiny)" }}>
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
          <span className="sub2" style={{ fontWeight: 450 }}>
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
      {(block.type === "treatment_list" ||
        block.type === "treatment_card" ||
        (block.type === "carousel" && s.source !== "custom")) && (
        <label style={{ display: "flex", gap: 6, fontSize: "var(--fs-small)" }}>
          <input
            type="checkbox"
            checked={s.yes_books !== false}
            onChange={(e) => set({ yes_books: e.target.checked })}
          />
          A typed &quot;yes&quot; after the treatment&apos;s details starts the
          booking (asks name, phone…), the same as tapping Book
        </label>
      )}
      {block.type === "doctor_card" && (
        <>
          {text("doctor", "Doctor's name", 1, 80)}
          {text("title", "Title (e.g. Founder and Director)", 1, 120)}
          {text("qualifications", "Qualifications", 2, 300)}
          <Row label="Photo (optional): choose a picture, or paste a link">
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              {String(s.photo ?? "") && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={String(s.photo)}
                  alt=""
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: "50%",
                    objectFit: "cover",
                    border: "1px solid var(--line)",
                  }}
                />
              )}
              <label className="pill" style={{ cursor: "pointer" }}>
                {String(s.photo ?? "") ? "Change photo" : "Choose photo"}
                <input
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={async (e) => {
                    const file = e.target.files?.[0];
                    e.target.value = ""; // the same file can be chosen again
                    if (!file) return;
                    try {
                      // A square JPEG of a few KB, kept with the card.
                      const photo = await fitImage(file, {
                        width: 240,
                        height: 240,
                        square: true,
                        type: "image/jpeg",
                      });
                      setPhotoError("");
                      set({ photo });
                    } catch (err) {
                      setPhotoError(
                        err instanceof ImageError
                          ? err.message
                          : "Could not prepare the photo.",
                      );
                    }
                  }}
                />
              </label>
              {String(s.photo ?? "") && (
                <button
                  type="button"
                  className="pill"
                  onClick={() =>
                    window.confirm("Remove this photo?") && set({ photo: "" })
                  }
                >
                  Remove
                </button>
              )}
            </div>
            <input
              placeholder="or a link: https://…"
              maxLength={600}
              value={
                String(s.photo ?? "").startsWith("data:")
                  ? ""
                  : String(s.photo ?? "")
              }
              onChange={(e) => set({ photo: e.target.value })}
            />
            {photoError && (
              <span style={{ color: "var(--err)" }}>{photoError}</span>
            )}
          </Row>
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
          {text(
            "intro",
            "Message before the questions (optional), e.g. Sure! Our team will call you back. Please share a few details.",
            2,
            500,
          )}
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
            <span style={{ fontWeight: 450 }}>
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
                fontWeight: 450,
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
        [
          "answer",
          "emergency",
          "doctor_card",
          "location",
          "reviews",
          "faq",
          "media",
          "carousel",
        ].includes(block.type)) && (
        <Buttons
          list={buttonsOf(block)}
          onChange={onButtons}
          prefix={block.type === "opening" ? "m" : "b"}
        />
      )}
      <Phrases
        block={block}
        phrases={phrases}
        onChange={onPhrases}
        onApprove={onApprove}
        dirty={dirty}
      />
    </div>
  );
}

/** Typed phrases for this block's buttons (or its Typed trigger). New ones are pending; the chat uses a
 * phrase only after a manager approves it here (saved first), never by itself. */
function Phrases({
  block,
  phrases,
  onChange,
  onApprove,
  dirty,
}: {
  block: FlowNode;
  phrases: Phrase[];
  onChange: (p: Phrase[]) => void;
  onApprove: (ids: string[]) => void;
  dirty: boolean;
}) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const targets: [string, string][] =
    block.type === "typed"
      ? [[block.id, "This trigger"]]
      : buttonsOf(block)
          .filter((b) => b.visible !== false)
          .map((b) => [`${block.id}:${b.id}`, b.label]);
  if (!targets.length) return null;
  const pending = phrases.filter(
    (p) => p.status === "pending" && targets.some(([t]) => t === p.target),
  );
  return (
    <Row label="Typed phrases (used only once approved)">
      {targets.map(([t, label]) => (
        <div
          key={t}
          style={{ display: "flex", flexDirection: "column", gap: 3 }}
        >
          <span style={{ fontWeight: 600, fontSize: "var(--fs-small)" }}>
            {label}
          </span>
          {phrases
            .filter((p) => p.target === t)
            .map((p) => (
              <div
                key={p.id}
                className="wf-btn"
                style={{ fontSize: "var(--fs-small)" }}
              >
                <span
                  className={`badge ${p.status === "approved" ? "b-vi" : "b-fu"}`}
                >
                  {p.status === "approved" ? "Approved" : "Pending"}
                </span>
                <span style={{ flex: 1, fontWeight: 450 }}>{p.text}</span>
                <button
                  aria-label="Remove"
                  onClick={() => onChange(phrases.filter((x) => x.id !== p.id))}
                >
                  ✕
                </button>
              </div>
            ))}
          <div className="wf-btn">
            <input
              maxLength={100}
              placeholder="e.g. I want to book"
              value={drafts[t] ?? ""}
              onChange={(e) => setDrafts({ ...drafts, [t]: e.target.value })}
            />
            <button
              className="pill"
              disabled={(drafts[t] ?? "").trim().length < 2}
              onClick={() => {
                onChange([
                  ...phrases,
                  {
                    id:
                      "p" +
                      Date.now().toString(36) +
                      Math.random().toString(36).slice(2, 6),
                    target: t,
                    text: (drafts[t] ?? "").trim(),
                    status: "pending",
                  },
                ]);
                setDrafts({ ...drafts, [t]: "" });
              }}
            >
              Add
            </button>
          </div>
        </div>
      ))}
      {!!pending.length && (
        <button
          className="pill"
          style={{ alignSelf: "flex-start" }}
          disabled={dirty}
          title={dirty ? "Save changes first" : ""}
          onClick={() => onApprove(pending.map((p) => p.id))}
        >
          Approve {pending.length} pending
        </button>
      )}
    </Row>
  );
}

type CardT = {
  title: string;
  text: string;
  image: string;
  buttons: FlowButton[];
};

/** A carousel's own cards (2 to 10); each card's one button does its own job, so it needs no line. */
function Cards({
  cards,
  onChange,
}: {
  cards: CardT[];
  onChange: (c: CardT[]) => void;
}) {
  const put = (i: number, patch: Partial<CardT>) =>
    onChange(cards.map((c, k) => (k === i ? { ...c, ...patch } : c)));
  const actions = BUTTON_ACTIONS.filter(([a]) => a);
  return (
    <Row label="Cards (2 to 10; each button does its own job)">
      {cards.map((c, i) => {
        const btn = c.buttons[0] ?? {
          id: "b1",
          label: "Book",
          action: "book",
          value: "",
        };
        const putBtn = (patch: Partial<FlowButton>) =>
          put(i, { buttons: [{ ...btn, ...patch }] });
        return (
          <div
            key={i}
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 4,
              border: "1px solid var(--line, #e5e7eb)",
              borderRadius: 6,
              padding: 6,
            }}
          >
            <div style={{ display: "flex", gap: 4 }}>
              <input
                maxLength={60}
                placeholder="Title"
                value={c.title}
                onChange={(e) => put(i, { title: e.target.value })}
              />
              <button
                aria-label="Remove card"
                onClick={() => onChange(cards.filter((_, k) => k !== i))}
              >
                ✕
              </button>
            </div>
            <input
              maxLength={200}
              placeholder="Text (optional)"
              value={c.text}
              onChange={(e) => put(i, { text: e.target.value })}
            />
            <input
              maxLength={300}
              placeholder="Picture https://… (optional)"
              value={c.image}
              onChange={(e) => put(i, { image: e.target.value })}
            />
            <div style={{ display: "flex", gap: 4 }}>
              <input
                maxLength={40}
                placeholder="Button text"
                value={btn.label}
                onChange={(e) => putBtn({ label: e.target.value })}
              />
              <select
                value={btn.action}
                onChange={(e) => putBtn({ action: e.target.value })}
              >
                {actions.map(([a, label]) => (
                  <option key={a} value={a}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <input
              maxLength={600}
              placeholder={actions.find(([a]) => a === btn.action)?.[2] ?? ""}
              value={btn.value ?? ""}
              onChange={(e) => putBtn({ value: e.target.value })}
            />
          </div>
        );
      })}
      {cards.length < 10 && (
        <button
          className="pill"
          style={{ alignSelf: "flex-start" }}
          onClick={() =>
            onChange([
              ...cards,
              {
                title: "",
                text: "",
                image: "",
                buttons: [
                  { id: "b1", label: "Book", action: "book", value: "" },
                ],
              },
            ])
          }
        >
          + Add a card
        </button>
      )}
    </Row>
  );
}

type Test = { subject: string; field: string; op: string; value: string };
type Branch = { id: string; label: string; match: string; tests: Test[] };
// What each subject can be tested with (as the backend's Test model), and a hint for its value.
const SUBJECTS: Record<string, { label: string; ops: string[]; hint: string }> =
  {
    field: {
      label: "Field",
      ops: ["is", "is_not", "contains", "empty", "not_empty"],
      hint: "a value",
    },
    weekday: { label: "Day", ops: ["is", "is_not"], hint: "sat,sun" },
    time: { label: "Time (India)", ops: ["before", "after"], hint: "13:30" },
    device: { label: "Device", ops: ["is"], hint: "mobile or desktop" },
    returning: { label: "Returning patient", ops: ["is"], hint: "yes or no" },
  };
const OPS: Record<string, string> = {
  is: "is",
  is_not: "is not",
  contains: "contains",
  empty: "is empty",
  not_empty: "is filled",
  before: "before",
  after: "after",
};

/** If / else branches: tried in order, the first that matches leads on along its line; none → else. */
function Conditions({
  branches,
  fields,
  onChange,
}: {
  branches: Branch[];
  fields: string[];
  onChange: (b: Branch[]) => void;
}) {
  const put = (i: number, patch: Partial<Branch>) =>
    onChange(branches.map((b, k) => (k === i ? { ...b, ...patch } : b)));
  const blank: Test = { subject: "field", field: "", op: "is", value: "" };
  return (
    <Row label="Branches (tried in order; none matches → else)">
      {branches.map((b, i) => (
        <div
          key={b.id}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 4,
            border: "1px solid var(--line, #e5e7eb)",
            borderRadius: 6,
            padding: 6,
          }}
        >
          <div style={{ display: "flex", gap: 4 }}>
            <input
              maxLength={40}
              placeholder="Branch name (its exit)"
              value={b.label}
              onChange={(e) => put(i, { label: e.target.value })}
            />
            <select
              value={b.match}
              onChange={(e) => put(i, { match: e.target.value })}
            >
              <option value="all">all match</option>
              <option value="any">any matches</option>
            </select>
            <button
              aria-label="Remove branch"
              onClick={() => onChange(branches.filter((_, k) => k !== i))}
            >
              ✕
            </button>
          </div>
          {b.tests.map((t, j) => {
            const putTest = (patch: Partial<Test>) =>
              put(i, {
                tests: b.tests.map((x, k) =>
                  k === j ? { ...x, ...patch } : x,
                ),
              });
            const sub = SUBJECTS[t.subject] ?? SUBJECTS.field;
            return (
              <div key={j} style={{ display: "flex", gap: 4 }}>
                <select
                  value={t.subject}
                  onChange={(e) =>
                    putTest({
                      subject: e.target.value,
                      op: SUBJECTS[e.target.value].ops[0],
                      value: "",
                    })
                  }
                >
                  {Object.entries(SUBJECTS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v.label}
                    </option>
                  ))}
                </select>
                {t.subject === "field" && (
                  <select
                    value={t.field}
                    onChange={(e) => putTest({ field: e.target.value })}
                  >
                    <option value="">Choose…</option>
                    {fields.map((f) => (
                      <option key={f}>{f}</option>
                    ))}
                  </select>
                )}
                <select
                  value={t.op}
                  onChange={(e) => putTest({ op: e.target.value })}
                >
                  {sub.ops.map((o) => (
                    <option key={o} value={o}>
                      {OPS[o]}
                    </option>
                  ))}
                </select>
                {t.op !== "empty" && t.op !== "not_empty" && (
                  <input
                    maxLength={100}
                    placeholder={sub.hint}
                    value={t.value}
                    onChange={(e) => putTest({ value: e.target.value })}
                  />
                )}
                <button
                  aria-label="Remove test"
                  disabled={b.tests.length < 2}
                  onClick={() =>
                    put(i, { tests: b.tests.filter((_, k) => k !== j) })
                  }
                >
                  ✕
                </button>
              </div>
            );
          })}
          {b.tests.length < 5 && (
            <button
              className="pill"
              style={{ alignSelf: "flex-start" }}
              onClick={() => put(i, { tests: [...b.tests, blank] })}
            >
              + Add a test
            </button>
          )}
        </div>
      ))}
      {branches.length < 8 && (
        <button
          className="pill"
          style={{ alignSelf: "flex-start" }}
          onClick={() => {
            let n = 1;
            while (branches.some((b) => b.id === `c${n}`)) n++;
            onChange([
              ...branches,
              {
                id: `c${n}`,
                label: `Branch ${n}`,
                match: "all",
                tests: [blank],
              },
            ]);
          }}
        >
          + Add a branch
        </button>
      )}
    </Row>
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
