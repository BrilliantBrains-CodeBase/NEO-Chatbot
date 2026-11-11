"use client";

import { useState } from "react";

// Clinic info → Reviews: the Google rating and links, the patient quotes the chat may show (word for word,
// first name and last initial only), and the answer about well-known patients.

export type Quote = {
  name: string;
  topic: string;
  text: string;
  show: boolean;
};
export type Reviews = {
  rating: string;
  count: string;
  link: string;
  videos: string;
  quotes: Quote[];
  celebrities: string;
};

export default function ReviewsTab({
  value,
  onChange,
  selected,
  onSelect,
}: {
  value: Reviews;
  onChange: (v: Reviews) => void;
  selected: number | null;
  onSelect: (i: number | null) => void;
}) {
  const [topic, setTopic] = useState("");
  const topics = [...new Set(value.quotes.map((q) => q.topic).filter(Boolean))];
  const set = (patch: Partial<Reviews>) => onChange({ ...value, ...patch });
  const setQuote = (i: number, patch: Partial<Quote>) =>
    set({
      quotes: value.quotes.map((q, k) => (k === i ? { ...q, ...patch } : q)),
    });
  const rows = value.quotes
    .map((q, i) => [q, i] as const)
    .filter(([q]) => !topic || q.topic === topic);

  return (
    <div className="ci">
      <section>
        <h4>Google rating</h4>
        <div className="ci-grid">
          <label>
            <span>Rating (out of 5)</span>
            <input
              maxLength={3}
              placeholder="4.8"
              value={value.rating}
              onChange={(e) => set({ rating: e.target.value })}
            />
          </label>
          <label>
            <span>Number of reviews</span>
            <input
              maxLength={12}
              placeholder="1,040"
              value={value.count}
              onChange={(e) => set({ count: e.target.value })}
            />
          </label>
          <label className="wide">
            <span>Link to the reviews (Google Maps)</span>
            <input
              maxLength={600}
              placeholder="https://www.google.com/maps/place/…"
              value={value.link}
              onChange={(e) => set({ link: e.target.value })}
            />
          </label>
          <label className="wide">
            <span>Patient videos page (optional)</span>
            <input
              maxLength={300}
              placeholder="https://…"
              value={value.videos}
              onChange={(e) => set({ videos: e.target.value })}
            />
          </label>
        </div>
      </section>

      <section>
        <h4>
          Patient quotes ({value.quotes.filter((q) => q.show).length} shown of{" "}
          {value.quotes.length})
        </h4>
        <span className="sub2">
          Word for word from Google; first name and last initial only; no
          medical-result claims.
        </span>
        <div className="ci-days" style={{ margin: "8px 0" }}>
          <button
            type="button"
            className={topic ? "" : "on"}
            style={{ width: "auto", padding: "0 10px" }}
            onClick={() => setTopic("")}
          >
            All
          </button>
          {topics.map((t) => (
            <button
              key={t}
              type="button"
              className={topic === t ? "on" : ""}
              style={{ width: "auto", padding: "0 10px" }}
              onClick={() => setTopic(t)}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="svc">
          {rows.map(([q, i]) => (
            <div key={i} className={`svc-row${selected === i ? " on" : ""}`}>
              <div
                className="svc-head"
                onClick={() => onSelect(selected === i ? null : i)}
              >
                <input
                  type="checkbox"
                  title="Show in the chat"
                  checked={q.show}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => setQuote(i, { show: e.target.checked })}
                />
                <b style={{ opacity: q.show ? 1 : 0.5, whiteSpace: "nowrap" }}>
                  {q.name}
                </b>
                <span className="sub2">{q.topic}</span>
                <span
                  className="sub2"
                  style={{
                    flex: 1,
                    minWidth: 0,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {q.text}
                </span>
                <span className="sub2">{selected === i ? "▾" : "▸"}</span>
              </div>
              {selected === i && (
                <div className="ci-grid" style={{ padding: "4px 2px 8px" }}>
                  <label>
                    <span>Name (first name, last initial)</span>
                    <input
                      maxLength={40}
                      value={q.name}
                      onChange={(e) => setQuote(i, { name: e.target.value })}
                    />
                  </label>
                  <label>
                    <span>Topic</span>
                    <input
                      list="rv-topics"
                      maxLength={30}
                      value={q.topic}
                      onChange={(e) => setQuote(i, { topic: e.target.value })}
                    />
                  </label>
                  <label className="wide">
                    <span>Review text</span>
                    <textarea
                      rows={4}
                      maxLength={1500}
                      value={q.text}
                      onChange={(e) => setQuote(i, { text: e.target.value })}
                      style={{
                        font: "inherit",
                        fontSize: "var(--fs-sec)",
                        border: "1px solid var(--line)",
                        borderRadius: 8,
                        padding: "6px 9px",
                      }}
                    />
                  </label>
                  <div
                    className="wide row"
                    style={{ justifyContent: "flex-end" }}
                  >
                    <button
                      type="button"
                      className="pill"
                      style={{ color: "var(--err)" }}
                      onClick={() => {
                        if (!window.confirm("Remove this review?")) return;
                        set({ quotes: value.quotes.filter((_, k) => k !== i) });
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
        <datalist id="rv-topics">
          {topics.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
        {value.quotes.length < 30 && (
          <button
            type="button"
            className="pill"
            style={{ marginTop: 8 }}
            onClick={() => {
              set({
                quotes: [
                  ...value.quotes,
                  { name: "", topic, text: "", show: true },
                ],
              });
              onSelect(value.quotes.length);
            }}
          >
            + Add quote
          </button>
        )}
      </section>

      <section>
        <h4>Well-known patients</h4>
        <span className="sub2">
          The chat&apos;s answer when someone asks about celebrities or famous
          patients.
        </span>
        <textarea
          rows={3}
          maxLength={600}
          value={value.celebrities}
          onChange={(e) => set({ celebrities: e.target.value })}
          style={{
            width: "100%",
            marginTop: 6,
            font: "inherit",
            fontSize: "var(--fs-sec)",
            border: "1px solid var(--line)",
            borderRadius: 8,
            padding: "6px 9px",
          }}
        />
      </section>
    </div>
  );
}

/** The chat's reviews answer: rating, one quote, and the links. */
export function ReviewsPreview({
  r,
  quote,
  main,
}: {
  r: Reviews;
  quote: Quote | undefined;
  main: string;
}) {
  const chip = (label: string) => (
    <span
      style={{
        border: `1.5px solid ${main}`,
        color: main,
        borderRadius: 999,
        padding: "4px 10px",
        fontSize: 11,
        fontWeight: 700,
      }}
    >
      {label}
    </span>
  );
  return (
    <div
      className="chat-preview"
      style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 12 }}
    >
      <span
        style={{
          alignSelf: "flex-start",
          background: "#F1F3F7",
          borderRadius: 12,
          padding: "8px 10px",
        }}
      >
        <b style={{ fontSize: 14 }}>{r.rating || "–"}★</b> from {r.count || "–"}{" "}
        Google reviews
      </span>
      {quote && (
        <div
          style={{
            border: "1px solid #EFE3E6",
            borderRadius: 12,
            padding: 10,
            background: "#fff",
          }}
        >
          <span style={{ color: "#F2A33A" }}>★★★★★</span>
          <p style={{ margin: "4px 0", color: "#374151" }}>
            &ldquo;
            {quote.text.length > 220
              ? quote.text.slice(0, 220) + "…"
              : quote.text}
            &rdquo;
          </p>
          <b style={{ fontSize: 11.5 }}>{quote.name}</b>
        </div>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {r.link && chip("Read all reviews")}
        {r.videos && chip("Watch patient videos")}
      </div>
    </div>
  );
}
