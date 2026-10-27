"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";

// The test chat on the canvas: runs the saved DRAFT flow (patients see nothing), tap or type like a patient.
// The block the chat is on lights up on the canvas (onAt).

type Btn = { id: string; label: string; action: string; value?: string };
type Msg = {
  text: string;
  buttons?: Btn[];
  media?: { kind: string; url: string };
  open?: { action: string; value: string };
  cards?: { title: string }[];
};
type Reply = {
  messages: Msg[];
  at: string | null;
  lead: Record<string, string> | null;
  state: Record<string, unknown>;
};
type Line = { from: "bot" | "me"; msg: Msg };

const OPEN: Record<string, string> = {
  call: "Opens the phone to call",
  whatsapp: "Opens WhatsApp",
  link: "Opens the link",
};

export default function TestChat({
  clinicId,
  dirty,
  onAt,
  onClose,
}: {
  clinicId: string;
  dirty: boolean;
  onAt: (id: string | null) => void;
  onClose: () => void;
}) {
  const [lines, setLines] = useState<Line[]>([]);
  const [state, setState] = useState<Record<string, unknown> | null>(null);
  const [text, setText] = useState("");
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [error, setError] = useState("");
  const [run, setRun] = useState(0); // a new number starts the chat again
  const end = useRef<HTMLDivElement>(null);

  async function send(body: object, mine?: string) {
    if (mine) setLines((l) => [...l, { from: "me", msg: { text: mine } }]);
    setError("");
    try {
      const r = await api<Reply>(`/v1/crm/console/${clinicId}/flow/test`, {
        method: "POST",
        body: JSON.stringify({ device, ...body }),
      });
      setLines((l) => [
        ...l,
        ...r.messages.map((m) => ({ from: "bot" as const, msg: m })),
        ...(r.lead
          ? [
              {
                from: "bot" as const,
                msg: {
                  text: `Test lead (not saved yet): ${Object.entries(r.lead)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(", ")}`,
                },
              },
            ]
          : []),
      ]);
      setState(r.state);
      onAt(r.at);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The test chat failed.");
    }
  }

  useEffect(() => {
    let live = true;
    void api<Reply>(`/v1/crm/console/${clinicId}/flow/test`, {
      method: "POST",
      body: JSON.stringify({ device }),
    })
      .then((r) => {
        if (!live) return;
        setLines(r.messages.map((m) => ({ from: "bot", msg: m })));
        setState(r.state);
        onAt(r.at);
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "The test chat failed."),
      );
    return () => {
      live = false;
    };
    // device and onAt are read at the start of each run only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clinicId, run]);

  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [lines]);

  const last = lines.length - 1;
  return (
    <div className="wf-test">
      <div className="wf-test-head">
        <b>Test chat</b>
        <select
          value={device}
          onChange={(e) => setDevice(e.target.value as "desktop" | "mobile")}
          aria-label="Device"
        >
          <option value="desktop">Desktop</option>
          <option value="mobile">Mobile</option>
        </select>
        <button
          className="pill"
          onClick={() => {
            setLines([]);
            setRun((n) => n + 1);
          }}
        >
          Restart
        </button>
        <button
          aria-label="Close"
          onClick={() => {
            onAt(null);
            onClose();
          }}
        >
          ✕
        </button>
      </div>
      {dirty && (
        <p className="wf-test-note">
          Runs the saved draft: save your changes to test them.
        </p>
      )}
      <div className="wf-test-body">
        {lines.map((l, i) => (
          <div key={i} className={`wf-test-msg ${l.from}`}>
            {l.msg.text && <p>{l.msg.text}</p>}
            {l.msg.media && (
              <p className="wf-test-note">
                [{l.msg.media.kind}] {l.msg.media.url}
              </p>
            )}
            {l.msg.cards && (
              <p className="wf-test-note">
                Cards: {l.msg.cards.map((c) => c.title).join(" · ")}
              </p>
            )}
            {l.msg.open && (
              <p className="wf-test-note">
                {OPEN[l.msg.open.action] ?? "Opens"}: {l.msg.open.value}
              </p>
            )}
            {!!l.msg.buttons?.length && (
              <div className="wf-test-btns">
                {l.msg.buttons.map((b) => (
                  <button
                    key={b.id}
                    className="pill"
                    disabled={
                      i !== last && l.from === "bot" && !b.id.includes(":")
                    }
                    onClick={() => send({ state, tap: b.id }, b.label)}
                  >
                    {b.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {error && <p className="warnbox">{error}</p>}
        <div ref={end} />
      </div>
      <form
        className="wf-test-input"
        onSubmit={(e) => {
          e.preventDefault();
          if (!text.trim() || !state) return;
          void send({ state, text }, text);
          setText("");
        }}
      >
        <input
          value={text}
          maxLength={500}
          placeholder="Type like a patient…"
          onChange={(e) => setText(e.target.value)}
        />
        <button className="btn" disabled={!text.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
