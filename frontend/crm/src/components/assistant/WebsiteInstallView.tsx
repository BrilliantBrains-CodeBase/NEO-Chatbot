"use client";

import Loading from "@/components/crm/Loading";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useCrm } from "@/components/crm/CrmProvider";

// Dashboard → Website install: the websites the clinic's chatbot may run on. A site is added as pending and
// the chat runs only on approved ones (any other site is refused). Approve / reject: Clinic Manager or BB Admin.

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

const BADGE = { pending: "b-fu", approved: "b-vi", rejected: "b-in" } as const;
const LABEL = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
} as const;

export default function WebsiteInstallView() {
  const { clinic, me, toast } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const [sites, setSites] = useState<{ clinic: string; list: Site[] } | null>(
    null,
  );
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Site[]>(`/v1/crm/console/${clinicId}/websites`).then(
      (list) => live && setSites({ clinic: clinicId, list }),
      (e) =>
        live &&
        setError(
          e instanceof ApiError ? e.message : "Could not load the websites.",
        ),
    );
    return () => {
      live = false;
    };
  }, [clinicId]);

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
      const list = await api<Site[]>(
        `/v1/crm/console/${clinicId}/websites${path}`,
        {
          method,
          body: body ? JSON.stringify(body) : undefined,
        },
      );
      setSites({ clinic: clinicId, list });
      if (done) toast(done);
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

  const list = sites && sites.clinic === clinicId ? sites.list : null;
  return (
    <div className="page" style={{ maxWidth: 820 }}>
      <h2 style={{ margin: "0 0 4px" }}>Website install</h2>
      <p className="sub2" style={{ margin: "0 0 14px" }}>
        The chatbot runs only on approved websites; any other site is refused.
        Add the clinic&apos;s website, approve it, then copy the code.
      </p>
      {error && <div className="warnbox">{error}</div>}
      <div
        className="card"
        style={{ display: "flex", gap: 8, marginBottom: 14 }}
      >
        <input
          className="f"
          style={{ flex: 1 }}
          placeholder="https://neofollicle.com"
          value={address}
          maxLength={200}
          onChange={(e) => setAddress(e.target.value)}
        />
        <button
          className="btn"
          disabled={busy || address.trim().length < 4}
          onClick={async () => {
            if (
              await call(
                "",
                "POST",
                { address },
                "Website added: waiting for approval",
              )
            )
              setAddress("");
          }}
        >
          Add website
        </button>
      </div>
      {list === null && !error && <Loading />}
      {list?.length === 0 && <p className="sub2">No websites yet.</p>}
      {list?.map((s) => (
        <div key={s.id} className="card" style={{ marginBottom: 10 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            <span className={`badge ${BADGE[s.status]}`}>
              {LABEL[s.status]}
            </span>
            <b style={{ flex: 1, wordBreak: "break-all" }}>{s.origin}</b>
            {s.status !== "approved" && (
              <button
                className="btn"
                disabled={busy}
                onClick={() =>
                  call(
                    `/${s.id}/decision`,
                    "POST",
                    { status: "approved" },
                    "Approved: the chatbot can run there",
                  )
                }
              >
                Approve
              </button>
            )}
            {s.status !== "rejected" && (
              <button
                className="btn g"
                disabled={busy}
                onClick={() =>
                  call(
                    `/${s.id}/decision`,
                    "POST",
                    { status: "rejected" },
                    "Rejected: the chatbot is refused there",
                  )
                }
              >
                Reject
              </button>
            )}
            {s.status === "approved" && (
              <CheckInstall clinicId={clinicId} site={s.id} />
            )}
            <button
              className="btn g"
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    `Remove ${s.origin}? The chatbot stops running there.`,
                  )
                )
                  void call(`/${s.id}`, "DELETE", undefined, "Website removed");
              }}
            >
              Remove
            </button>
          </div>
          <p className="sub2" style={{ margin: "6px 0 0", fontSize: "var(--fs-small)" }}>
            {s.added_by
              ? `Added by ${s.added_by}`
              : "Allowed before the Dashboard"}
            {s.decided_at &&
              ` · ${LABEL[s.status]}${s.decided_by ? ` by ${s.decided_by}` : ""} on ${new Date(s.decided_at).toLocaleDateString("en-IN")}`}
          </p>
          <Pages
            site={s}
            busy={busy}
            onSave={(p) => call(`/${s.id}/pages`, "PUT", p, "Pages saved")}
          />
          {s.status === "approved" && (
            <label
              className="row"
              style={{ gap: 6, marginTop: 8, fontSize: "var(--fs-sec)", cursor: "pointer" }}
            >
              <input
                type="checkbox"
                disabled={busy}
                checked={s.capture_forms}
                onChange={(e) =>
                  call(
                    `/${s.id}/capture`,
                    "PUT",
                    { on: e.target.checked },
                    e.target.checked
                      ? "This site's forms now come in as leads"
                      : "Form capture off",
                  )
                }
              />
              Also send this site&apos;s own forms to the CRM as leads
              <span className="sub2">
                (any form with a phone or email; passwords and card fields are
                never sent)
              </span>
            </label>
          )}
        </div>
      ))}
      {list && clinicId && <EmbedCode clinicId={clinicId} sites={list} />}
    </div>
  );
}

/** The one line to paste on the clinic's website(s), with each added site and whether the chat runs there. */
function EmbedCode({ clinicId, sites }: { clinicId: string; sites: Site[] }) {
  const { toast } = useCrm();
  const [embed, setEmbed] = useState<{ clinic: string; code: string } | null>(
    null,
  );
  useEffect(() => {
    let live = true;
    api<{ code: string }>(`/v1/crm/console/${clinicId}/websites/embed`).then(
      (e) => live && setEmbed({ clinic: clinicId, code: e.code }),
      () => {},
    );
    return () => {
      live = false;
    };
  }, [clinicId]);
  const code = embed?.clinic === clinicId ? embed.code : "";
  return (
    <div className="card" style={{ marginTop: 6 }}>
      <h3 style={{ margin: "0 0 6px" }}>Widget code</h3>
      {!sites.length ? (
        <p className="sub2" style={{ margin: 0 }}>
          Add the clinic&apos;s website above to get the code.
        </p>
      ) : !code ? (
        <p className="sub2" style={{ margin: 0 }}>
          This clinic has no widget yet.
        </p>
      ) : (
        <>
          <p className="sub2" style={{ margin: "0 0 6px", fontSize: "var(--fs-small)" }}>
            Paste this just before <code>&lt;/body&gt;</code> on:
          </p>
          <ul style={{ margin: "0 0 6px", paddingLeft: 18, fontSize: "var(--fs-small)" }}>
            {sites.map((s) => (
              <li key={s.id}>
                {s.origin}{" "}
                <span className={`badge ${BADGE[s.status]}`}>
                  {s.status === "approved"
                    ? "the chatbot runs here"
                    : s.status === "pending"
                      ? "approve it first"
                      : "rejected: refused"}
                </span>
              </li>
            ))}
          </ul>
          <p className="sub2" style={{ margin: "0 0 6px", fontSize: "var(--fs-small)" }}>
            On any website that is not approved, the chatbot is refused.
          </p>
          <textarea
            readOnly
            rows={2}
            value={code}
            style={{
              width: "100%",
              fontFamily: "ui-monospace, monospace",
              fontSize: "var(--fs-small)",
            }}
            onFocus={(e) => e.target.select()}
          />
          <button
            className="btn"
            style={{ marginTop: 6 }}
            onClick={() =>
              navigator.clipboard.writeText(code).then(
                () => toast("Widget code copied"),
                () => toast("Select the code and copy it"),
              )
            }
          >
            Copy code
          </button>
        </>
      )}
    </div>
  );
}

/** Looks for the widget code on the approved website's home page. */
function CheckInstall({
  clinicId,
  site,
}: {
  clinicId: string | undefined;
  site: string;
}) {
  const [result, setResult] = useState<{
    found: boolean;
    message: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <button
        className="btn g"
        disabled={busy || !clinicId}
        onClick={async () => {
          setBusy(true);
          try {
            setResult(
              await api(`/v1/crm/console/${clinicId}/websites/${site}/check`, {
                method: "POST",
              }),
            );
          } catch (e) {
            setResult({
              found: false,
              message: e instanceof ApiError ? e.message : "Could not check.",
            });
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Checking…" : "Check install"}
      </button>
      {result && (
        <span
          className={`badge ${result.found ? "b-vi" : "b-in"}`}
          title={result.message}
        >
          {result.found ? "Installed" : "Not found"}
        </span>
      )}
      {result && !result.found && (
        <p
          className="sub2"
          style={{ width: "100%", margin: "4px 0 0", fontSize: "var(--fs-small)" }}
        >
          {result.message}
        </p>
      )}
    </>
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
  const changed =
    mode !== site.pages_mode || text.trim() !== site.pages.join("\n");
  return (
    <div
      style={{
        marginTop: 8,
        display: "flex",
        flexDirection: "column",
        gap: 6,
        fontSize: "var(--fs-sec)",
      }}
    >
      <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
        Show the chatbot on
        <select
          className="sel"
          value={mode}
          onChange={(e) => setMode(e.target.value as Site["pages_mode"])}
        >
          <option value="all">every page</option>
          <option value="only">only these pages</option>
          <option value="except">every page except these</option>
        </select>
      </label>
      {mode !== "all" && (
        <textarea
          rows={3}
          placeholder={"/hair-transplant/*\n/contact"}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      )}
      {changed && (
        <button
          className="btn"
          style={{ alignSelf: "flex-start" }}
          disabled={busy}
          onClick={() =>
            onSave({
              pages_mode: mode,
              pages: mode === "all" ? [] : text.split("\n"),
            })
          }
        >
          Save pages
        </button>
      )}
    </div>
  );
}
