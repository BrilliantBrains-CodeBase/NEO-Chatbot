"use client";

import Loading from "@/components/crm/Loading";
import Icon, { type IconName } from "@/components/crm/Icon";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";
import ApiPanel from "./ApiPanel";
import OnlineSetup from "./OnlineSetup";
import SheetsPanel from "./SheetsPanel";
import FormsPanel from "./FormsPanel";
import GmailPanel from "./GmailPanel";
import WebhooksPanel from "./WebhooksPanel";
import WhatsAppPanel from "./WhatsAppPanel";

// Chatbot → Integrations: the outside services the chatbot and the CRM use. A hub of tiles (what each does, if
// it is on, what it did lately), and for each a page: the steps, the controls, what you need, what happens,
// troubleshooting and developer notes. Keys stay on the server (Supabase Vault) and are never shown again.

type Integration = {
  id: string;
  name: string;
  does: string;
  state: "connected" | "not_connected" | "not_built";
  detail: string[];
  last: string | null;
};
type Category = "Bookings" | "Lead sources" | "Messaging" | "Automation";
type Guide = {
  icon: IconName;
  category: Category;
  tagline: string;
  steps: (i: Integration) => [string, boolean][];
  need: ReactNode[];
  happens: ReactNode[];
  trouble: [string, ReactNode][];
  dev?: ReactNode;
};

const num = (i: Integration, re: RegExp) => Number(i.detail.join(" ").match(re)?.[1] ?? 0);
const on = (i: Integration) => i.state === "connected";
const Code = ({ children }: { children: string }) => (
  <pre className="wi-pre">
    <code>{children}</code>
  </pre>
);

const GUIDES: Record<string, Guide> = {
  calcom: {
    icon: "cal",
    category: "Bookings",
    tagline: "Online consults with a Google Meet link, booked when staff approve them.",
    steps: (i) => [
      ["Create an API key in Cal.com", i.detail.some((d) => d.startsWith("Account: "))],
      ["Connect it here", i.detail.some((d) => d.startsWith("Account: "))],
      ["Choose the doctors who consult online", num(i, /(\d+) online consults/) > 0],
      ["First online consult booked", num(i, /(\d+) online consults/) > 0],
    ],
    need: [
      "A Cal.com account (the free plan works).",
      "Each online doctor's Google Calendar connected in Cal.com, so the Meet link is made.",
      <>An API key: Cal.com → <b>Settings → Developer → API keys</b>.</>,
    ],
    happens: [
      "A patient asks for an online consult in the chat, or staff book one.",
      "When staff approve it, Cal.com books it and emails the patient the Google Meet link.",
      "Cancelled or moved in Cal.com? The CRM follows on its own (once the backend is online over https).",
    ],
    trouble: [
      ["“Not a valid key”", "Copy the whole key (it starts with cal_live_) from Cal.com and paste it again."],
      ["No times to offer", "Give the doctor online hours in Chatbot → Doctors and tick them under online doctors here."],
      ["No Meet link", "Connect the doctor's Google Calendar (with Google Meet) inside Cal.com."],
      ["“Bookings sync back” not set up", "It is set up automatically once the backend runs on its public https address."],
    ],
    dev: (
      <>
        <p>
          The key is checked with Cal.com and kept encrypted in Supabase Vault; it is never sent to the browser
          again. Connecting creates one Cal.com webhook to <code>/v1/integrations/calcom/&lt;clinic&gt;</code>, signed
          with <code>X-Cal-Signature-256</code> (HMAC-SHA256 of the body).
        </p>
        <p>
          It listens for <code>BOOKING_CANCELLED</code> (the appointment is cancelled) and{" "}
          <code>BOOKING_RESCHEDULED</code> (the appointment moves, with the new Meet link).
        </p>
      </>
    ),
  },
  sheet: {
    icon: "file",
    category: "Lead sources",
    tagline: "Meta lead ads into the Inbox: each new row in your Google Sheet becomes a lead.",
    steps: (i) => [
      ["Add the sheet here", num(i, /(\d+) sheet\(s\) added/) > 0],
      ["Paste the script in the sheet and run it once", num(i, /(\d+) leads received/) > 0],
      ["Turn the tab on and match its columns", num(i, /(\d+) leads received/) > 0],
      ["Leads arriving", num(i, /(\d+) leads received/) > 0],
    ],
    need: [
      "The Google Sheet your Meta lead ads write to (Meta → Leads Center, or a Zapier / Make sync).",
      "Edit access to that sheet, to paste and run the script.",
    ],
    happens: [
      "Every 5 minutes the script sends the sheet's tabs and column names, and the new rows of the tabs you turned on (up to 50 a run).",
      "Each row becomes a lead (source Meta Ads), waiting in the Inbox. The same phone updates its lead.",
      "The script adds a CRM column to the tab and writes each row's lead code there (or why it was skipped), so a row is never sent twice.",
    ],
    trouble: [
      ["Tabs and columns don't appear", <>In the sheet run <code>crmSetup</code> once and allow the permissions Google asks for. They appear within 5 minutes.</>],
      ["“Authorization required”", "The script runs as the person who ran crmSetup: run it with an account that can edit the sheet."],
      ["Rows are skipped", "The CRM column says why. A row needs a name and a phone or email: check the column matching for this tab."],
    ],
    dev: (
      <p>
        The script is Google Apps Script with its own private address inside (one per sheet). It runs on a time
        trigger every 5 minutes (rows added by Meta don&apos;t fire edit triggers) and posts the new rows as JSON to{" "}
        <code>/v1/integrations/sheets/&lt;sheet&gt;</code>. Its functions start with <code>crm</code>, so they never
        clash with the sheet&apos;s own scripts.
      </p>
    ),
  },
  forms: {
    icon: "code",
    category: "Lead sources",
    tagline: "Your own forms on your website and landing pages, straight into the Inbox.",
    steps: (i) => [
      ["Add a form here", num(i, /(\d+) form\(s\) added/) > 0],
      ["Send its submissions to its address", num(i, /(\d+) on/) > 0 || num(i, /(\d+) leads received/) > 0],
      ["Match its fields and turn it on", num(i, /(\d+) on/) > 0],
      ["Leads arriving", num(i, /(\d+) leads received/) > 0],
    ],
    need: [
      "A form that can send its data to another address (a webhook): your developer's code, or a form builder such as Elementor, Webflow, Typeform or Google Forms.",
      <>Tip: the simpler option is <b>Website install → Forms → leads</b>, which picks up your site&apos;s forms with no code.</>,
    ],
    happens: [
      "The first submission shows the form's fields here; you match them to ours (name, phone, email…).",
      "Once the form is on, each submission becomes a lead (source Website form) in the Inbox.",
    ],
    trouble: [
      ["No fields appear", "Submit the form once after connecting it; the fields come from that first submission."],
      ["Submissions arrive but no lead", "Turn the form on, and make sure name plus a phone or email are matched."],
      ["“This form's address is not valid”", "Copy the address again from this page: each form has its own private key."],
    ],
    dev: (
      <>
        <p>
          POST each submission to the form&apos;s private address (from the form&apos;s card above). It accepts JSON (also
          sent as <code>text/plain</code>, as Google Apps Script does) or a normal form post. A flat object, or nested one
          level; up to 100 KB.
        </p>
        <Code>{`fetch(FORM_ADDRESS, {
  method: "POST",
  headers: { "Content-Type": "text/plain;charset=utf-8" },
  body: JSON.stringify({ name: "Asha Rao", phone: "9800000001", email: "asha@example.com", message: "Hair fall" })
});`}</Code>
        <p>
          It answers <code>{`{"ok": true, "result": "<lead code>"}`}</code>. Until the form is on, it only records the
          fields.
        </p>
      </>
    ),
  },
  api: {
    icon: "plug",
    category: "Lead sources",
    tagline: "Your own address and key: any website, app or tool sends leads and booking requests as JSON.",
    steps: (i) => [
      ["Add an endpoint", num(i, /(\d+) endpoint/) > 0],
      ["Paste a sample payload and match its fields", num(i, /(\d+) on/) > 0],
      ["Turn it on", num(i, /(\d+) on/) > 0],
      ["Calls arriving", num(i, /(\d+) calls taken/) > 0],
    ],
    need: [
      "The system that will send the data: your website's developer, a landing page tool, Zapier or Make, or a partner app.",
      "A sample of the JSON it sends (from its documentation or one test call).",
    ],
    happens: [
      "The system POSTs JSON to the endpoint's address with its key in the X-API-Key header.",
      "Lead only: each call makes a lead, waiting in the Inbox. The same phone updates its lead.",
      "Lead + booking request: also a request in the Inbox. A free time is held for the patient; a taken or missing time still comes in, and the front desk arranges it. No date at all: a call back request.",
      "Fields you don't match are kept on the lead as More information (switch it off to ignore them).",
    ],
    trouble: [
      ["401 Invalid API key", "Send the key in the X-API-Key header exactly as shown; after “Make a new key” the old one stops working."],
      ["403 switched off", "Turn the endpoint on (it needs Name and a Phone or Email matched)."],
      ["422 needs a name and a phone or email", "The payload's fields don't match: check the matching with “Test with the sample”."],
      ["Booking without a held time", "The asked time was not free or not understood: the request is in the Inbox for the front desk to pick a time."],
      ["Duplicate leads", "Match a unique field to External id: a call repeated with the same id answers the first result."],
    ],
    dev: (
      <>
        <p>
          <code>POST</code> the endpoint&apos;s address with <code>Content-Type: application/json</code> and{" "}
          <code>X-API-Key: &lt;key&gt;</code>. Body: one JSON object, up to 100 KB, nested fields allowed. At most 120 calls
          a minute per endpoint.
        </p>
        <Code>{`fetch(ENDPOINT_ADDRESS, {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-API-Key": API_KEY },
  body: JSON.stringify({ name: "Asha Rao", phone: "9800000001", service: "PRP",
                         date: "2026-11-10", time: "10:30", mode: "in clinic" })
});`}</Code>
        <p>
          Answer <code>200</code>:{" "}
          <code>{`{"ok": true, "lead_code": "NFHT-00048", "request_id": "…", "time_held": true, "duplicate": false}`}</code>.
          Errors: <code>{`{"ok": false, "error": "…"}`}</code> with 400 (not JSON), 401 (key), 403 (switched off), 413
          (too large), 422 (no name or phone/email), 429 (too many calls).
        </p>
        <p>
          Dates: <code>2026-11-10</code>, <code>10/11/2026</code> (day first) or <code>10 Nov 2026</code>. Times:{" "}
          <code>10:30</code>, <code>10:30 AM</code> or <code>2 pm</code>. Online when the type says online, video or
          virtual. Doctor: by name (“Dr Sandeep”). Source: meta_ads, google_ads, whatsapp, referral, walk_in,
          phone_call, website_form or manual, else “API”.
        </p>
        <p>
          Keep the key on a server when you can: a key in a web page&apos;s code can be read by anyone. Make a new key
          if it leaks.
        </p>
      </>
    ),
  },
  whatsapp: {
    icon: "wa",
    category: "Messaging",
    tagline: "Request received, booking confirmations and the Check my appointment OTP on WhatsApp.",
    steps: (i) => [
      ["Connect Interakt (API key)", on(i)],
      ["Set each message's approved template", on(i)],
      ["Send a test message", false],
    ],
    need: [
      "An Interakt account linked to the clinic's WhatsApp Business number.",
      <>The API key: Interakt → <b>Settings → Developer Setting</b>.</>,
      "WhatsApp templates approved by Meta in Interakt: a business can write first only with an approved template.",
    ],
    happens: [
      "Request received: when a patient books or asks for a call back in the chat.",
      "Appointment booked (in-clinic or online): when staff confirm it in the CRM.",
      "Imported lead: to each new lead when an Admin imports a list.",
      "OTP: for Check my appointment in the chat.",
    ],
    trouble: [
      ["Test fails with a template error", "The template name and language must match Interakt exactly, and it must be approved."],
      ["Blanks filled wrongly", "Each {{1}}, {{2}}… must be set to the value it shows in the approved text, in order."],
      ["Nothing is sent", "Check the message is switched on and has a template; the number needs its country code."],
    ],
    dev: (
      <p>
        Messages go through Interakt&apos;s public API (<code>api.interakt.ai/v1/public/message</code>) with the clinic&apos;s
        key, kept encrypted in Supabase Vault. Each message type is sent only when it is switched on and has an
        approved template.
      </p>
    ),
  },
  email: {
    icon: "inbox",
    category: "Messaging",
    tagline: "Emails from the clinic's own Gmail: staff login codes now, patient emails next.",
    steps: (i) => [
      ["Turn on 2-Step Verification in that Google account", on(i)],
      ["Create a 16-letter App password", on(i)],
      ["Connect the Gmail here", on(i)],
      ["Send a test email", false],
    ],
    need: [
      "A Gmail or Google Workspace address for the clinic.",
      <>2-Step Verification on, then an App password: Google Account → <b>Security → App passwords</b>.</>,
    ],
    happens: [
      "Login codes and emails from the CRM come from this address, with the sender name you set.",
      "Until it is connected, emails come from the Brilliant Brains Gmail (if one is set up).",
    ],
    trouble: [
      ["“Username and password not accepted”", "Use the 16-letter App password, not the account's normal password."],
      ["No App passwords option", "Turn on 2-Step Verification first; some Workspace admins also have to allow App passwords."],
      ["Emails land in spam", "Send a few tests and mark them “Not spam”; set a clear sender name."],
    ],
    dev: (
      <p>
        Sent over Gmail SMTP with the App password, kept encrypted in Supabase Vault and never shown again. The last
        emails sent are listed above, with any error Gmail returned.
      </p>
    ),
  },
  webhooks: {
    icon: "flow",
    category: "Automation",
    tagline: "Send CRM events to Zapier, Make or your own system, and receive leads from them.",
    steps: (i) => [
      ["Add a sending or receiving webhook", num(i, /(\d+) sending/) + num(i, /(\d+) receiving/) > 0],
      ["Send a test event", !!i.last],
      ["Events flowing", !!i.last],
    ],
    need: [
      "Sending: an https address that accepts JSON POSTs (a Zapier or Make “Catch hook”, or your own endpoint).",
      "Receiving: a system that can POST JSON to the private address shown here.",
    ],
    happens: [
      "Sending: each chosen event (new lead, booking request, call back request, appointment confirmed) is posted as JSON within seconds.",
      "A failed delivery is retried 3 times, and every attempt is logged here.",
      "Receiving: each POST becomes a lead in the Inbox (one lead per phone) and gets back its lead code.",
    ],
    trouble: [
      ["Deliveries fail", "Open the webhook to see the status code and error: the address must be https and answer 2xx within 10 seconds."],
      ["Signature doesn't match", "Compute it over the raw body exactly as received, with the webhook's signing secret."],
      ["Received leads are missing", "Each needs a name and a phone or email; other keys go into the lead's notes."],
    ],
    dev: (
      <>
        <p>
          <b>Sending.</b> Each event is a POST with <code>Content-Type: application/json</code>,{" "}
          <code>X-Neo-Event</code> and <code>X-Neo-Signature: sha256=&lt;hex&gt;</code> (HMAC-SHA256 of the raw body with
          the webhook&apos;s signing secret, shown on the webhook above). Events: <code>lead_new</code>,{" "}
          <code>booking_request</code>, <code>callback_request</code>, <code>appointment_confirmed</code>.
        </p>
        <Code>{`{
  "event": "booking_request", "clinic": "NFHT", "at": "2026-11-06T10:15:00+00:00",
  "lead_code": "NFHT-00046", "type": "book", "name": "Asha Rao",
  "phone": "+919800000001", "email": "asha@example.com",
  "treatment": "PRP Treatment", "date": "2026-11-10", "time": "10:30", "reason": null
}`}</Code>
        <p>
          <code>lead_new</code> carries lead_code, name, phone, email, treatment, campaign, source;{" "}
          <code>appointment_confirmed</code> carries lead_code, name, phone, type, date, time, doctor. Answer 2xx within
          10 seconds; otherwise it is retried after 2, 10 and 30 seconds. Redirects are not followed.
        </p>
        <Code>{`// Node.js: check the signature over the raw body
const crypto = require("crypto");
const expected = "sha256=" + crypto.createHmac("sha256", SECRET).update(rawBody).digest("hex");
const ok = crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(req.headers["x-neo-signature"] || ""));`}</Code>
        <p>
          <b>Receiving.</b> POST one lead as JSON to the private address (its <code>?key=</code> is the password). Keys:{" "}
          <code>name</code>, <code>phone</code>, <code>email</code>, <code>city</code>, <code>treatment</code>,{" "}
          <code>campaign</code>, <code>ad_name</code>, <code>notes</code>, <code>date</code> and <code>source</code>{" "}
          (meta_ads, google_ads, manual, whatsapp, referral, walk_in, phone_call). Other keys go into the lead&apos;s
          notes. The answer is <code>{`{"lead_code": "NFHT-00047"}`}</code>.
        </p>
        <Code>{`curl -X POST "RECEIVING_ADDRESS" -H "Content-Type: application/json" \\
  -d '{"name":"Asha Rao","phone":"9800000001","treatment":"PRP","source":"meta_ads"}'`}</Code>
      </>
    ),
  },
};
const CATEGORIES: ("All" | Category)[] = ["All", "Bookings", "Lead sources", "Messaging", "Automation"];

export default function IntegrationsView() {
  return (
    <Suspense fallback={<Loading />}>
      <Hub />
    </Suspense>
  );
}

function Hub() {
  const { clinic, me } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const router = useRouter();
  const params = useSearchParams();
  const openId = params.get("open");
  const [data, setData] = useState<{ clinic: string; list: Integration[] } | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"All" | Category>("All");

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Integration[]>(`/v1/crm/console/${clinicId}/integrations`).then(
      (list) => live && setData({ clinic: clinicId, list }),
      (e) => live && setError(e instanceof ApiError ? e.message : "Could not load the integrations."),
    );
    return () => {
      live = false;
    };
  }, [clinicId]);

  const list = data && data.clinic === clinicId ? data.list : null;
  const go = (id: string | null) =>
    router.replace(id ? `/assistant/integrations?open=${id}` : "/assistant/integrations", { scroll: false });
  const open = list?.find((i) => i.id === openId);

  if (open && clinicId)
    return (
      <Detail
        i={open}
        clinicId={clinicId}
        onBack={() => go(null)}
        onList={(l) => setData({ clinic: clinicId, list: l })}
      />
    );

  const known = list?.filter((i) => GUIDES[i.id]) ?? [];
  const connected = known.filter(on).length;
  const shown = known.filter((i) => filter === "All" || GUIDES[i.id].category === filter);
  return (
    <div className="wi">
      <div className="ph">
        <div>
          <h1>Integrations</h1>
          <p>Connect the services your clinic already uses. Keys are kept encrypted on the server and never shown again.</p>
        </div>
        {list && (
          <span className={`wi-pill ${connected ? "live" : "off"}`}>
            <i />
            {connected} of {known.length} connected
          </span>
        )}
      </div>
      <div className="wi-tabs" role="tablist" aria-label="Category" style={{ marginBottom: 14 }}>
        {CATEGORIES.map((c) => (
          <button key={c} role="tab" aria-selected={filter === c} className={filter === c ? "on" : ""} onClick={() => setFilter(c)}>
            {c}
          </button>
        ))}
      </div>
      {error && <div className="warnbox">{error}</div>}
      {list === null && !error && <Loading />}
      <div className="ig-grid">
        {shown.map((i) => {
          const g = GUIDES[i.id];
          return (
            <article key={i.id} className={`card ig-tile${on(i) ? " on" : ""}`}>
              <div className="ig-tile-h">
                <span className="ig-icon">
                  <Icon name={g.icon} />
                </span>
                <span className={`wi-pill ${on(i) ? "live" : "off"}`}>
                  <i />
                  {on(i) ? "Connected" : "Not connected"}
                </span>
              </div>
              <div>
                <h3>{i.name}</h3>
                <span className="sub2 ig-cat">{g.category}</span>
              </div>
              <p className="ig-line">{g.tagline}</p>
              <p className="sub2 ig-stat">{i.detail[i.detail.length - 1]}</p>
              <div className="ig-foot">
                <span className="sub2">
                  {i.last ? `Last used ${new Date(i.last).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}` : "Not used yet"}
                </span>
                <button className={`btn sm${on(i) ? " g" : ""}`} onClick={() => go(i.id)}>
                  {on(i) ? "Manage" : "Set up →"}
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

function Detail({
  i,
  clinicId,
  onBack,
  onList,
}: {
  i: Integration;
  clinicId: string;
  onBack: () => void;
  onList: (l: Integration[]) => void;
}) {
  const g = GUIDES[i.id];
  // A later step done means the earlier ones are too.
  const raw = g.steps(i);
  const last = raw.map(([, d]) => d).lastIndexOf(true);
  const steps = raw.map(([label, d], n) => [label, d || n < last] as [string, boolean]);
  const current = steps.findIndex(([, d]) => !d);
  return (
    <div className="wi">
      <button className="lnk ig-back" onClick={onBack}>
        ← All integrations
      </button>
      <div className="ph">
        <div className="ig-title">
          <span className="ig-icon big">
            <Icon name={g.icon} />
          </span>
          <div>
            <h1>{i.name}</h1>
            <p>{i.does}</p>
          </div>
        </div>
        <span className={`wi-pill ${on(i) ? "live" : "off"}`}>
          <i />
          {on(i) ? "Connected" : "Not connected"}
        </span>
      </div>

      <ol className="wi-steps" aria-label="Setup progress" style={{ gridTemplateColumns: `repeat(${steps.length},minmax(0,1fr))` }}>
        {steps.map(([label, done], n) => (
          <li key={label} className={done ? "done" : n === current ? "now" : ""}>
            <span>{done ? "✓" : n + 1}</span>
            {label}
          </li>
        ))}
      </ol>

      <div className="wi-grid">
        <section className="wi-col">
          <div className="card ig-setup">
            <div className="wi-col-h">
              <h3>Set up</h3>
              <span className="sub2">
                {i.last ? `Last used ${new Date(i.last).toLocaleString("en-IN")}` : "Not used yet"}
              </span>
            </div>
            <ul className="wi-facts">
              {i.detail.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
            {i.id === "api" && <ApiPanel clinicId={clinicId} />}
            {i.id === "whatsapp" && <WhatsAppPanel clinicId={clinicId} />}
            {i.id === "webhooks" && <WebhooksPanel clinicId={clinicId} />}
            {i.id === "email" && (
              <GmailPanel
                url={`/v1/crm/console/${clinicId}/integrations/email`}
                fallbackNote="Until then, emails come from the BB Gmail (if BB connected one)."
              />
            )}
            {i.id === "forms" && <FormsPanel clinicId={clinicId} />}
            {i.id === "sheet" && <SheetsPanel clinicId={clinicId} />}
            {i.id === "calcom" && (
              <CalcomConnect clinicId={clinicId} own={i.detail[0]?.startsWith("Account: ") ?? false} onDone={onList} />
            )}
          </div>
        </section>
        <section className="wi-col">
          <div className="card ig-info">
            <h3>What you need</h3>
            <ul className="wi-facts">
              {g.need.map((n, k) => (
                <li key={k}>{n}</li>
              ))}
            </ul>
            <h3>What happens</h3>
            <ol className="wi-howto">
              {g.happens.map((n, k) => (
                <li key={k}>{n}</li>
              ))}
            </ol>
          </div>
          <div className="card wi-help">
            <details>
              <summary>Troubleshooting</summary>
              <ul>
                {g.trouble.map(([q, a]) => (
                  <li key={q}>
                    <b>{q}:</b> {a}
                  </li>
                ))}
              </ul>
            </details>
            {g.dev && (
              <details>
                <summary>Developer notes</summary>
                <div className="ig-dev">{g.dev}</div>
              </details>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

/** The clinic's own Cal.com: paste the API key (Cal.com → Settings → Developer → API keys). It is checked with
 * Cal.com and kept in Supabase Vault; it is never shown again. */
function CalcomConnect({
  clinicId,
  own,
  onDone,
}: {
  clinicId: string;
  own: boolean;
  onDone: (list: Integration[]) => void;
}) {
  const { toast } = useCrm();
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function send(method: "POST" | "DELETE") {
    setBusy(true);
    setError("");
    try {
      onDone(
        await api<Integration[]>(`/v1/crm/console/${clinicId}/integrations/calcom`, {
          method,
          body: method === "POST" ? JSON.stringify({ api_key: key }) : undefined,
        }),
      );
      setKey("");
      toast(method === "POST" ? "Cal.com connected" : "Cal.com disconnected");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not connect. Please try again.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="ig-block">
      <label className="ig-label">
        {own ? "Replace the API key" : "Cal.com API key"}
        <span className="sub2">Cal.com → Settings → Developer → API keys. Checked with Cal.com, then kept encrypted.</span>
      </label>
      <div className="row">
        <input
          className="f"
          type="password"
          autoComplete="off"
          style={{ flex: 1, minWidth: 200 }}
          placeholder="cal_live_…"
          value={key}
          maxLength={300}
          onChange={(e) => setKey(e.target.value)}
        />
        <button className="btn" disabled={busy || key.trim().length < 10} onClick={() => send("POST")}>
          {busy ? "Checking…" : own ? "Replace key" : "Connect"}
        </button>
        {own && (
          <button
            className="btn g"
            disabled={busy}
            onClick={() => {
              if (window.confirm("Disconnect the clinic's Cal.com? Online consults stop using it.")) void send("DELETE");
            }}
          >
            Disconnect
          </button>
        )}
      </div>
      {error && <p className="warnbox">{error}</p>}
      {own && <OnlineSetup clinicId={clinicId} />}
    </div>
  );
}
