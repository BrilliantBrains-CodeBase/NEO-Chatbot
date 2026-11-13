"use client";

import Loading from "@/components/crm/Loading";
import { useEffect, useState, type ReactNode } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError } from "@/lib/api";
import LeadQuestionsTab from "./LeadQuestionsTab";
import ReviewsTab, { ReviewsPreview, type Reviews } from "./ReviewsTab";
import ServicesTab, { ServiceCard, type Services } from "./ServicesTab";

// Dashboard → Clinic info: Contact & hours, Services, Reviews and Lead questions, one draft with a preview.
// Contact & hours is built first; the other tabs follow one by one.

type Day = { day: string; open: boolean; start: string; end: string };
type Contact = {
  phone: string;
  emergency_number: string;
  whatsapp: string;
  whatsapp_message: string;
  email: string;
  address: string;
  landmark: string;
  parking: string;
  maps_link: string;
  hours: Day[];
  closed_message: string;
};
type Settings = {
  draft: {
    contact: Contact;
    services: Services;
    reviews: Reviews;
    appearance: {
      look: { name: string };
      colours: { main: string; whatsapp: string };
    };
  };
  changed: boolean;
};

const TABS = [
  ["contact", "Contact & hours"],
  ["services", "Services"],
  ["reviews", "Reviews"],
  ["flows", "Lead questions"],
] as const;
type Tab = (typeof TABS)[number][0];

const clock = (t: string) => {
  const [h, m] = t.split(":").map(Number);
  return `${((h + 11) % 12) + 1}${m ? ":" + String(m).padStart(2, "0") : ""} ${h < 12 ? "AM" : "PM"}`;
};
const sameHours = (hours: Day[]) => {
  const open = hours.filter((d) => d.open);
  return open.every((d) => d.start === open[0].start && d.end === open[0].end);
};
/** "Open every day except Tuesday, 10 AM to 7 PM." when every open day has the same hours. */
function hoursText(hours: Day[]) {
  const open = hours.filter((d) => d.open);
  if (!open.length) return "Closed every day.";
  const closed = hours.filter((d) => !d.open).map((d) => d.day);
  if (!sameHours(hours))
    return open
      .map((d) => `${d.day.slice(0, 3)} ${clock(d.start)}–${clock(d.end)}`)
      .join(", ");
  return `Open ${closed.length ? `every day except ${closed.join(", ")}` : "every day"}, ${clock(open[0].start)} to ${clock(open[0].end)}.`;
}

export default function ClinicInfoView() {
  const { clinic, me, toast } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const [loaded, setLoaded] = useState<{
    clinic: string;
    s?: Settings;
    error?: string;
  }>({ clinic: "" });
  const [form, setForm] = useState<Contact | null>(null);
  const [tab, setTab] = useState<Tab>("contact");
  const [perDay, setPerDay] = useState(false);
  const [services, setServices] = useState<Services | null>(null);
  const [svc, setSvc] = useState<number | null>(null); // the treatment open in the list (and the preview)
  const [reviews, setReviews] = useState<Reviews | null>(null);
  const [quote, setQuote] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Settings>(`/v1/crm/console/${clinicId}/settings`).then(
      (s) => {
        if (!live) return;
        setLoaded({ clinic: clinicId, s });
        setForm(s.draft.contact);
        setServices(s.draft.services);
        setReviews(s.draft.reviews);
      },
      (e) =>
        live &&
        setLoaded({
          clinic: clinicId,
          error: e instanceof ApiError ? e.message : "Could not load.",
        }),
    );
    return () => {
      live = false;
    };
  }, [clinicId]);

  const s = loaded.clinic === clinicId ? loaded.s : undefined;
  const contactDirty =
    !!s && !!form && JSON.stringify(form) !== JSON.stringify(s.draft.contact);
  const servicesDirty =
    !!s &&
    !!services &&
    JSON.stringify(services) !== JSON.stringify(s.draft.services);
  const reviewsDirty =
    !!s &&
    !!reviews &&
    JSON.stringify(reviews) !== JSON.stringify(s.draft.reviews);
  const dirty = contactDirty || servicesDirty || reviewsDirty;

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function call(
    path: string,
    method: string,
    body?: object,
    done?: string,
  ) {
    if (!clinicId) return;
    setBusy(true);
    setError("");
    try {
      const next = await api<Settings>(`/v1/crm/console/${clinicId}/${path}`, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      });
      setLoaded({ clinic: clinicId, s: next });
      setForm(next.draft.contact);
      setServices(next.draft.services);
      setReviews(next.draft.reviews);
      if (done) toast(done);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not save. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (loaded.clinic === clinicId && loaded.error)
    return <div className="warnbox">{loaded.error}</div>;
  if (!s || !form || !services || !reviews) return <Loading />;

  async function save() {
    // Each changed tab is its own section of the draft; the last save shows "Draft saved".
    const todo: [string, object][] = [];
    if (reviewsDirty && reviews) todo.push(["settings/reviews", reviews]);
    if (servicesDirty && services) todo.push(["settings/services", services]);
    if (contactDirty && form) todo.push(["settings/contact", form]);
    for (const [k, [path, body]] of todo.entries())
      await call(
        path,
        "PUT",
        body,
        k === todo.length - 1 ? "Draft saved" : undefined,
      );
  }

  const set = (patch: Partial<Contact>) => setForm({ ...form, ...patch });
  const setDay = (i: number, patch: Partial<Day>) =>
    set({
      hours: form.hours.map((d, k) => (k === i ? { ...d, ...patch } : d)),
    });
  const firstOpen = form.hours.find((d) => d.open) ?? form.hours[0];
  const setAllTimes = (patch: Partial<Day>) =>
    set({ hours: form.hours.map((d) => ({ ...d, ...patch })) });
  const showPerDay = perDay || !sameHours(form.hours);

  return (
    <>
      <div className="ph">
        <div>
          <h1>Clinic info</h1>
        </div>
        <div className="row">
          <button className="pill" disabled={busy || !dirty} onClick={save}>
            Save changes
          </button>
          <button
            className="btn"
            disabled={busy || dirty || !s.changed}
            onClick={() => call("publish", "POST", undefined, "Published")}
          >
            Publish
          </button>
        </div>
      </div>
      {error && <div className="warnbox">{error}</div>}
      <div
        className="split-preview"
        style={{
          display: "grid",
          // Lead questions is a list, not a chatbot setting: the full width, no preview.
          gridTemplateColumns:
            tab === "flows" ? "minmax(0, 1fr)" : "minmax(0, 1fr) 320px",
          gap: 16,
          alignItems: "start",
        }}
      >
        <div className="card">
          <div className="tabs">
            {TABS.map(([k, label]) => (
              <button
                key={k}
                className={tab === k ? "on" : ""}
                onClick={() => setTab(k)}
              >
                {label}
              </button>
            ))}
          </div>
          {tab === "reviews" ? (
            <ReviewsTab
              value={reviews}
              onChange={setReviews}
              selected={quote}
              onSelect={setQuote}
            />
          ) : tab === "services" ? (
            <ServicesTab
              value={services}
              onChange={setServices}
              selected={svc}
              onSelect={setSvc}
            />
          ) : tab === "flows" ? (
            clinicId ? (
              <LeadQuestionsTab clinicId={clinicId} />
            ) : null
          ) : (
            <div className="ci">
              <section>
                <h4>Phone & WhatsApp</h4>
                <div className="ci-grid">
                  <In
                    label="Clinic phone"
                    value={form.phone}
                    max={16}
                    ph="+919731207940"
                    on={(v) => set({ phone: v })}
                  />
                  <In
                    label="WhatsApp"
                    value={form.whatsapp}
                    max={16}
                    ph="+919731207940"
                    on={(v) => set({ whatsapp: v })}
                  />
                  <In
                    label="Emergency"
                    value={form.emergency_number}
                    max={16}
                    ph="108"
                    on={(v) => set({ emergency_number: v })}
                  />
                  <In
                    label="Email"
                    value={form.email}
                    max={120}
                    ph="Optional"
                    on={(v) => set({ email: v })}
                  />
                  <In
                    wide
                    label="WhatsApp opens with"
                    value={form.whatsapp_message}
                    max={300}
                    ph="Hi, I would like to know about…"
                    on={(v) => set({ whatsapp_message: v })}
                  />
                </div>
              </section>

              <section>
                <h4>Address</h4>
                <div className="ci-grid">
                  <In
                    wide
                    label="Address"
                    value={form.address}
                    max={300}
                    ph="Floor, building, area, city, PIN"
                    on={(v) => set({ address: v })}
                  />
                  <In
                    label="Landmark"
                    value={form.landmark}
                    max={120}
                    ph="Optional"
                    on={(v) => set({ landmark: v })}
                  />
                  <In
                    label="Parking"
                    value={form.parking}
                    max={200}
                    ph="Optional"
                    on={(v) => set({ parking: v })}
                  />
                  <In
                    wide
                    label="Google Maps link"
                    value={form.maps_link}
                    max={300}
                    ph="https://maps.app.goo.gl/…"
                    on={(v) => set({ maps_link: v })}
                  />
                </div>
              </section>

              <section>
                <h4>Opening hours</h4>
                <div className="ci-days" role="group" aria-label="Open days">
                  {form.hours.map((d, i) => (
                    <button
                      key={d.day}
                      type="button"
                      title={d.day}
                      aria-pressed={d.open}
                      className={d.open ? "on" : ""}
                      onClick={() => setDay(i, { open: !d.open })}
                    >
                      {d.day.slice(0, 2)}
                    </button>
                  ))}
                  {!showPerDay && (
                    <span className="ci-times">
                      <input
                        type="time"
                        step={900}
                        aria-label="Opens"
                        value={firstOpen.start}
                        onChange={(e) => setAllTimes({ start: e.target.value })}
                      />
                      <span>to</span>
                      <input
                        type="time"
                        step={900}
                        aria-label="Closes"
                        value={firstOpen.end}
                        onChange={(e) => setAllTimes({ end: e.target.value })}
                      />
                    </span>
                  )}
                </div>
                {showPerDay && (
                  <div className="ci-perday">
                    {form.hours.map((d, i) =>
                      d.open ? (
                        <span key={d.day} className="ci-times">
                          <b>{d.day.slice(0, 3)}</b>
                          <input
                            type="time"
                            step={900}
                            aria-label={`${d.day} opens`}
                            value={d.start}
                            onChange={(e) =>
                              setDay(i, { start: e.target.value })
                            }
                          />
                          <span>–</span>
                          <input
                            type="time"
                            step={900}
                            aria-label={`${d.day} closes`}
                            value={d.end}
                            onChange={(e) => setDay(i, { end: e.target.value })}
                          />
                        </span>
                      ) : null,
                    )}
                  </div>
                )}
                <div
                  className="row"
                  style={{ justifyContent: "space-between", marginTop: 6 }}
                >
                  <span className="sub2">{hoursText(form.hours)}</span>
                  <button
                    type="button"
                    className="lnk"
                    style={{
                      border: 0,
                      background: "none",
                      cursor: "pointer",
                      fontSize: "var(--fs-small)",
                    }}
                    onClick={() => {
                      if (showPerDay)
                        setAllTimes({
                          start: firstOpen.start,
                          end: firstOpen.end,
                        });
                      setPerDay(!showPerDay);
                    }}
                  >
                    {showPerDay
                      ? "Same hours every day"
                      : "Different hours per day"}
                  </button>
                </div>
                <div className="ci-grid" style={{ marginTop: 8 }}>
                  <In
                    wide
                    label="When closed, the chat says"
                    value={form.closed_message}
                    max={300}
                    on={(v) => set({ closed_message: v })}
                  />
                </div>
              </section>
            </div>
          )}
        </div>
        {tab === "flows" ? null : tab === "reviews" ? (
          <div className="card">
            <h3>
              Live preview <small>&quot;Show me reviews&quot;</small>
            </h3>
            <ReviewsPreview
              r={reviews}
              quote={
                quote !== null
                  ? reviews.quotes[quote]
                  : reviews.quotes.find((q) => q.show)
              }
              main={s.draft.appearance.colours.main}
            />
          </div>
        ) : tab === "services" ? (
          <div className="card">
            <h3>
              Live preview <small>the treatment card</small>
            </h3>
            {(() => {
              const shown =
                svc !== null
                  ? services.items[svc]
                  : services.items.find((x) => x.show);
              return shown ? (
                <ServiceCard s={shown} main={s.draft.appearance.colours.main} />
              ) : (
                <p className="sub2">Add a treatment to see its card.</p>
              );
            })()}
          </div>
        ) : (
          <Preview
            c={form}
            name={s.draft.appearance.look.name}
            main={s.draft.appearance.colours.main}
            wa={s.draft.appearance.colours.whatsapp}
          />
        )}
      </div>
    </>
  );
}

/** A small labelled text box; wide ones take the whole row. */
function In({
  label,
  value,
  max,
  ph,
  wide,
  on,
}: {
  label: string;
  value: string;
  max: number;
  ph?: string;
  wide?: boolean;
  on: (v: string) => void;
}) {
  return (
    <label className={wide ? "wide" : undefined}>
      <span>{label}</span>
      <input
        value={value}
        maxLength={max}
        placeholder={ph}
        onChange={(e) => on(e.target.value)}
      />
    </label>
  );
}

/** The chat's answer to "Where is the clinic?", built from the form. */
function Preview({
  c,
  name,
  main,
  wa,
}: {
  c: Contact;
  name: string;
  main: string;
  wa: string;
}) {
  const chip = (label: string, color: string): ReactNode => (
    <span
      style={{
        border: `1.5px solid ${color}`,
        color: "#1F2937",
        borderRadius: 999,
        padding: "4px 9px",
        fontSize: 11,
        fontWeight: 600,
      }}
    >
      {label}
    </span>
  );
  const pretty = (n: string) =>
    n.startsWith("+91") && n.length === 13
      ? `+91 ${n.slice(3, 8)} ${n.slice(8)}`
      : n;
  return (
    <div className="card">
      <h3>
        Live preview <small>&quot;Where is the clinic?&quot;</small>
      </h3>
      <div
        className="chat-preview"
        style={{ background: "#F3F5F9", borderRadius: 12, padding: 10 }}
      >
        <div
          style={{ background: "#fff", borderRadius: 14, overflow: "hidden" }}
        >
          <div
            style={{
              background: main,
              color: "#fff",
              padding: "8px 12px",
              fontWeight: 700,
              fontSize: 13,
            }}
          >
            {name}
          </div>
          <div
            style={{
              padding: 10,
              display: "flex",
              flexDirection: "column",
              gap: 8,
              fontSize: 12,
            }}
          >
            <span
              style={{
                alignSelf: "flex-end",
                background: main,
                color: "#fff",
                borderRadius: 12,
                padding: "6px 9px",
              }}
            >
              Where is the clinic?
            </span>
            <span
              style={{
                alignSelf: "flex-start",
                background: "#F1F3F7",
                borderRadius: 12,
                padding: "7px 9px",
                maxWidth: "92%",
                whiteSpace: "pre-line",
              }}
            >
              {[
                c.address,
                c.landmark && `Landmark: ${c.landmark}`,
                c.parking && `Parking: ${c.parking}`,
                hoursText(c.hours),
              ]
                .filter(Boolean)
                .join("\n")}
            </span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {c.maps_link && chip("Open in Google Maps", main)}
              {c.phone && chip(`Call ${pretty(c.phone)}`, main)}
              {c.whatsapp && chip("WhatsApp us", wa)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
