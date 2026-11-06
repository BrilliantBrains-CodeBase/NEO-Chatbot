"use client";

import { useEffect, useState } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import AssignControls from "@/components/inbox/AssignControls";
import RequestCard from "@/components/inbox/RequestCard";
import { level } from "@/lib/access";
import { api, ApiError, type InboxItem, type LeadDetail, type LeadOptions } from "@/lib/api";
import { EVENT, SOURCE, STAGE_LABEL, when } from "./labels";
import LeadActions from "./LeadActions";

const errorText = (e: unknown) => (e instanceof ApiError ? e.message : "Could not load this lead.");

/** The lead drawer, the same from Leads and from the Inbox. A lead without an owner shows how to assign it
 * and its requests read-only; once assigned, its owner handles the requests and works the stages here. */
export default function LeadDrawer({
  code,
  clinicId,
  onClose,
  onChanged,
}: {
  code: string;
  clinicId: string | undefined;
  onClose: () => void;
  onChanged: () => void; // the list behind should load again
}) {
  const { me, clinic, toast, refreshInbox } = useCrm();
  const [version, setVersion] = useState(0);
  const [detail, setDetail] = useState<{ key: string; d?: LeadDetail; error?: string }>({ key: "" });
  const [asks, setAsks] = useState<{ key: string; items: InboxItem[] }>({ key: "", items: [] });
  const [treatments, setTreatments] = useState<string[]>([]);
  const key = `${code}|${version}`;

  useEffect(() => {
    let live = true;
    const url = `/v1/crm/leads/${encodeURIComponent(code)}`;
    api<LeadDetail>(url).then(
      (d) => live && setDetail({ key, d }),
      (e) => live && setDetail((now) => ({ ...now, key, error: errorText(e) })),
    );
    api<InboxItem[]>(`${url}/requests`).then(
      (items) => live && setAsks({ key, items }),
      () => live && setAsks({ key, items: [] }),
    );
    return () => {
      live = false;
    };
  }, [code, key]);

  useEffect(() => {
    if (!clinicId) return;
    api<LeadOptions>(`/v1/crm/lead-options?clinic=${clinicId}`).then(
      (o) => setTreatments(o.treatments),
      () => {},
    );
  }, [clinicId]);

  // While the next version loads (after a change), the last one stays on screen: no flash.
  const lead = detail.d?.code === code ? detail.d : undefined;
  const error = detail.key === key ? detail.error : undefined;
  const requests = asks.key.split("|")[0] === code ? asks.items : [];

  function reload() {
    setVersion((v) => v + 1);
    onChanged();
  }
  function handled(message: string) {
    toast(message);
    refreshInbox();
    reload();
  }

  const inInbox = !!lead && !lead.assigned_id && lead.stage !== "lost" && lead.stage !== "invalid";
  const canAct = !inInbox && level(me, clinic, "inbox") === "edit";

  return (
    <>
      <div className="dh">
        <div>
          <h2>{lead?.name ?? "…"}</h2>
          <p>
            {code}
            {lead && <span className={`badge ${STAGE_LABEL[lead.stage]?.[1]}`}>{STAGE_LABEL[lead.stage]?.[0]}</span>}
            {inInbox && <span className="badge b-fu">In Inbox</span>}
          </p>
        </div>
        <button className="x" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>
      <div className="db">
        {error && <div className="warnbox">{error}</div>}
        {lead && (
          <>
            {inInbox && (
              <div className="sec assign-box">
                <h4>ASSIGN</h4>
                <p className="sub2" style={{ margin: "0 0 8px" }}>
                  This lead is waiting in the Inbox. Once assigned, it moves to Leads and its owner confirms
                  bookings and calls back from there.
                </p>
                <AssignControls clinicId={clinicId} codes={[lead.code]} onAssigned={reload} />
              </div>
            )}
            <div className="kv">
              {(
                [
                  ["Phone", lead.phone],
                  ["Email", lead.email],
                  ["Source", `${SOURCE[lead.source] ?? lead.source}${lead.campaign ? " · " + lead.campaign : ""}`],
                  ["Treatment", lead.treatment],
                  ["Doctor", lead.doctor],
                  ["Type", lead.type === "online" ? "Online" : lead.type ? "In-clinic" : null],
                  ["Assigned", lead.assigned ?? "Unassigned"],
                  ["Contacts", String(lead.contacts)],
                  ["First contact", when(lead.created_at)],
                  ["Verified", lead.verified ? "Yes" : "No"],
                ] as [string, string | null][]
              ).map(([k, v]) => (
                <div key={k}>
                  <span>{k}</span>
                  <b>{v || "—"}</b>
                </div>
              ))}
            </div>
            {requests.length > 0 && (
              <div className="sec">
                <h4>PENDING REQUESTS ({requests.length})</h4>
                {inInbox && (
                  <p className="sub2" style={{ margin: "0 0 8px" }}>
                    Assign the lead to confirm or reject these.
                  </p>
                )}
                <div className="rq-list">
                  {requests.map((r) => (
                    <RequestCard
                      key={r.id}
                      item={r}
                      clinicId={clinicId}
                      treatments={treatments}
                      canAct={canAct}
                      onDone={handled}
                    />
                  ))}
                </div>
              </div>
            )}
            {!inInbox && <LeadActions key={lead.code} lead={lead} clinicId={clinicId} onChange={reload} />}
            {lead.notes && (
              <div className="sec">
                <h4>NOTES</h4>
                <p>{lead.notes}</p>
              </div>
            )}
            <div className="sec">
              <h4>TIMELINE</h4>
              {lead.events.length ? (
                <div className="tl">
                  {lead.events.map((e, i) => (
                    <div key={i}>
                      {EVENT[e.kind] ?? e.kind}
                      {typeof e.data.outcome === "string" && `: ${e.data.outcome.replace("_", " ")}`}
                      {typeof e.data.text === "string" && e.data.text && `: ${e.data.text}`}
                      {typeof e.data.to === "string" && ` to ${STAGE_LABEL[e.data.to]?.[0] ?? e.data.to}`}
                      <small>
                        {when(e.at)}
                        {e.by ? " · " + e.by : ""}
                      </small>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="sub2">Nothing yet.</p>
              )}
            </div>
            <div className="sec">
              <h4>LATEST CHAT</h4>
              {lead.chat.length ? (
                <div className="list">
                  {lead.chat.map((m, i) => (
                    <div className="li" key={i}>
                      <div className="x">
                        <b>{m.role === "bot" ? "Bot" : "Patient"}</b>
                        <span style={{ whiteSpace: "pre-wrap" }}>{m.text}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="sub2">No chat with this lead.</p>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
