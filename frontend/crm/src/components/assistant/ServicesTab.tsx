"use client";

import { useState } from "react";

// Clinic info → Services: every treatment the chat can show (card, price, Book and Read more), the booking
// list ("Which treatment?" when booking) and the words the chat answers "not offered" to.

export type Service = {
  name: string;
  category: string;
  description: string;
  page: string;
  photo: string;
  duration: string;
  price: number | null;
  show_price: boolean;
  book_as: string;
  show: boolean;
};
export type Services = {
  items: Service[];
  booking_options: string[];
  not_offered: string[];
};

const BLANK: Service = {
  name: "New treatment",
  category: "",
  description: "",
  page: "",
  photo: "",
  duration: "",
  price: null,
  show_price: false,
  book_as: "",
  show: true,
};
const rupees = (n: number) => "₹" + n.toLocaleString("en-IN");

export default function ServicesTab({
  value,
  onChange,
  selected,
  onSelect,
}: {
  value: Services;
  onChange: (v: Services) => void;
  selected: number | null;
  onSelect: (i: number | null) => void;
}) {
  const [find, setFind] = useState("");
  const [group, setGroup] = useState("");
  const groups = [
    ...new Set(value.items.map((s) => s.category).filter(Boolean)),
  ];
  const setItem = (i: number, patch: Partial<Service>) =>
    onChange({
      ...value,
      items: value.items.map((s, k) => (k === i ? { ...s, ...patch } : s)),
    });
  const rows = value.items
    .map((s, i) => [s, i] as const)
    .filter(
      ([s]) =>
        (!group || s.category === group) &&
        s.name.toLowerCase().includes(find.trim().toLowerCase()),
    );

  return (
    <div className="ci">
      <section>
        <h4>
          Treatments ({value.items.filter((s) => s.show).length} shown of{" "}
          {value.items.length})
        </h4>
        <div className="row" style={{ marginBottom: 8 }}>
          <input
            className="f"
            style={{ flex: "1 1 180px", minHeight: 32, padding: "5px 9px" }}
            placeholder="Find a treatment"
            value={find}
            onChange={(e) => setFind(e.target.value)}
          />
          <div className="ci-days">
            <button
              type="button"
              className={group ? "" : "on"}
              style={{ width: "auto", padding: "0 10px" }}
              onClick={() => setGroup("")}
            >
              All
            </button>
            {groups.map((g) => (
              <button
                key={g}
                type="button"
                className={group === g ? "on" : ""}
                style={{ width: "auto", padding: "0 10px" }}
                onClick={() => setGroup(g)}
              >
                {g}
              </button>
            ))}
          </div>
        </div>
        <div className="svc">
          {rows.map(([s, i]) => (
            <div key={i} className={`svc-row${selected === i ? " on" : ""}`}>
              <div
                className="svc-head"
                onClick={() => onSelect(selected === i ? null : i)}
              >
                <input
                  type="checkbox"
                  title="Show in the chat"
                  checked={s.show}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => setItem(i, { show: e.target.checked })}
                />
                <b style={{ opacity: s.show ? 1 : 0.5 }}>{s.name}</b>
                <span className="sub2">{s.category}</span>
                <span className="sub2" style={{ marginLeft: "auto" }}>
                  {s.show_price && s.price != null
                    ? `From ${rupees(s.price)}`
                    : "Price at consultation"}
                </span>
                {!s.book_as && (
                  <span className="badge b-fu">No booking option</span>
                )}
                <span className="sub2">{selected === i ? "▾" : "▸"}</span>
              </div>
              {selected === i && (
                <div className="ci-grid" style={{ padding: "4px 2px 8px" }}>
                  <label>
                    <span>Treatment name</span>
                    <input
                      maxLength={80}
                      value={s.name}
                      onChange={(e) => setItem(i, { name: e.target.value })}
                    />
                  </label>
                  <label>
                    <span>Category</span>
                    <input
                      list="svc-groups"
                      maxLength={40}
                      value={s.category}
                      onChange={(e) => setItem(i, { category: e.target.value })}
                    />
                  </label>
                  <label className="wide">
                    <span>
                      Short description ({(s.description ?? "").length}/400;
                      Enter starts a new line in the chat)
                    </span>
                    <textarea
                      rows={4}
                      maxLength={400}
                      value={s.description}
                      onChange={(e) =>
                        setItem(i, { description: e.target.value })
                      }
                    />
                  </label>
                  <label className="wide">
                    <span>Page on the website (Read more)</span>
                    <input
                      maxLength={300}
                      placeholder="https://…"
                      value={s.page}
                      onChange={(e) => setItem(i, { page: e.target.value })}
                    />
                  </label>
                  <label>
                    <span>Photo (optional)</span>
                    <input
                      maxLength={300}
                      placeholder="https://…"
                      value={s.photo}
                      onChange={(e) => setItem(i, { photo: e.target.value })}
                    />
                  </label>
                  <label>
                    <span>Duration (optional)</span>
                    <input
                      maxLength={30}
                      placeholder="e.g. 6 to 8 hours"
                      value={s.duration}
                      onChange={(e) => setItem(i, { duration: e.target.value })}
                    />
                  </label>
                  <label>
                    <span>Starting price (₹, optional)</span>
                    <input
                      inputMode="numeric"
                      value={s.price ?? ""}
                      onChange={(e) => {
                        const n = e.target.value.replace(/\D/g, "");
                        setItem(i, { price: n ? Number(n) : null });
                      }}
                    />
                  </label>
                  <label>
                    <span>Book button chooses</span>
                    <select
                      value={s.book_as}
                      onChange={(e) => setItem(i, { book_as: e.target.value })}
                      style={{
                        font: "inherit",
                        fontSize: "var(--fs-sec)",
                        border: "1px solid var(--line)",
                        borderRadius: 8,
                        padding: "6px 8px",
                        minHeight: 32,
                      }}
                    >
                      <option value="">Ask the patient</option>
                      {value.booking_options.map((o) => (
                        <option key={o}>{o}</option>
                      ))}
                    </select>
                  </label>
                  <div
                    className="wide row"
                    style={{ justifyContent: "space-between" }}
                  >
                    <label
                      className="opt"
                      style={{
                        flexDirection: "row",
                        fontSize: "var(--fs-small)",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={s.show_price}
                        onChange={(e) =>
                          setItem(i, { show_price: e.target.checked })
                        }
                      />
                      Show &quot;From ₹&quot; on the card (off: the price is
                      shared at consultation)
                    </label>
                    <button
                      type="button"
                      className="pill"
                      style={{ color: "var(--err)" }}
                      onClick={() => {
                        if (
                          !window.confirm(
                            `Remove the treatment "${s.name || "this treatment"}"? It disappears from the chatbot's lists after you save and publish.`,
                          )
                        )
                          return;
                        onChange({
                          ...value,
                          items: value.items.filter((_, k) => k !== i),
                        });
                        onSelect(null);
                      }}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
        <datalist id="svc-groups">
          {groups.map((g) => (
            <option key={g} value={g} />
          ))}
        </datalist>
        <button
          type="button"
          className="pill"
          style={{ marginTop: 8 }}
          onClick={() => {
            onChange({
              ...value,
              items: [...value.items, { ...BLANK, category: group }],
            });
            onSelect(value.items.length);
          }}
        >
          + Add treatment
        </button>
      </section>

      <section>
        <h4>Booking list</h4>
        <span className="sub2">
          The choices when a patient books (&quot;Which treatment?&quot;).
        </span>
        <Words
          list={value.booking_options}
          max={20}
          onChange={(v) => onChange({ ...value, booking_options: v })}
          placeholder="Add a choice"
        />
      </section>

      <section>
        <h4>Not offered</h4>
        <span className="sub2">
          When a patient asks about these, the chat says the clinic does not
          offer them.
        </span>
        <Words
          list={value.not_offered}
          max={80}
          onChange={(v) => onChange({ ...value, not_offered: v })}
          placeholder="Add a word, e.g. botox"
        />
      </section>
    </div>
  );
}

/** Small removable chips with an add box. */
function Words({
  list,
  max,
  placeholder,
  onChange,
}: {
  list: string[];
  max: number;
  placeholder: string;
  onChange: (v: string[]) => void;
}) {
  const [text, setText] = useState("");
  const add = () => {
    const t = text.trim();
    if (t && !list.includes(t) && list.length < max) onChange([...list, t]);
    setText("");
  };
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 5,
        marginTop: 6,
        alignItems: "center",
      }}
    >
      {list.map((w) => (
        <span
          key={w}
          className="pill"
          style={{
            padding: "3px 4px 3px 10px",
            fontSize: "var(--fs-small)",
            display: "inline-flex",
            gap: 4,
            alignItems: "center",
          }}
        >
          {w}
          <button
            type="button"
            aria-label={`Remove ${w}`}
            onClick={() => onChange(list.filter((x) => x !== w))}
            style={{
              border: 0,
              background: "none",
              cursor: "pointer",
              color: "var(--mute)",
            }}
          >
            ✕
          </button>
        </span>
      ))}
      <input
        value={text}
        placeholder={placeholder}
        maxLength={80}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            add();
          }
        }}
        onBlur={add}
        style={{
          font: "inherit",
          fontSize: "var(--fs-small)",
          border: "1px dashed var(--line)",
          borderRadius: 999,
          padding: "4px 10px",
          minWidth: 150,
        }}
      />
    </div>
  );
}

/** The chat's card for one treatment, as patients see it. */
export function ServiceCard({ s, main }: { s: Service; main: string }) {
  return (
    <div
      className="chat-preview"
      style={{
        border: "1px solid #EFE3E6",
        borderRadius: 12,
        overflow: "hidden",
        background: "#fff",
        fontSize: 12,
      }}
    >
      {s.photo && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={s.photo}
          alt=""
          style={{
            width: "100%",
            height: 90,
            objectFit: "cover",
            display: "block",
          }}
        />
      )}
      <div
        style={{
          padding: 10,
          display: "flex",
          flexDirection: "column",
          gap: 5,
        }}
      >
        <b style={{ fontSize: 13 }}>{s.name}</b>
        {s.description && (
          <span style={{ color: "#4B5563", whiteSpace: "pre-line" }}>
            {s.description.trim()}
          </span>
        )}
        <span style={{ color: "#6B5F63", fontSize: 11.5 }}>
          {[
            s.duration,
            s.show_price && s.price != null
              ? `From ${rupees(s.price)}`
              : "Price shared at consultation",
          ]
            .filter(Boolean)
            .join(" · ")}
        </span>
        <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
          <span
            style={{
              background: main,
              color: "#fff",
              borderRadius: 999,
              padding: "5px 12px",
              fontWeight: 700,
            }}
          >
            Book
          </span>
          {s.page && (
            <span
              style={{
                border: `1.5px solid ${main}`,
                color: main,
                borderRadius: 999,
                padding: "5px 12px",
                fontWeight: 700,
              }}
            >
              Read more
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
