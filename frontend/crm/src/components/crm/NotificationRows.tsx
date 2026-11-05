"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import {
  ago,
  groupNotes,
  needsAction,
  noteTitle,
  type BellNote,
  type NoteList,
  type NoteSummary,
} from "@/lib/notifications";
import { useCrm } from "./CrmProvider";
import Icon from "./Icon";

/** One page of notifications, read again when the counts change, plus the actions on them. */
export function useNotes(
  params: { show: "all" | "unread"; kind?: string; limit: number; offset: number },
  enabled: boolean,
) {
  const { clinicId, notes, setNotes, toast } = useCrm();
  const query = new URLSearchParams({
    clinic: clinicId ?? "",
    show: params.show,
    limit: String(params.limit),
    offset: String(params.offset),
    ...(params.kind ? { kind: params.kind } : {}),
  }).toString();
  const [list, setList] = useState<{ query: string; d?: NoteList; error?: string }>({ query: "" });
  const [version, setVersion] = useState(0);
  const unread = notes?.unread;
  const urgent = notes?.urgent;

  useEffect(() => {
    if (!enabled || !clinicId) return;
    let live = true;
    api<NoteList>(`/v1/crm/notifications?${query}`).then(
      (d) => live && setList({ query, d }),
      (e: unknown) =>
        live &&
        setList((now) => ({
          query,
          d: now.query === query ? now.d : undefined,
          error: e instanceof ApiError ? e.message : "Could not load notifications.",
        })),
    );
    return () => {
      live = false;
    };
  }, [enabled, clinicId, query, unread, urgent, version]);

  const act = useCallback(
    async (path: string, withClinic = false) => {
      try {
        const s = await api<NoteSummary>(
          `/v1/crm/notifications/${path}${withClinic ? `?clinic=${clinicId}` : ""}`,
          { method: "POST" },
        );
        setNotes(s);
        setVersion((v) => v + 1);
      } catch (e) {
        toast(e instanceof ApiError ? e.message : "Could not save. Please try again.");
      }
    },
    [clinicId, setNotes, toast],
  );

  const same = list.query === query;
  return {
    data: same ? list.d : undefined,
    error: same ? list.error : undefined,
    act,
    retry: () => setVersion((v) => v + 1),
  };
}

/** The rows, under Needs action, Today, Yesterday and Earlier. */
export default function NotificationRows({
  items,
  act,
  onOpen,
}: {
  items: BellNote[];
  act: (path: string) => Promise<void>;
  onOpen: (href: string) => void;
}) {
  return (
    <>
      {groupNotes(items).map(([label, rows]) => (
        <div key={label} className="nt-group">
          <div className={`nt-head${label === "Needs action" ? " urgent" : ""}`}>{label}</div>
          {rows.map((n) => (
            <Row key={n.id} n={n} act={act} onOpen={onOpen} />
          ))}
        </div>
      ))}
    </>
  );
}

function Row({
  n,
  act,
  onOpen,
}: {
  n: BellNote;
  act: (path: string) => Promise<void>;
  onOpen: (href: string) => void;
}) {
  const waiting = needsAction(n);
  const href = n.request_id ? `/inbox?tab=${n.tab}&open=${n.request_id}` : null;
  const detail = [waiting ? n.reason : n.treatment, ago(n.created_at)].filter(Boolean).join(" · ");
  const unread = !n.read && !n.resolved;
  return (
    <div className={`nt-row${unread ? " unread" : ""}${waiting ? " urgent" : ""}${n.resolved ? " done" : ""}`}>
      <button
        className="nt-main"
        onClick={() => {
          if (!n.read) void act(`${n.id}/read`);
          if (href) onOpen(href);
        }}
      >
        <span className="nt-dot" aria-hidden="true" />
        <span className="nt-text">
          <span className="nt-title">{noteTitle(n)}</span>
          <small>{detail}</small>
          {n.resolved && (
            <small className="nt-handled">
              {n.resolved_by ? `Handled by ${n.resolved_by}` : "Handled"}
            </small>
          )}
          {n.time_passed && <small className="nt-passed">Time passed: call the patient</small>}
        </span>
      </button>
      <span className="nt-acts">
        {waiting && !n.request_id ? (
          <button className="nt-ack" onClick={() => void act(`${n.id}/dismiss`)}>
            Acknowledge
          </button>
        ) : (
          <>
            <button
              className="nt-ic"
              title={n.read ? "Mark as unread" : "Mark as read"}
              aria-label={n.read ? `Mark as unread: ${noteTitle(n)}` : `Mark as read: ${noteTitle(n)}`}
              onClick={() => void act(`${n.id}/${n.read ? "unread" : "read"}`)}
            >
              {n.read ? <span className="nt-ring" aria-hidden="true" /> : <Icon name="check" />}
            </button>
            {!waiting && (
              <button
                className="nt-ic"
                title="Clear"
                aria-label={`Clear: ${noteTitle(n)}`}
                onClick={() => void act(`${n.id}/dismiss`)}
              >
                <Icon name="x" />
              </button>
            )}
          </>
        )}
      </span>
    </div>
  );
}
