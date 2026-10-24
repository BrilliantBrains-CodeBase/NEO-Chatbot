"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Live, { Today } from "@/components/crm/Live";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError, type Count, type Dashboard } from "@/lib/api";

const SOURCE: Record<string, string> = { chatbot: "Chatbot", meta_ads: "Meta Ads", google_ads: "Google Ads", manual: "Manual", whatsapp: "WhatsApp" };
const STAGE: Record<string, [string, string]> = {
  new: ["New", "#2563EB"],
  follow_up: ["Follow Up", "#D97706"],
  booked: ["Booked", "#7C3AED"],
  visited: ["Visited", "#059669"],
  lost: ["Lost", "#DC2626"],
  invalid: ["Invalid", "#6B7280"],
};
const ANSWER: Record<string, string> = { flow: "Guided flow", rule: "Fixed rule", kb: "Knowledge base", menu: "Menu", lead: "Lead form" };

function Bars({ rows, label }: { rows: Count[]; label: (k: string) => string }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  if (!rows.length) return <p className="sub2">No data in this period.</p>;
  return rows.map((r) => (
    <div className="bar" key={r.key}>
      <span>{label(r.key)}</span>
      <i><em style={{ width: `${(r.count / max) * 100}%` }} /></i>
      <b>{r.count}</b>
    </div>
  ));
}

export default function DashboardPage() {
  const { clinic, me } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const [days, setDays] = useState(7);
  const [data, setData] = useState<{ key: string; d?: Dashboard; error?: string }>({ key: "" });
  const key = `${clinicId}-${days}`;

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Dashboard>(`/v1/crm/dashboard?clinic=${clinicId}&days=${days}`).then(
      (d) => live && setData({ key, d }),
      (e) => live && setData({ key, error: e instanceof ApiError ? e.message : "Could not load the dashboard." }),
    );
    return () => {
      live = false;
    };
  }, [clinicId, days, key]);

  const d = data.key === key ? data.d : undefined;
  const error = data.key === key ? data.error : undefined;
  const kpis: [string, number | undefined, string, string][] = [
    ["New leads", d?.new_leads, `Last ${days} days`, "/leads"],
    ["Pending in Inbox", d?.inbox_pending, "Waiting for staff", "/inbox"],
    ["Callbacks waiting", d?.callbacks_waiting, "Patients asked for a call", "/inbox"],
    ["Follow-ups due", d?.followups_due, "Today and overdue", "/leads"],
  ];

  return (
    <>
      <div className="ph">
        <div>
          <h1>Good morning{me ? ", " + me.name.split(" ")[0] : ""}</h1>
          <p>
            {clinic} · <Live><Today /></Live>
          </p>
        </div>
        <div className="seg">
          {[7, 30, 90].map((n) => (
            <button key={n} className={n === days ? "on" : ""} onClick={() => setDays(n)}>
              {n} days
            </button>
          ))}
        </div>
      </div>
      {error && <div className="warnbox">{error}</div>}
      <div className="grid4">
        {kpis.map(([t, n, s, href]) => (
          <Link key={t} href={href} className="card kpi">
            <div className="t">{t}</div>
            <div className="n">{n ?? "…"}</div>
            <div className="s">{s}</div>
          </Link>
        ))}
      </div>
      <div className="grid2">
        <div className="card">
          <h3>
            Today&apos;s appointments <small>{d ? d.today.length : ""}</small>
          </h3>
          <div className="list">
            {d && !d.today.length && <p className="sub2">No appointments today.</p>}
            {d?.today.map((a) => (
              <div className="li" key={a.lead_code + a.time}>
                <div className="tm">{a.time ?? "Any"}</div>
                <div className="x">
                  <b>{a.patient}</b>
                  <span>
                    {[a.treatment, a.doctor, a.type === "online" ? "Online" : "In-clinic"].filter(Boolean).join(" · ")}
                  </span>
                </div>
                <span className={`badge ${a.status === "confirmed" ? "b-bk" : "b-fu"}`}>
                  {a.status === "confirmed" ? "Confirmed" : "Pending"}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <h3>
            Funnel <small>leads, last {days} days</small>
          </h3>
          <div className="fun">
            {d?.funnel.map((f) => (
              <div key={f.key} style={{ background: STAGE[f.key][1] }}>
                {STAGE[f.key][0]} <span>{f.count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="grid2">
        <div className="card">
          <h3>Leads by source</h3>
          {d && <Bars rows={d.sources} label={(k) => SOURCE[k] ?? k} />}
          <h3 style={{ marginTop: 16 }}>Top treatments</h3>
          {d && <Bars rows={d.treatments} label={(k) => k} />}
        </div>
        <div className="card">
          <h3>
            Chatbot <small>last {days} days</small>
          </h3>
          {d && (
            <>
              <div className="bar"><span>Chats</span><i /><b>{d.chats}</b></div>
              <div className="bar"><span>Became leads</span><i /><b>{d.chat_leads}</b></div>
              <div className="bar"><span>Not answered</span><i /><b>{d.unanswered}</b></div>
              <h3 style={{ marginTop: 16 }}>How replies were made</h3>
              <Bars rows={d.chat_answered_by} label={(k) => ANSWER[k] ?? k} />
            </>
          )}
        </div>
      </div>
    </>
  );
}
