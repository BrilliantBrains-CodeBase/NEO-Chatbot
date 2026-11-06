"use client";

import Loading from "@/components/crm/Loading";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";

// Chatbot → Website install: the websites the clinic's chatbot may run on, the one line of code to paste, how
// to paste it on each kind of website, and whether it is there. A site is added as pending; the chat runs only
// on approved ones (any other site is refused). Approve / reject: Admin or Super Admin.

type Site = {
  id: string;
  origin: string;
  status: "pending" | "approved" | "rejected";
  pages_mode: "all" | "only" | "except";
  pages: string[];
  capture_forms: boolean;
  added_by: string | null;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
};
type Check = { busy: boolean; found?: boolean; message?: string };

const host = (origin: string) => origin.replace(/^https?:\/\//, "").replace(/\/$/, "");
const day = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

export default function WebsiteInstallView() {
  const { clinic, me, toast } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const [sites, setSites] = useState<{ clinic: string; list: Site[] } | null>(null);
  const [embed, setEmbed] = useState<{ clinic: string; code: string } | null>(null);
  const [checks, setChecks] = useState<Record<string, Check>>({});
  const [adding, setAdding] = useState(false);
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const check = useCallback(
    async (site: string) => {
      if (!clinicId) return;
      setChecks((c) => ({ ...c, [site]: { ...c[site], busy: true } }));
      try {
        const r = await api<{ found: boolean; message: string }>(
          `/v1/crm/console/${clinicId}/websites/${site}/check`,
          { method: "POST" },
        );
        setChecks((c) => ({ ...c, [site]: { busy: false, ...r } }));
      } catch (e) {
        const message = e instanceof ApiError ? e.message : "Could not check.";
        setChecks((c) => ({ ...c, [site]: { busy: false, found: false, message } }));
      }
    },
    [clinicId],
  );

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Site[]>(`/v1/crm/console/${clinicId}/websites`).then(
      (list) => {
        if (!live) return;
        setSites({ clinic: clinicId, list });
        list.filter((s) => s.status === "approved").forEach((s) => void check(s.id)); // is it live?
      },
      (e) => live && setError(e instanceof ApiError ? e.message : "Could not load the websites."),
    );
    api<{ code: string }>(`/v1/crm/console/${clinicId}/websites/embed`).then(
      (e) => live && setEmbed({ clinic: clinicId, code: e.code }),
      () => {},
    );
    return () => {
      live = false;
    };
  }, [clinicId, check]);

  async function call(path: string, method: string, body?: object, done?: string) {
    if (!clinicId) return false;
    setBusy(true);
    setError("");
    try {
      const list = await api<Site[]>(`/v1/crm/console/${clinicId}/websites${path}`, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      });
      setSites({ clinic: clinicId, list });
      if (done) toast(done);
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save. Please try again.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  function copy(text: string) {
    navigator.clipboard.writeText(text).then(
      () => {
        setCopied(true);
        toast("Install code copied");
        setTimeout(() => setCopied(false), 2500);
      },
      () => toast("Select the code and copy it"),
    );
  }

  const list = sites && sites.clinic === clinicId ? sites.list : null;
  const code = embed && embed.clinic === clinicId ? embed.code : "";
  const approved = list?.filter((s) => s.status === "approved") ?? [];
  const liveCount = approved.filter((s) => checks[s.id]?.found).length;
  const steps: [string, boolean][] = [
    ["Add website", !!list?.length],
    ["Approve it", approved.length > 0],
    ["Paste the code", liveCount > 0 || copied],
    ["Verify", liveCount > 0],
  ];
  const current = steps.findIndex(([, done]) => !done);

  return (
    <div className="wi">
      <div className="ph">
        <div>
          <h1>Website install</h1>
          <p>Put your chatbot on the clinic&apos;s website: add the site, approve it, paste one line of code.</p>
        </div>
        {list && (
          <span className={`wi-pill ${liveCount ? "live" : approved.length ? "wait" : "off"}`}>
            <i />
            {liveCount
              ? `Live on ${liveCount} of ${approved.length} approved site${approved.length === 1 ? "" : "s"}`
              : approved.length
                ? "Approved, not installed yet"
                : "Not set up yet"}
          </span>
        )}
      </div>

      <ol className="wi-steps" aria-label="Setup progress">
        {steps.map(([label, done], i) => (
          <li key={label} className={done ? "done" : i === current ? "now" : ""}>
            <span>{done ? "✓" : i + 1}</span>
            {label}
          </li>
        ))}
      </ol>

      {error && <div className="warnbox">{error}</div>}

      <div className="wi-grid">
        <section className="wi-col">
          <div className="wi-col-h">
            <h3>Your websites</h3>
            {!adding && (
              <button className="btn sm" onClick={() => setAdding(true)}>
                + Add website
              </button>
            )}
          </div>
          {adding && (
            <form
              className="card wi-add"
              onSubmit={async (e) => {
                e.preventDefault();
                if (await call("", "POST", { address }, "Website added: approve it to switch the chatbot on")) {
                  setAddress("");
                  setAdding(false);
                }
              }}
            >
              <label>
                Website address
                <input
                  className="f"
                  autoFocus
                  placeholder="https://yourclinic.com"
                  value={address}
                  maxLength={200}
                  onChange={(e) => setAddress(e.target.value)}
                />
              </label>
              <p className="sub2">
                The whole site counts, with or without www. Add a staging or test site separately if you use one.
              </p>
              <div className="row">
                <button className="btn" disabled={busy || address.trim().length < 4}>
                  Add website
                </button>
                <button type="button" className="btn g" onClick={() => setAdding(false)}>
                  Cancel
                </button>
              </div>
            </form>
          )}
          {list === null && !error && <Loading />}
          {list?.length === 0 && !adding && (
            <div className="card wi-empty">
              <b>No website yet</b>
              <span className="sub2">Add the clinic&apos;s website to get its install code.</span>
              <button className="btn" onClick={() => setAdding(true)}>
                + Add website
              </button>
            </div>
          )}
          {list?.map((s) => (
            <SiteCard
              key={s.id}
              site={s}
              busy={busy}
              check={checks[s.id]}
              onCheck={() => check(s.id)}
              call={call}
            />
          ))}
        </section>

        <section className="wi-col">
          <div className="card wi-code">
            <div className="wi-col-h">
              <h3>Install code</h3>
              {code && (
                <button className={`btn sm${copied ? " g" : ""}`} onClick={() => copy(code)}>
                  {copied ? "Copied ✓" : "Copy code"}
                </button>
              )}
            </div>
            {!code ? (
              <p className="sub2">{list?.length ? "This clinic has no widget yet." : "Add a website to get the code."}</p>
            ) : (
              <>
                <pre className="wi-pre" onClick={() => copy(code)} title="Click to copy">
                  <code>{code}</code>
                </pre>
                <ul className="wi-facts">
                  <li>Paste it once, just before the closing <code>&lt;/body&gt;</code> tag, on every page (or in the shared footer).</li>
                  <li>The same code for every approved site. It only runs on approved ones.</li>
                </ul>
              </>
            )}
          </div>
          {code && <Guides code={code} />}
          {code && <Help code={code} />}
        </section>
      </div>
    </div>
  );
}

function SiteCard({
  site: s,
  busy,
  check,
  onCheck,
  call,
}: {
  site: Site;
  busy: boolean;
  check: Check | undefined;
  onCheck: () => void;
  call: (path: string, method: string, body?: object, done?: string) => Promise<boolean>;
}) {
  const [pagesOpen, setPagesOpen] = useState(false);
  const live = s.status === "approved" && check?.found;
  const pill =
    s.status === "pending"
      ? ["wait", "Waiting for approval"]
      : s.status === "rejected"
        ? ["off", "Rejected: chatbot refused"]
        : check?.busy
          ? ["wait", "Checking…"]
          : live
            ? ["live", "Live"]
            : check
              ? ["warn", "Approved · code not found"]
              : ["wait", "Approved"];
  const where =
    s.pages_mode === "all"
      ? "Every page"
      : `${s.pages_mode === "only" ? "Only" : "All except"} ${s.pages.length} page${s.pages.length === 1 ? "" : "s"}`;
  return (
    <article className={`card wi-site ${s.status}`}>
      <div className="wi-site-h">
        <span className="wi-avatar" aria-hidden="true">
          {host(s.origin).charAt(0).toUpperCase()}
        </span>
        <div className="wi-site-t">
          <a href={s.origin} target="_blank" rel="noreferrer">
            {host(s.origin)}
          </a>
          <span className="sub2">
            {where}
            {s.status === "approved" && ` · Forms → leads ${s.capture_forms ? "on" : "off"}`}
          </span>
        </div>
        <span className={`wi-pill ${pill[0]}`}>
          <i />
          {pill[1]}
        </span>
      </div>

      {s.status === "approved" && check && !check.busy && !check.found && check.message && (
        <p className="wi-note">{check.message}</p>
      )}

      <div className="wi-actions">
        {s.status !== "approved" && (
          <button
            className="btn sm"
            disabled={busy}
            onClick={() => call(`/${s.id}/decision`, "POST", { status: "approved" }, "Approved: the chatbot can run there")}
          >
            Approve
          </button>
        )}
        {s.status === "pending" && (
          <button
            className="btn g sm"
            disabled={busy}
            onClick={() => call(`/${s.id}/decision`, "POST", { status: "rejected" }, "Rejected: the chatbot is refused there")}
          >
            Reject
          </button>
        )}
        {s.status === "approved" && (
          <button className="btn g sm" disabled={check?.busy} onClick={onCheck}>
            {check?.busy ? "Checking…" : "Check install"}
          </button>
        )}
        <button className="btn g sm" onClick={() => setPagesOpen(!pagesOpen)} aria-expanded={pagesOpen}>
          Pages
        </button>
        {s.status === "approved" && (
          <label className="wi-switch">
            <input
              type="checkbox"
              disabled={busy}
              checked={s.capture_forms}
              onChange={(e) =>
                call(
                  `/${s.id}/capture`,
                  "PUT",
                  { on: e.target.checked },
                  e.target.checked ? "This site's forms now come in as leads" : "Form capture off",
                )
              }
            />
            <span />
            Forms → leads
          </label>
        )}
        <details className="wi-more">
          <summary aria-label="More actions">⋯</summary>
          <div>
            {s.status === "approved" && (
              <button
                disabled={busy}
                onClick={() =>
                  call(`/${s.id}/decision`, "POST", { status: "rejected" }, "Rejected: the chatbot is refused there")
                }
              >
                Stop the chatbot here (reject)
              </button>
            )}
            <button
              className="danger"
              disabled={busy}
              onClick={() => {
                if (window.confirm(`Remove ${host(s.origin)}? The chatbot stops running there.`))
                  void call(`/${s.id}`, "DELETE", undefined, "Website removed");
              }}
            >
              Remove website
            </button>
          </div>
        </details>
      </div>

      {pagesOpen && (
        <Pages
          site={s}
          busy={busy}
          onSave={async (p) => {
            if (await call(`/${s.id}/pages`, "PUT", p, "Pages saved")) setPagesOpen(false);
          }}
        />
      )}
      {s.status === "approved" && s.capture_forms && (
        <p className="sub2 wi-small">
          The site&apos;s own forms (any with a phone or email) also arrive in the Inbox. Password and card fields are
          never sent.
        </p>
      )}
      <p className="sub2 wi-small">
        {s.added_by ? `Added by ${s.added_by}` : "Added during setup"}
        {s.decided_at && ` · ${s.status === "approved" ? "Approved" : s.status === "rejected" ? "Rejected" : "Decided"}`}
        {s.decided_at && s.decided_by && ` by ${s.decided_by}`}
        {s.decided_at && ` on ${day(s.decided_at)}`}
      </p>
    </article>
  );
}

/** Where on the site the bot shows: every page, only these paths, or every page except these. */
function Pages({
  site,
  busy,
  onSave,
}: {
  site: Site;
  busy: boolean;
  onSave: (p: { pages_mode: string; pages: string[] }) => void;
}) {
  const [mode, setMode] = useState(site.pages_mode);
  const [text, setText] = useState(site.pages.join("\n"));
  const changed = mode !== site.pages_mode || text.trim() !== site.pages.join("\n");
  return (
    <div className="wi-pages">
      <div className="seg" role="radiogroup" aria-label="Show the chatbot on">
        {(
          [
            ["all", "Every page"],
            ["only", "Only these pages"],
            ["except", "All except these"],
          ] as const
        ).map(([k, label]) => (
          <button key={k} type="button" className={mode === k ? "on" : ""} onClick={() => setMode(k)}>
            {label}
          </button>
        ))}
      </div>
      {mode !== "all" && (
        <>
          <textarea
            className="f"
            rows={3}
            placeholder={"/contact\n/treatments/*"}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <span className="sub2">
            One path per line. <code>*</code> matches anything: <code>/treatments/*</code> covers every treatment page.
          </span>
        </>
      )}
      <div className="row">
        <button
          className="btn sm"
          disabled={busy || !changed}
          onClick={() => onSave({ pages_mode: mode, pages: mode === "all" ? [] : text.split("\n") })}
        >
          Save pages
        </button>
      </div>
    </div>
  );
}

/** Step-by-step guides for the common website builders, with the clinic's own code. */
function Guides({ code }: { code: string }) {
  const { toast } = useCrm();
  const src = code.match(/src="([^"]+)"/)?.[1] ?? "";
  const clinic = code.match(/data-clinic="([^"]+)"/)?.[1];
  const next = `import Script from "next/script";\n\n// In app/layout.tsx, inside <body>:\n<Script src="${src}"${clinic ? ` data-clinic="${clinic}"` : ""} strategy="afterInteractive" />`;
  const GUIDES: [string, ReactNode[], string?][] = [
    [
      "HTML",
      [
        "Open the template or footer file that every page shares (often footer.html, footer.php or a layout file).",
        <>Paste the code on the line just before <code>&lt;/body&gt;</code>.</>,
        "Upload or deploy the site, then press Check install.",
      ],
    ],
    [
      "WordPress",
      [
        <>Easiest: install the free <b>WPCode</b> plugin (Insert Headers and Footers), open <b>Code Snippets → Header &amp; Footer</b>, paste the code in <b>Footer</b> and save.</>,
        <>Elementor Pro: <b>Elementor → Custom Code</b>, location <b>&lt;/body&gt; - End</b>, publish.</>,
        <>Or in a child theme: <b>Appearance → Theme File Editor → footer.php</b>, paste before <code>&lt;/body&gt;</code>.</>,
        "Clear any caching plugin (WP Rocket, LiteSpeed…), then Check install.",
      ],
    ],
    [
      "Wix",
      [
        <><b>Settings → Custom code</b> (under Advanced) → <b>+ Add Custom Code</b>.</>,
        <>Paste the code, choose <b>All pages</b> and <b>Load code once</b>.</>,
        <>Place code in <b>Body - end</b>, then Apply. (Needs a Premium plan with a connected domain.)</>,
      ],
    ],
    [
      "Shopify",
      [
        <><b>Online Store → Themes → ⋯ → Edit code</b>.</>,
        <>Open <b>layout/theme.liquid</b> and paste the code just before <code>&lt;/body&gt;</code>.</>,
        "Save, then Check install.",
      ],
    ],
    [
      "Webflow",
      [
        <><b>Site settings → Custom code → Footer code</b>.</>,
        "Paste the code, save, and Publish the site. (Custom code needs a paid site plan.)",
      ],
    ],
    [
      "Squarespace",
      [
        <><b>Settings → Advanced → Code Injection</b> (or Website → Pages → Custom code).</>,
        <>Paste the code in <b>Footer</b> and save. (Needs a Business plan or higher.)</>,
      ],
    ],
    [
      "Tag Manager",
      [
        <>In Google Tag Manager: <b>Tags → New → Custom HTML</b>, paste the code.</>,
        <>Trigger: <b>All Pages</b>. Save, then <b>Submit → Publish</b>.</>,
        "Check install reads the page's own HTML, so it shows “not found” for a Tag Manager install. Open the site to see the chat button instead.",
      ],
    ],
    [
      "React / Next.js",
      [
        <>Next.js: add the <code>Script</code> below to the root layout, inside <code>&lt;body&gt;</code>.</>,
        <>Vite or Create React App: paste the code in <code>index.html</code> just before <code>&lt;/body&gt;</code>.</>,
        "Page rules (Pages) are applied on full page loads; moving between pages inside the app keeps the chat as it is.",
      ],
      next,
    ],
  ];
  const [tab, setTab] = useState(0);
  const [, steps, snippet] = GUIDES[tab];
  return (
    <div className="card wi-guides">
      <h3>How to install</h3>
      <div className="wi-tabs" role="tablist">
        {GUIDES.map(([name], i) => (
          <button key={name} role="tab" aria-selected={tab === i} className={tab === i ? "on" : ""} onClick={() => setTab(i)}>
            {name}
          </button>
        ))}
      </div>
      <ol className="wi-howto">
        {steps.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ol>
      {snippet && (
        <pre
          className="wi-pre"
          title="Click to copy"
          onClick={() =>
            navigator.clipboard.writeText(snippet).then(
              () => toast("Copied"),
              () => {},
            )
          }
        >
          <code>{snippet}</code>
        </pre>
      )}
    </div>
  );
}

/** Troubleshooting and the notes a website developer needs. */
function Help({ code }: { code: string }) {
  const src = code.match(/src="([^"]+)"/)?.[1] ?? "";
  let backend = "";
  try {
    backend = src ? new URL(src).origin : "";
  } catch {
    backend = "";
  }
  return (
    <div className="card wi-help">
      <details>
        <summary>Troubleshooting</summary>
        <ul>
          <li>
            <b>“Code not found” after pasting:</b> publish or redeploy the site, then clear its cache (caching plugin,
            Cloudflare or other CDN) and check again. The check looks at the home page.
          </li>
          <li>
            <b>Installed with Google Tag Manager:</b> the check cannot see code added by Tag Manager. Open the site: if
            the chat button shows, it works.
          </li>
          <li>
            <b>The chat button does not show:</b> the site must be Approved here, the page must be allowed under Pages,
            and the chatbot must be switched on (Chatbot → Appearance → Enabled).
          </li>
          <li>
            <b>www or not:</b> <code>yourclinic.com</code> and <code>www.yourclinic.com</code> count as the same site. A
            different domain or a staging site needs its own entry.
          </li>
          <li>
            <b>Security headers:</b> a site with a strict <code>Content-Security-Policy</code> must allow{" "}
            <code>{backend || "the chatbot's address"}</code> in <code>script-src</code>, <code>connect-src</code> and{" "}
            <code>img-src</code>.
          </li>
        </ul>
      </details>
      <details>
        <summary>Developer notes</summary>
        <ul>
          <li>
            The script loads with <code>defer</code> (it never blocks the page) and is under 5 KB; the full chat loads
            only when a visitor first opens it.
          </li>
          <li>
            It draws inside its own Shadow DOM, so the site&apos;s CSS and the chat&apos;s styles never affect each
            other. Nothing else is added to the page.
          </li>
          <li>
            Settings on the script tag: <code>data-clinic</code> (which clinic, for the shared loader) and{" "}
            <code>data-api</code> (only to point at a different chatbot server; normally left out).
          </li>
          <li>
            The chatbot runs only on approved websites: the server checks every request&apos;s origin. On any other
            site, or on a page excluded under Pages, nothing shows.
          </li>
          <li>
            In the visitor&apos;s browser it keeps a visitor id, a session id and the visitor&apos;s own recent chat (for
            up to 3 days), in local storage. No cookies are set.
          </li>
          <li>
            With “Forms → leads” on, forms on the page that have a phone or email are also sent as leads. Password and
            card fields are never read.
          </li>
          <li>Paste the code once per page; a second copy is ignored.</li>
        </ul>
      </details>
    </div>
  );
}
