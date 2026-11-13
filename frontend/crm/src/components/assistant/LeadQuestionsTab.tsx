"use client";

import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import LeadDrawer from "@/components/leads/LeadDrawer";
import { when } from "@/components/leads/labels";
import { api, ApiError } from "@/lib/api";

// Chatbot → Clinic info → Lead questions (backend: /v1/crm/console/{clinic}/lead-questions). Every question
// the chatbot had no approved answer for, newest first, with the patient when they left their number. Staff
// mark one answered after the call, or turn it into a Knowledge base draft (the bot never learns by itself).

type Show = "new" | "answered" | "all";
type Asked = {
  id: number;
  question: string;
  reason: "medical" | "no_match" | "llm_rejected";
  answered: boolean;
  created_at: string;
  lead_code: string | null;
  lead_name: string | null;
};
type Page = { items: Asked[]; total: number; new: number };

const SHOWS: [Show, string][] = [
  ["new", "New"],
  ["answered", "Answered"],
  ["all", "All"],
];

export default function LeadQuestionsTab({ clinicId }: { clinicId: string }) {
  const { toast } = useCrm();
  const [show, setShow] = useState<Show>("new");
  const [typed, setTyped] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [openCode, setOpenCode] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => {
      setQ(typed.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [typed]);

  const base = `/v1/crm/console/${clinicId}/lead-questions`;
  useEffect(() => {
    let live = true; // a newer filter or page wins over an older answer
    const params = new URLSearchParams({ show, q, page: String(page) });
    api<Page>(`${base}?${params}`).then(
      (got) => {
        if (!live) return;
        setData((old) =>
          page > 1 && old
            ? { ...got, items: [...old.items, ...got.items] }
            : got,
        );
        setError("");
      },
      (e) => {
        if (live)
          setError(
            e instanceof ApiError ? e.message : "Could not load the questions.",
          );
      },
    );
    return () => {
      live = false;
    };
  }, [base, show, q, page, version]);

  async function mark(a: Asked, answered: boolean) {
    setBusy(a.id);
    try {
      await api(`${base}/${a.id}`, {
        method: "PUT",
        body: JSON.stringify({ answered }),
      });
      toast(answered ? "Marked answered" : "Moved back to New");
      setPage(1);
      setVersion((v) => v + 1);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function toKnowledgeBase(a: Asked) {
    if (
      !window.confirm(
        "Add this question to the Knowledge base as a draft? You write the answer and approve it there; the chatbot uses it only after approval.",
      )
    )
      return;
    setBusy(a.id);
    try {
      await api(`${base}/${a.id}/kb`, { method: "POST", body: "{}" });
      toast("Draft added to the Knowledge base");
      setPage(1);
      setVersion((v) => v + 1);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Could not add it. Please try again.",
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="lq">
      <p className="sub2" style={{ marginTop: 0 }}>
        Questions patients asked that the chatbot had no approved answer for.
        When a patient left their number, their call back is in Inbox → Call
        back with all their questions. After 90 days the patient&apos;s name is
        removed from here.
      </p>
      <div
        className="row"
        style={{ gap: 10, flexWrap: "wrap", marginBottom: 12 }}
      >
        <div className="seg" style={{ marginLeft: 0 }}>
          {SHOWS.map(([k, label]) => (
            <button
              key={k}
              className={show === k ? "on" : ""}
              onClick={() => {
                setShow(k);
                setPage(1);
              }}
            >
              {label}
              {k === "new" && data ? ` (${data.new})` : ""}
            </button>
          ))}
        </div>
        <input
          className="f"
          style={{ flex: 1, minWidth: 200, maxWidth: 360 }}
          placeholder="Search a question, patient or lead code"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
      </div>
      {error && <div className="warnbox">{error}</div>}
      {!data ? (
        <p className="sub2">Loading…</p>
      ) : !data.items.length ? (
        <p className="sub2">
          {show === "new"
            ? "No new questions. Every question the chatbot could not answer shows here."
            : "Nothing here."}
        </p>
      ) : (
        <div className="tw">
          <table>
            <thead>
              <tr>
                <th>Question</th>
                <th>Patient</th>
                <th>Asked</th>
                <th>Type</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((a) => (
                <tr key={a.id}>
                  <td style={{ whiteSpace: "normal", minWidth: 240 }}>
                    {a.question}
                  </td>
                  <td>
                    {a.lead_code ? (
                      <button
                        className="lq-link"
                        onClick={() => setOpenCode(a.lead_code)}
                        title="Open the lead"
                      >
                        {a.lead_name || "Patient"} · {a.lead_code}
                      </button>
                    ) : (
                      <span className="sub2">No number left</span>
                    )}
                  </td>
                  <td>{when(a.created_at)}</td>
                  <td>
                    <span
                      className={`badge ${a.reason === "medical" ? "b-vi" : "b-bk"}`}
                    >
                      {a.reason === "medical" ? "Medical" : "No answer"}
                    </span>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <div
                      className="row"
                      style={{ gap: 6, justifyContent: "flex-end" }}
                    >
                      <button
                        className="btn g sm"
                        disabled={busy === a.id}
                        onClick={() => mark(a, !a.answered)}
                      >
                        {a.answered ? "Mark new" : "Mark answered"}
                      </button>
                      {a.reason !== "medical" && (
                        <button
                          className="btn g sm"
                          disabled={busy === a.id}
                          onClick={() => toKnowledgeBase(a)}
                        >
                          Add to Knowledge base
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && data.items.length < data.total && (
        <button
          className="btn g"
          style={{ marginTop: 12 }}
          onClick={() => setPage((p) => p + 1)}
        >
          Show more ({data.total - data.items.length} more)
        </button>
      )}
      <div
        className={`ov${openCode ? " on" : ""}`}
        onClick={() => setOpenCode(null)}
      />
      <aside className={`dr${openCode ? " on" : ""}`} aria-hidden={!openCode}>
        {openCode && (
          <LeadDrawer
            code={openCode}
            clinicId={clinicId}
            onClose={() => setOpenCode(null)}
            onChanged={() => setVersion((v) => v + 1)}
          />
        )}
      </aside>
    </div>
  );
}
