"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import Live, { Today } from "@/components/crm/Live";
import Loading from "@/components/crm/Loading";
import { useCrm } from "@/components/crm/CrmProvider";
import { canSee } from "@/lib/access";
import { api, ApiError, type Count, type Dashboard, type Totals } from "@/lib/api";
import { Bars, ChartTable, dayLabel, Donut, LineChart, num, Sparkline, type Series, type Slice } from "./charts";
import MonthCalendar from "./MonthCalendar";
import Schedule from "./Schedule";

// The CRM home: what needs staff now, this period's numbers next to the period before, how leads and
// bookings moved day by day, where leads came from, how far they got, how appointments ended, the chatbot,
// and (on the right) the month's calendar and today's schedule. One period choice drives every number.

const PERIODS = [7, 30, 90];
const SOURCE: Record<string, [string, string]> = {
  // colour follows the source, whatever its rank
  chatbot: ["Chatbot", "var(--s1)"],
  meta_ads: ["Meta Ads", "var(--s2)"],
  google_ads: ["Google Ads", "var(--s3)"],
  website_form: ["Website form", "var(--s4)"],
  whatsapp: ["WhatsApp", "var(--s5)"],
  manual: ["Added by staff", "var(--s7)"],
};
const ANSWER: Record<string, string> = { flow: "Guided flow", rule: "Fixed rule", kb: "Knowledge base", menu: "Menu", lead: "Lead form" };
const STAGE: Record<string, string> = { new: "New", follow_up: "Follow up", booked: "Booked", visited: "Visited", lost: "Lost", invalid: "Invalid" };

const I = {
  leads: <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M19 8v6M22 11h-6" />,
  book: <path d="M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM9 16l2 2 4-4" />,
  visit: <path d="M22 11.1V12a10 10 0 1 1-5.9-9.1M22 4 12 14l-3-3" />,
  rate: <path d="M3 17l6-6 4 4 8-8M14 7h7v7" />,
  phone: <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z" />,
  inbox: <path d="M22 12h-6l-2 3h-4l-2-3H2M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z" />,
  clock: <path d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2" />,
  help: <path d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01" />,
  check: <path d="M20 6 9 17l-5-5" />,
  x: <path d="M18 6 6 18M6 6l12 12" />,
  minus: <path d="M5 12h14" />,
};
const Icon = ({ d }: { d: ReactNode }) => <svg viewBox="0 0 24 24" aria-hidden>{d}</svg>;

function Hello({ name }: { name?: string }) {
  const h = new Date().getHours();
  return <>{(h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening") + (name ? `, ${name}` : "")}</>;
}

/** The change from the period before. Up is good for every number on this page. */
function Delta({ now, before, points = false }: { now: number; before: number; points?: boolean }) {
  let text: string;
  let dir = Math.sign(now - before);
  if (points) text = `${Math.abs(now - before).toFixed(1)} pts`;
  else if (before === 0) {
    text = now === 0 ? "No change" : "New";
    dir = now === 0 ? 0 : 1;
  } else text = `${Math.abs(Math.round(((now - before) / before) * 100))}%`;
  if (dir === 0 && text !== "No change") text = "No change";
  return (
    <span className={`db-delta ${dir > 0 ? "up" : dir < 0 ? "down" : ""}`}>
      {dir !== 0 && <Icon d={<path d={dir > 0 ? "M12 19V5M5 12l7-7 7 7" : "M12 5v14M19 12l-7 7-7-7"} />} />}
      <span className="sr-only">{dir > 0 ? "Up " : dir < 0 ? "Down " : ""}</span>
      {text}
    </span>
  );
}

const rate = (t: Totals) => (t.leads ? (t.converted / t.leads) * 100 : 0);

export default function DashboardView() {
  const { clinic, me } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const [days, setDays] = useState(7);
  const [data, setData] = useState<{ key: string; clinic?: string; d?: Dashboard; error?: string }>({ key: "" });
  const key = `${clinicId}-${days}`;
  const see = (path: string) => canSee(me, clinic, path);

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Dashboard>(`/v1/crm/dashboard?clinic=${clinicId}&days=${days}`).then(
      (d) => live && setData({ key, clinic: clinicId, d }),
      (e) => live && setData({ key, clinic: clinicId, error: e instanceof ApiError ? e.message : "Could not load the dashboard." }),
    );
    return () => {
      live = false;
    };
  }, [clinicId, days, key]);

  // While another period loads, the last one stays on screen, faded (no jump, no flash).
  const d = data.clinic === clinicId ? data.d : undefined;
  const stale = data.key !== key;
  const error = !stale ? data.error : undefined;
  const vs = `vs previous ${days} days`;

  return (
    <div className="dash">
      <div className="db-head ph">
        <div>
          <h1>
            <Live fallback={<>Hello{me ? `, ${me.name.split(" ")[0]}` : ""}</>}>
              <Hello name={me?.name.split(" ")[0]} />
            </Live>
          </h1>
          <p>
            {clinic} · <Live><Today /></Live>
          </p>
        </div>
        <div className="seg" role="group" aria-label="Period">
          {PERIODS.map((n) => (
            <button key={n} className={n === days ? "on" : ""} aria-pressed={n === days} onClick={() => setDays(n)}>
              {n} days
            </button>
          ))}
        </div>
      </div>
      {error && <div className="warnbox db-full">{error}</div>}
      {!d && !error && <Loading />}
      {d && (
        <>
          <Needs d={d} see={see} />
          <div className={`db-kpis${stale ? " db-stale" : ""}`}>
            <Kpi title="New leads" icon={I.leads} tone="blue" value={num(d.now.leads)} href={see("/leads") ? "/leads" : undefined}
              delta={<Delta now={d.now.leads} before={d.before.leads} />} vs={vs} trend={d.series.map((s) => s.leads)} />
            <Kpi title="Bookings" icon={I.book} tone="violet" value={num(d.now.bookings)} href={see("/appointments") ? "/appointments" : undefined}
              delta={<Delta now={d.now.bookings} before={d.before.bookings} />} vs={vs} trend={d.series.map((s) => s.bookings)} />
            <Kpi title="Visits" icon={I.visit} tone="green" value={num(d.now.visits)} href={see("/leads") ? "/leads?stage=visited" : undefined}
              delta={<Delta now={d.now.visits} before={d.before.visits} />} vs={vs} trend={d.series.map((s) => s.visits)}
              note="Appointments marked Visited" />
            <Kpi title="Lead to booking" icon={I.rate} tone="amber" value={`${rate(d.now).toFixed(1)}%`}
              delta={<Delta now={rate(d.now)} before={rate(d.before)} points />} vs={vs}
              meter={rate(d.now)} note={`${num(d.now.converted)} of ${num(d.now.leads)} leads booked`} />
          </div>
          <aside className="db-rail" aria-label="Calendar and today">
            {clinicId && <MonthCalendar clinicId={clinicId} linkDays={see("/appointments")} />}
            <Schedule today={d.today} link={see("/leads")} />
          </aside>
          <div className={`db-charts${stale ? " db-stale" : ""}`}>
            <div className="db-row">
              <Trend d={d} />
              <Sources d={d} />
            </div>
            <div className="db-row">
              <Funnel d={d} see={see} />
              <Outcomes d={d} />
            </div>
            <div className="db-row">
              <Chatbot d={d} vs={vs} />
              <section className="card db-card">
                <h3>
                  Top treatments <small>new leads</small>
                </h3>
                <Bars rows={d.treatments.map((t) => ({ key: t.key, label: t.key, value: t.count }))} empty="No treatments chosen in this period." />
              </section>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/** The things waiting for staff right now (not tied to the period). */
function Needs({ d, see }: { d: Dashboard; see: (p: string) => boolean }) {
  const items: [string, number, string, ReactNode, boolean][] = [
    ["Callbacks waiting", d.callbacks_waiting, "/leads?request=callback", I.phone, d.callbacks_waiting > 0],
    ["Waiting in Inbox", d.inbox_pending, "/inbox", I.inbox, d.inbox_pending > 0],
    ["Leads to follow up", d.followups_due, "/leads?stage=follow_up", I.clock, d.followups_due > 0],
    ["Unanswered chat questions", d.unanswered, "", I.help, false],
  ];
  return (
    <div className="db-needs" aria-label="Needs you now">
      {items.map(([label, n, href, icon, hot]) => {
        const body = (
          <>
            <span className="db-needs-i"><Icon d={icon} /></span>
            <b>{num(n)}</b>
            <span>{label}</span>
          </>
        );
        const cls = `db-need${hot ? " hot" : ""}${n === 0 ? " zero" : ""}`;
        return href && see(href.split("?")[0]) ? (
          <Link key={label} href={href} className={cls}>{body}</Link>
        ) : (
          <div key={label} className={cls}>{body}</div>
        );
      })}
    </div>
  );
}

function Kpi(p: {
  title: string;
  icon: ReactNode;
  tone: "blue" | "violet" | "green" | "amber";
  value: string;
  delta: ReactNode;
  vs: string;
  href?: string;
  trend?: number[];
  meter?: number;
  note?: string;
}) {
  const body = (
    <>
      <div className="db-kpi-t">
        <span className={`db-ic ${p.tone}`}><Icon d={p.icon} /></span>
        {p.title}
      </div>
      <div className="db-kpi-n">{p.value}</div>
      <div className="db-kpi-d">
        {p.delta} <span>{p.vs}</span>
      </div>
      {p.trend && <Sparkline values={p.trend} />}
      {p.meter !== undefined && (
        <div className="db-meter" role="meter" aria-valuenow={Math.round(p.meter)} aria-valuemin={0} aria-valuemax={100} aria-label={p.title}>
          <i style={{ width: `${Math.min(100, p.meter)}%` }} />
        </div>
      )}
      {p.note && <div className="db-kpi-note">{p.note}</div>}
    </>
  );
  return p.href ? (
    <Link href={p.href} className="card db-kpi">{body}</Link>
  ) : (
    <div className="card db-kpi">{body}</div>
  );
}

const METRICS = [
  ["leads", "Leads"],
  ["bookings", "Bookings"],
  ["visits", "Visits"],
  ["chats", "Chats"],
] as const;

function Trend({ d }: { d: Dashboard }) {
  const [metric, setMetric] = useState<(typeof METRICS)[number][0]>("leads");
  const label = METRICS.find(([k]) => k === metric)![1];
  const days = d.series.map((s) => s.day);
  const series: Series[] = [{ key: "now", label: `${label}, last ${d.days} days`, values: d.series.map((s) => s[metric]), color: "var(--s1)", area: true }];
  if (metric === "leads")
    series.push({ key: "before", label: `Previous ${d.days} days`, values: d.series.map((s) => s.leads_before), color: "var(--prev)" });
  const total = series[0].values.reduce((a, b) => a + b, 0);
  return (
    <section className="card db-card">
      <h3>
        <span>
          {label} over time <small>{num(total)} in {d.days} days</small>
        </span>
        <span className="seg db-seg" role="group" aria-label="Show">
          {METRICS.map(([k, l]) => (
            <button key={k} className={k === metric ? "on" : ""} aria-pressed={k === metric} onClick={() => setMetric(k)}>
              {l}
            </button>
          ))}
        </span>
      </h3>
      {series.length > 1 && (
        <div className="ch-keys">
          {series.map((s) => (
            <span key={s.key}>
              <i style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
      <LineChart days={days} series={series} label={`${label} per day over the last ${d.days} days`} />
      <ChartTable
        head={["Day", ...series.map((s) => s.label)]}
        rows={days.map((day, i) => [dayLabel(day, true), ...series.map((s) => s.values[i])])}
      />
    </section>
  );
}

function Sources({ d }: { d: Dashboard }) {
  const slices: Slice[] = d.sources.map((s) => ({
    key: s.key,
    label: SOURCE[s.key]?.[0] ?? s.key,
    value: s.count,
    color: SOURCE[s.key]?.[1] ?? "var(--prev)",
  }));
  return (
    <section className="card db-card">
      <h3>
        Lead sources <small>last {d.days} days</small>
      </h3>
      {slices.length ? (
        <Donut slices={slices} label="New leads by source" middle={{ value: num(d.now.leads), text: "new leads" }} />
      ) : (
        <p className="ch-empty">No new leads in this period.</p>
      )}
    </section>
  );
}

/** How far this period's leads got: all → booked (or visited) → visited, with the share between steps. */
function Funnel({ d, see }: { d: Dashboard; see: (p: string) => boolean }) {
  const c = Object.fromEntries(d.funnel.map((f) => [f.key, f.count]));
  const all = d.funnel.reduce((a, f) => a + f.count, 0);
  const steps: [string, number, string][] = [
    ["All new leads", all, "var(--f1)"],
    ["Booked", (c.booked ?? 0) + (c.visited ?? 0), "var(--f2)"],
    ["Visited", c.visited ?? 0, "var(--f3)"],
  ];
  const share = (a: number, b: number) => (b ? `${Math.round((a / b) * 100)}%` : "–");
  const open: Count[] = d.funnel.filter((f) => ["new", "follow_up", "lost", "invalid"].includes(f.key));
  return (
    <section className="card db-card">
      <h3>
        Lead journey <small>leads from the last {d.days} days, by how far they got</small>
      </h3>
      {all === 0 ? (
        <p className="ch-empty">No new leads in this period.</p>
      ) : (
        <ol className="db-funnel">
          {steps.map(([label, n, color], i) => (
            <li key={label}>
              {i > 0 && (
                <div className="db-step">
                  {share(n, steps[i - 1][1])} {i === 1 ? "of leads booked" : "of bookings visited"}
                </div>
              )}
              <div className="db-fbar">
                <span className="ch-l">{label}</span>
                <span className="ch-track-h">
                  <i style={{ width: `${Math.max(n ? 2 : 0, (n / all) * 100)}%`, background: color }} />
                  <b>{num(n)}</b>
                </span>
              </div>
            </li>
          ))}
        </ol>
      )}
      <div className="db-stages">
        <span>Still open or closed:</span>
        {open.map((f) =>
          see("/leads") ? (
            <Link key={f.key} href={`/leads?stage=${f.key}`} className="db-chip">
              {STAGE[f.key]} <b>{num(f.count)}</b>
            </Link>
          ) : (
            <span key={f.key} className="db-chip">
              {STAGE[f.key]} <b>{num(f.count)}</b>
            </span>
          ),
        )}
      </div>
    </section>
  );
}

/** How appointments on days in the period ended. Status colours, each with an icon and a word. */
function Outcomes({ d }: { d: Dashboard }) {
  const c = Object.fromEntries(d.outcomes.map((o) => [o.key, o.count]));
  const n = (...k: string[]) => k.reduce((a, x) => a + (c[x] ?? 0), 0);
  const slices: Slice[] = [
    { key: "visited", label: "Visited", value: n("visited"), color: "var(--good)", icon: <Icon d={I.check} /> },
    { key: "no_show", label: "No-show", value: n("no_show"), color: "var(--critical)", icon: <Icon d={I.x} /> },
    { key: "missed", label: "Missed (never confirmed)", value: n("missed"), color: "var(--serious)", icon: <Icon d={I.help} /> },
    { key: "cancelled", label: "Cancelled or refused", value: n("cancelled", "rejected"), color: "var(--prev)", icon: <Icon d={I.minus} /> },
    { key: "open", label: "Upcoming or not marked", value: n("pending", "confirmed"), color: "var(--idle)", icon: <Icon d={I.clock} /> },
  ];
  const ended = slices[0].value + slices[1].value;
  const total = slices.reduce((a, s) => a + s.value, 0);
  return (
    <section className="card db-card">
      <h3>
        Appointments <small>{num(total)} on days in this period</small>
      </h3>
      {total ? (
        <Donut
          slices={slices}
          label="Appointments by outcome"
          middle={ended ? { value: `${Math.round((slices[0].value / ended) * 100)}%`, text: "show-up rate" } : { value: num(total), text: "appointments" }}
        />
      ) : (
        <p className="ch-empty">No appointments in this period.</p>
      )}
    </section>
  );
}

function Chatbot({ d, vs }: { d: Dashboard; vs: string }) {
  const share = d.now.chats ? (d.now.chat_leads / d.now.chats) * 100 : 0;
  return (
    <section className="card db-card">
      <h3>
        Chatbot <small>last {d.days} days</small>
      </h3>
      <div className="db-mini">
        <div>
          <span>Chats</span>
          <b>{num(d.now.chats)}</b>
          <Delta now={d.now.chats} before={d.before.chats} /> <small>{vs}</small>
        </div>
        <div>
          <span>Became leads</span>
          <b>{share.toFixed(0)}%</b>
          <small>{num(d.now.chat_leads)} of {num(d.now.chats)} chats</small>
          <div className="db-meter" role="meter" aria-valuenow={Math.round(share)} aria-valuemin={0} aria-valuemax={100} aria-label="Chats that became leads">
            <i style={{ width: `${Math.min(100, share)}%` }} />
          </div>
        </div>
        <div>
          <span>Questions it could not answer</span>
          <b>{num(d.unanswered)}</b>
          <small>waiting for review</small>
        </div>
      </div>
      <h4 className="db-sub">How replies were made</h4>
      <Bars rows={d.chat_answered_by.map((a) => ({ key: a.key, label: ANSWER[a.key] ?? a.key, value: a.count }))} empty="No chatbot replies in this period." />
    </section>
  );
}
