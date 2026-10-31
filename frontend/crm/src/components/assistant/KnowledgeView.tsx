"use client";

import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError } from "@/lib/api";

// Dashboard → Knowledge base: the clinic's facts and Q&A. One fact, many answers: an answer links a fact as
// {key} and shows its approved value. Staff save drafts; a clinic manager or BB Admin approves; only approved
// entries answer patients, and an answer whose linked fact is not approved is never given.

type Status = "draft" | "approved" | "retired";
type Fact = {
  id: string;
  key: string;
  category: string;
  value: string;
  variants: string;
  status: Status;
  used_by: number;
  updated_at: string;
};
type Qa = {
  id: string;
  question: string;
  variants: string;
  answer: string;
  category: string;
  treatment: string | null;
  status: Status;
  links: string[];
  missing: string[];
  updated_at: string;
};
type Knowledge = { facts: Fact[]; qa: Qa[]; can_approve: boolean };

const CATEGORIES: [string, string][] = [
  ["clinic_info", "Clinic info"],
  ["treatment", "Treatment"],
  ["cost", "Cost"],
  ["doctor", "Doctor"],
  ["policy", "Policy"],
  ["other", "Other"],
];
const CAT = Object.fromEntries(CATEGORIES);
const BADGE: Record<Status, [string, string]> = {
  draft: ["Draft", "b-fu"],
  approved: ["Approved", "b-vi"],
  retired: ["Retired", "b-in"],
};
const LINK = /\{([a-z][a-z0-9_]{1,49})\}/g;

/** The answer as the patient would see it, with approved facts filled in; missing ones shown as [key?]. */
function preview(answer: string, facts: Fact[]): string {
  const values = Object.fromEntries(
    facts.filter((f) => f.status === "approved").map((f) => [f.key, f.value]),
  );
  return answer.replace(LINK, (_, k: string) => values[k] ?? `[${k}?]`);
}

export default function KnowledgeView() {
  const { me, clinic, toast } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const url = `/v1/crm/console/${clinicId}/kb`;
  const [data, setData] = useState<{ clinic: string; k: Knowledge }>();
  const [tab, setTab] = useState<"facts" | "qa">("facts");
  const [show, setShow] = useState<Status | "all">("all");
  const [editFact, setEditFact] = useState<Partial<Fact> | null>(null);
  const [editQa, setEditQa] = useState<Partial<Qa> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Knowledge>(`/v1/crm/console/${clinicId}/kb`).then(
      (k) => live && setData({ clinic: clinicId, k }),
      (e) =>
        live &&
        setError(
          e instanceof ApiError
            ? e.message
            : "Could not load the knowledge base.",
        ),
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
    if (!clinicId) return false;
    setBusy(true);
    setError("");
    try {
      const k = await api<Knowledge>(`${url}${path}`, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      });
      setData({ clinic: clinicId, k });
      toast(done);
      return true;
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
      return false;
    } finally {
      setBusy(false);
    }
  }

  const k = data?.clinic === clinicId ? data?.k : undefined;
  const header = (
    <div className="ph">
      <div>
        <h1>Knowledge base</h1>
        <p>
          {clinic} · What the chatbot answers when patients type a question.
          Only approved entries are used; nothing goes live by itself.
        </p>
      </div>
    </div>
  );
  if (!k)
    return (
      <>
        {header}
        {error ? (
          <p className="warnbox">{error}</p>
        ) : (
          <p className="sub2">Loading…</p>
        )}
      </>
    );

  const count = (xs: { status: Status }[], s: Status) =>
    xs.filter((x) => x.status === s).length;
  const onHold = k.qa.filter(
    (q) => q.status === "approved" && q.missing.length,
  ).length;
  const row = (
    status: Status,
    actions: { id: string; kind: "facts" | "qa" },
  ) => (
    <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
      {status === "draft" && k.can_approve && (
        <button
          className="btn"
          disabled={busy}
          onClick={() =>
            void call(
              `/${actions.kind}/${actions.id}/approve`,
              "POST",
              undefined,
              "Approved: the bot uses it now",
            )
          }
        >
          Approve
        </button>
      )}
      {status !== "retired" ? (
        <button
          className="btn g"
          disabled={busy}
          onClick={() =>
            void call(
              `/${actions.kind}/${actions.id}/retire`,
              "POST",
              undefined,
              "Retired: the bot stops using it",
            )
          }
        >
          Retire
        </button>
      ) : (
        <button
          className="btn g"
          disabled={busy}
          onClick={() =>
            void call(
              `/${actions.kind}/${actions.id}/draft`,
              "POST",
              undefined,
              "Back to draft",
            )
          }
        >
          Restore
        </button>
      )}
    </div>
  );

  return (
    <>
      {header}
      <div
        className="row"
        style={{ gap: 16, marginBottom: 12, flexWrap: "wrap" }}
      >
        <span className="sub2">
          Facts: <b>{count(k.facts, "approved")}</b> approved,{" "}
          <b>{count(k.facts, "draft")}</b> drafts
        </span>
        <span className="sub2">
          Q&amp;A: <b>{count(k.qa, "approved")}</b> approved,{" "}
          <b>{count(k.qa, "draft")}</b> drafts
        </span>
        {onHold > 0 && (
          <span className="sub2" style={{ color: "var(--warn)" }}>
            {onHold} approved answer{onHold === 1 ? "" : "s"} on hold (a linked
            fact is not approved)
          </span>
        )}
        {!k.can_approve && (
          <span className="sub2">
            Your entries are drafts until a clinic manager approves them.
          </span>
        )}
      </div>
      <div
        className="row"
        style={{ gap: 8, marginBottom: 12, flexWrap: "wrap" }}
      >
        <div className="seg">
          <button
            className={tab === "facts" ? "on" : ""}
            onClick={() => setTab("facts")}
          >
            Facts ({k.facts.length})
          </button>
          <button
            className={tab === "qa" ? "on" : ""}
            onClick={() => setTab("qa")}
          >
            Questions &amp; answers ({k.qa.length})
          </button>
        </div>
        <select
          className="sel"
          aria-label="Show"
          value={show}
          onChange={(e) => setShow(e.target.value as Status | "all")}
        >
          <option value="all">All</option>
          <option value="draft">Drafts</option>
          <option value="approved">Approved</option>
          <option value="retired">Retired</option>
        </select>
        <button
          className="btn"
          onClick={() => {
            setError("");
            if (tab === "facts") {
              setEditQa(null);
              setEditFact({
                key: "",
                category: "clinic_info",
                value: "",
                variants: "",
              });
            } else {
              setEditFact(null);
              setEditQa({
                question: "",
                variants: "",
                answer: "",
                category: "other",
                treatment: "",
              });
            }
          }}
        >
          {tab === "facts" ? "+ Add fact" : "+ Add question"}
        </button>
      </div>
      {error && !editFact && !editQa && <p className="warnbox">{error}</p>}

      {editFact && (
        <FactForm
          fact={editFact}
          busy={busy}
          error={error}
          onChange={setEditFact}
          onCancel={() => {
            setEditFact(null);
            setError("");
          }}
          onSave={async () => {
            const body = {
              key: editFact.key,
              category: editFact.category,
              value: editFact.value,
              variants: editFact.variants,
            };
            const ok = editFact.id
              ? await call(
                  `/facts/${editFact.id}`,
                  "PUT",
                  body,
                  "Fact saved as a draft",
                )
              : await call("/facts", "POST", body, "Fact added as a draft");
            if (ok) setEditFact(null);
          }}
        />
      )}
      {editQa && (
        <QaForm
          qa={editQa}
          facts={k.facts}
          busy={busy}
          error={error}
          onChange={setEditQa}
          onCancel={() => {
            setEditQa(null);
            setError("");
          }}
          onSave={async () => {
            const body = {
              question: editQa.question,
              variants: editQa.variants,
              answer: editQa.answer,
              category: editQa.category,
              treatment: editQa.treatment || null,
            };
            const ok = editQa.id
              ? await call(
                  `/qa/${editQa.id}`,
                  "PUT",
                  body,
                  "Question saved as a draft",
                )
              : await call("/qa", "POST", body, "Question added as a draft");
            if (ok) setEditQa(null);
          }}
        />
      )}

      {tab === "facts" &&
        (k.facts.filter((f) => show === "all" || f.status === show).length ===
        0 ? (
          <div className="empty">
            <h2>No facts here yet</h2>
            Add the clinic&apos;s facts once (timings, address, fees…); answers
            can then link them.
          </div>
        ) : (
          k.facts
            .filter((f) => show === "all" || f.status === show)
            .map((f) => (
              <div
                key={f.id}
                className="card"
                style={{ padding: 12, marginBottom: 8 }}
              >
                <div
                  className="row"
                  style={{
                    gap: 8,
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                  }}
                >
                  <div style={{ minWidth: 0, flex: "1 1 300px" }}>
                    <span className={`badge ${BADGE[f.status][1]}`}>
                      {BADGE[f.status][0]}
                    </span>{" "}
                    <b>{`{${f.key}}`}</b>{" "}
                    <span className="sub2">· {CAT[f.category]}</span>
                    <div style={{ marginTop: 4, whiteSpace: "pre-wrap" }}>
                      {f.value}
                    </div>
                    <div className="sub2">
                      Used by {f.used_by} answer{f.used_by === 1 ? "" : "s"}
                      {f.variants
                        ? ` · Also asked as: ${f.variants.split("\n").join(", ")}`
                        : ""}
                    </div>
                  </div>
                  <div className="row" style={{ gap: 6 }}>
                    <button
                      className="btn g"
                      onClick={() => {
                        setError("");
                        setEditQa(null);
                        setEditFact({ ...f });
                      }}
                    >
                      Edit
                    </button>
                    {row(f.status, { id: f.id, kind: "facts" })}
                  </div>
                </div>
              </div>
            ))
        ))}

      {tab === "qa" &&
        (k.qa.filter((q) => show === "all" || q.status === show).length ===
        0 ? (
          <div className="empty">
            <h2>No questions here yet</h2>
            Add the questions patients ask and the clinic&apos;s answer. Link
            facts with {"{key}"} so one change updates every answer.
          </div>
        ) : (
          k.qa
            .filter((q) => show === "all" || q.status === show)
            .map((q) => (
              <div
                key={q.id}
                className="card"
                style={{ padding: 12, marginBottom: 8 }}
              >
                <div
                  className="row"
                  style={{
                    gap: 8,
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                  }}
                >
                  <div style={{ minWidth: 0, flex: "1 1 300px" }}>
                    <span className={`badge ${BADGE[q.status][1]}`}>
                      {BADGE[q.status][0]}
                    </span>{" "}
                    <b>{q.question}</b>{" "}
                    <span className="sub2">· {CAT[q.category]}</span>
                    <div style={{ marginTop: 4, whiteSpace: "pre-wrap" }}>
                      {preview(q.answer, k.facts)}
                    </div>
                    {q.missing.length > 0 && q.status !== "retired" && (
                      <div className="sub2" style={{ color: "var(--warn)" }}>
                        Not given to patients until these facts are approved:{" "}
                        {q.missing.map((m) => `{${m}}`).join(", ")}
                      </div>
                    )}
                    {q.variants && (
                      <div className="sub2">
                        Also asked as: {q.variants.split("\n").join(", ")}
                      </div>
                    )}
                  </div>
                  <div className="row" style={{ gap: 6 }}>
                    <button
                      className="btn g"
                      onClick={() => {
                        setError("");
                        setEditFact(null);
                        setEditQa({ ...q });
                      }}
                    >
                      Edit
                    </button>
                    {row(q.status, { id: q.id, kind: "qa" })}
                  </div>
                </div>
              </div>
            ))
        ))}
    </>
  );
}

function FactForm({
  fact: f,
  busy,
  error,
  onChange,
  onCancel,
  onSave,
}: {
  fact: Partial<Fact>;
  busy: boolean;
  error: string;
  onChange: (f: Partial<Fact>) => void;
  onCancel: () => void;
  onSave: () => void;
}) {
  const set = (p: Partial<Fact>) => onChange({ ...f, ...p });
  const keyOk = /^[a-z][a-z0-9_]{1,49}$/.test(f.key ?? "");
  return (
    <div
      className="card"
      style={{ padding: 16, marginBottom: 12, maxWidth: 760 }}
    >
      <b>{f.id ? "Edit fact" : "Add a fact"}</b>
      <div style={{ display: "grid", gap: 10, marginTop: 10 }}>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="sub2">
            Key: small letters, numbers and _, e.g. consult_fee (used as{" "}
            {"{consult_fee}"} in answers)
          </span>
          <input
            className="f"
            maxLength={50}
            value={f.key ?? ""}
            onChange={(e) =>
              set({
                key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"),
              })
            }
          />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="sub2">Category</span>
          <select
            className="sel"
            value={f.category}
            onChange={(e) => set({ category: e.target.value })}
          >
            {CATEGORIES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="sub2">
            Value: what the chatbot says, e.g. Rs 700
          </span>
          <textarea
            className="f"
            rows={3}
            maxLength={2000}
            value={f.value ?? ""}
            onChange={(e) => set({ value: e.target.value })}
          />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="sub2">
            Other ways patients ask for it (one per line, optional)
          </span>
          <textarea
            className="f"
            rows={3}
            maxLength={4000}
            value={f.variants ?? ""}
            onChange={(e) => set({ variants: e.target.value })}
          />
        </label>
      </div>
      {!!f.used_by && (
        <p className="warnbox" style={{ marginTop: 10 }}>
          Used by {f.used_by} answer{f.used_by === 1 ? "" : "s"}. Saving puts
          this fact back to draft: those answers are not given until it is
          approved again.
        </p>
      )}
      {error && (
        <p role="alert" style={{ color: "var(--err)", margin: "10px 0 0" }}>
          {error}
        </p>
      )}
      <div className="row" style={{ gap: 8, marginTop: 14 }}>
        <button
          className="btn"
          disabled={busy || !keyOk || !(f.value ?? "").trim()}
          onClick={onSave}
        >
          {busy ? "Saving…" : "Save as draft"}
        </button>
        <button className="btn g" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function QaForm({
  qa: q,
  facts,
  busy,
  error,
  onChange,
  onCancel,
  onSave,
}: {
  qa: Partial<Qa>;
  facts: Fact[];
  busy: boolean;
  error: string;
  onChange: (q: Partial<Qa>) => void;
  onCancel: () => void;
  onSave: () => void;
}) {
  const set = (p: Partial<Qa>) => onChange({ ...q, ...p });
  const answer = q.answer ?? "";
  const linked = [...new Set([...answer.matchAll(LINK)].map((m) => m[1]))];
  const approved = new Set(
    facts.filter((f) => f.status === "approved").map((f) => f.key),
  );
  const unknown = linked.filter((k) => !facts.some((f) => f.key === k));
  const waiting = linked.filter(
    (k) => !approved.has(k) && !unknown.includes(k),
  );
  return (
    <div
      className="card"
      style={{ padding: 16, marginBottom: 12, maxWidth: 760 }}
    >
      <b>{q.id ? "Edit question" : "Add a question"}</b>
      <div style={{ display: "grid", gap: 10, marginTop: 10 }}>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="sub2">Question, as patients ask it</span>
          <input
            className="f"
            maxLength={300}
            value={q.question ?? ""}
            onChange={(e) => set({ question: e.target.value })}
          />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="sub2">
            Other wordings (one per line, optional): more ways patients ask the
            same
          </span>
          <textarea
            className="f"
            rows={3}
            maxLength={4000}
            value={q.variants ?? ""}
            onChange={(e) => set({ variants: e.target.value })}
          />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="sub2">
            Answer (link a fact as {"{key}"} so it always shows the current
            value)
          </span>
          <textarea
            className="f"
            rows={4}
            maxLength={2000}
            value={answer}
            onChange={(e) => set({ answer: e.target.value })}
          />
        </label>
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          <select
            className="sel"
            aria-label="Insert a fact"
            value=""
            onChange={(e) =>
              e.target.value && set({ answer: `${answer}{${e.target.value}}` })
            }
          >
            <option value="">Insert a fact…</option>
            {facts
              .filter((f) => f.status !== "retired")
              .map((f) => (
                <option key={f.id} value={f.key}>
                  {`{${f.key}}`} · {f.value.slice(0, 40)}
                  {f.status === "draft" ? " (draft)" : ""}
                </option>
              ))}
          </select>
          <select
            className="sel"
            aria-label="Category"
            value={q.category}
            onChange={(e) => set({ category: e.target.value })}
          >
            {CATEGORIES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
          <input
            className="f"
            style={{ flex: "1 1 200px" }}
            placeholder="Treatment it is about (optional)"
            maxLength={100}
            value={q.treatment ?? ""}
            onChange={(e) => set({ treatment: e.target.value })}
          />
        </div>
      </div>
      {answer.trim() && (
        <div className="box" style={{ marginTop: 10 }}>
          <span className="sub2">The patient sees:</span>
          <p
            style={{
              whiteSpace: "pre-wrap",
              color: "var(--ink)",
              fontSize: 13.5,
            }}
          >
            {preview(answer, facts)}
          </p>
        </div>
      )}
      {unknown.length > 0 && (
        <p className="warnbox" style={{ marginTop: 10 }}>
          No fact with this key: {unknown.map((k) => `{${k}}`).join(", ")}. Add
          it in Facts, or fix the key.
        </p>
      )}
      {waiting.length > 0 && (
        <p className="warnbox" style={{ marginTop: 10 }}>
          Not approved yet: {waiting.map((k) => `{${k}}`).join(", ")}. This
          answer is not given until they are.
        </p>
      )}
      {error && (
        <p role="alert" style={{ color: "var(--err)", margin: "10px 0 0" }}>
          {error}
        </p>
      )}
      <div className="row" style={{ gap: 8, marginTop: 14 }}>
        <button
          className="btn"
          disabled={
            busy || (q.question ?? "").trim().length < 3 || !answer.trim()
          }
          onClick={onSave}
        >
          {busy ? "Saving…" : "Save as draft"}
        </button>
        <button className="btn g" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
