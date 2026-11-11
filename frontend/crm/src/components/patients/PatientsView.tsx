"use client";

import Loading from "@/components/crm/Loading";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useCrm } from "@/components/crm/CrmProvider";
import Pager from "@/components/crm/Pager";
import AddLeadForm from "@/components/leads/AddLeadForm";
import { ConfirmDelete } from "@/components/leads/DeleteLeads";
import {
  SOURCE,
  STAGE_LABEL,
  useDebounced,
} from "@/components/leads/LeadsView";
import { level } from "@/lib/access";
import {
  api,
  apiBlob,
  ApiError,
  REFRESH_MS,
  saveFile,
  type PatientList,
} from "@/lib/api";

const PAGE_SIZE = 30;

const SOURCES: Record<string, string> = {
  ...SOURCE,
  walk_in: "Walk-in",
  phone_call: "Phone call",
  referral: "Referral",
};
// How regular someone is. The wording of each rule is shown on the tab, so staff can see what it means.
const ACTIVITY: [string, string, string, string][] = [
  ["never", "Never visited", "No visit yet", "b-new"],
  ["new", "New", "1 visit", "b-fu"],
  ["returning", "Returning", "2 visits", "b-bk"],
  ["regular", "Regular", "3 or more visits", "b-vi"],
  ["inactive", "Inactive", "No visit in 6 months", "b-in"],
];
const DATE_FIELDS: [string, string][] = [
  ["added", "Date added"],
  ["contact", "Last contact"],
  ["first_visit", "First visit"],
  ["last_visit", "Last visit"],
  ["next_visit", "Next appointment"],
];
const PRESETS: [string, number | null][] = [
  ["All", null],
  ["Last 7 days", 7],
  ["Last 15 days", 15],
  ["Last 30 days", 30],
];

type Sort = { by: string; dir: "asc" | "desc" };
const NEWEST: Sort = { by: "added", dir: "desc" };

const ymd = (d: Date) => d.toLocaleDateString("en-CA"); // YYYY-MM-DD, the browser's day
const day = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "—";

function Select({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: ReactNode;
}) {
  return (
    <select
      className="sel"
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{label}</option>
      {children}
    </select>
  );
}

export default function PatientsView() {
  const { clinic, me, toast, openModal, closeModal } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const router = useRouter();
  const canOpen = level(me, clinic, "leads") !== "hidden"; // a row opens its lead
  const canAdd = level(me, clinic, "leads") === "edit"; // Add patient, as the top bar's Add lead
  // Tick patients to export, assign or delete them: Clinic Managers and Super Admin (as on Leads).
  const canBulk =
    !!clinicId &&
    (!!me?.bb_admin ||
      me?.clinics.find((c) => c.id === clinicId)?.role === "clinic_manager");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [assignTo, setAssignTo] = useState("");
  const [working, setWorking] = useState(false);
  const [version, setVersion] = useState(0); // bumped after a change, to load the list again

  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  const [activity, setActivity] = useState("");
  const [stage, setStage] = useState("");
  const [source, setSource] = useState("");
  const [campaign, setCampaign] = useState("");
  const [treatment, setTreatment] = useState("");
  const [doctor, setDoctor] = useState("");
  const [assigned, setAssigned] = useState("");
  const [noShows, setNoShows] = useState("");
  const [upcoming, setUpcoming] = useState("");
  const [consent, setConsent] = useState("");
  const [visitsMin, setVisitsMin] = useState("");
  const [visitsMax, setVisitsMax] = useState("");
  const [dateField, setDateField] = useState("added");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [preset, setPreset] = useState<number | null | "custom">(null);
  const [sort, setSort] = useState<Sort>(NEWEST);
  const [page, setPage] = useState(1);

  const shown = new URLSearchParams();
  const put = (key: string, value: string) => {
    if (value) shown.set(key, value);
  };
  put("q", q);
  put("activity", activity);
  put("stage", stage);
  put("source", source);
  put("campaign", campaign);
  put("treatment", treatment);
  put("doctor", doctor);
  put("assigned", assigned);
  put("no_shows", noShows);
  put("upcoming", upcoming);
  put("consent", consent);
  put("visits_min", visitsMin);
  put("visits_max", visitsMax);
  put("from", from);
  put("to", to);
  if (from || to) shown.set("date_field", dateField);
  const filterQuery = shown.toString();

  // New filters or a new order: back to the first page.
  const filters = `${clinicId}|${filterQuery}|${sort.by}|${sort.dir}`;
  const [seenFilters, setSeenFilters] = useState(filters);
  if (filters !== seenFilters) {
    setSeenFilters(filters);
    setPage(1);
  }
  const key = `${filters}|${page}|${version}`;
  const listUrl = `/v1/crm/patients?clinic=${clinicId}&sort=${sort.by}&direction=${sort.dir}&limit=${PAGE_SIZE}&offset=${(page - 1) * PAGE_SIZE}&${filterQuery}`;
  const [list, setList] = useState<{
    key: string;
    d?: PatientList;
    error?: string;
  }>({ key: "" });
  // The last list stays on screen while the next one loads, so the tabs and drop-downs do not flicker.
  const [last, setLast] = useState<PatientList | undefined>();

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<PatientList>(listUrl).then(
      (d) => {
        if (!live) return;
        setList({ key, d });
        setLast(d);
      },
      (e) =>
        live &&
        setList({
          key,
          error: e instanceof ApiError ? e.message : "Could not load patients.",
        }),
    );
    return () => {
      live = false;
    };
  }, [clinicId, listUrl, key]);

  // Quietly, without "Loading…": the same list again while the tab is in view.
  useEffect(() => {
    if (!clinicId) return;
    const timer = setInterval(() => {
      if (document.hidden) return;
      api<PatientList>(listUrl).then(
        (d) => setList((now) => (now.key === key ? { key, d } : now)),
        () => {},
      );
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [clinicId, listUrl, key]);

  const d = list.key === key ? list.d : undefined;
  const error = list.key === key ? list.error : undefined;
  const opts = d ?? last;
  const pages = d ? Math.max(1, Math.ceil(d.total / PAGE_SIZE)) : 1;
  if (d && page > pages) setPage(pages);
  const everyone = opts?.activities.reduce((n, a) => n + a.count, 0);

  function range(days: number | null) {
    setPreset(days);
    if (days === null) {
      setFrom("");
      setTo("");
      return;
    }
    const start = new Date();
    start.setDate(start.getDate() - (days - 1));
    setFrom(ymd(start));
    setTo(ymd(new Date()));
  }

  function clearAll() {
    setSearch("");
    setActivity("");
    setStage("");
    setSource("");
    setCampaign("");
    setTreatment("");
    setDoctor("");
    setAssigned("");
    setNoShows("");
    setUpcoming("");
    setConsent("");
    setVisitsMin("");
    setVisitsMax("");
    setDateField("added");
    range(null);
    setSort(NEWEST);
  }

  function goPage(n: number) {
    setPage(n);
    document.querySelector(".crm .page")?.scrollTo(0, 0);
  }

  // Dates open newest first and names A to Z; a second click turns the order round.
  function sortBy(by: string) {
    setSort((s) =>
      s.by === by
        ? { by, dir: s.dir === "asc" ? "desc" : "asc" }
        : { by, dir: by === "name" ? "asc" : "desc" },
    );
  }
  const head = (by: string, label: string) => (
    <th
      aria-sort={
        sort.by === by
          ? sort.dir === "asc"
            ? "ascending"
            : "descending"
          : "none"
      }
    >
      <button
        type="button"
        className={`sortb${sort.by === by ? " on" : ""}`}
        onClick={() => sortBy(by)}
      >
        {label}
        <span aria-hidden="true">
          {sort.by === by ? (sort.dir === "asc" ? " ↑" : " ↓") : ""}
        </span>
      </button>
    </th>
  );

  const COLUMNS = canBulk ? 11 : 10;
  const onPage = d?.items.map((x) => x.code) ?? [];
  const pageTicked = onPage.length > 0 && onPage.every((c) => picked.has(c));
  const tick = (code: string, on: boolean) => {
    const next = new Set(picked);
    if (on) next.add(code);
    else next.delete(code);
    setPicked(next);
  };
  const reload = () => {
    setPicked(new Set());
    setVersion((v) => v + 1);
  };

  async function exportPicked() {
    setWorking(true);
    try {
      const file = await apiBlob("/v1/crm/leads/export", {
        method: "POST",
        body: JSON.stringify({ clinic: clinicId, codes: [...picked] }),
      });
      saveFile(
        file,
        `patients-${clinicId}-${new Date().toLocaleDateString("en-CA")}.csv`,
      );
      toast("Patients exported");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not export.");
    } finally {
      setWorking(false);
    }
  }

  async function assignPicked() {
    if (!assignTo) return;
    setWorking(true);
    let failed = 0;
    for (const code of picked) {
      try {
        await api(`/v1/crm/leads/${encodeURIComponent(code)}`, {
          method: "PATCH",
          body: JSON.stringify({ assigned_to: assignTo }),
        });
      } catch {
        failed += 1;
      }
    }
    const name = opts?.owners?.find((x) => x.id === assignTo)?.name ?? "them";
    toast(
      failed
        ? `Assigned ${picked.size - failed}; ${failed} could not be`
        : `Assigned to ${name}`,
    );
    setWorking(false);
    setAssignTo("");
    reload();
  }

  return (
    <>
      <div className="ph">
        <div>
          <h1>Patients</h1>
          <p>
            Everyone who has contacted the clinic, visited or not. One record
            per phone number.
          </p>
        </div>
        {canAdd && clinicId && (
          <button
            className="btn"
            onClick={() =>
              openModal({
                title: "Add patient",
                body: (
                  <AddLeadForm
                    clinicId={clinicId}
                    onDone={() => {
                      closeModal();
                      reload();
                    }}
                  />
                ),
              })
            }
          >
            + Add patient
          </button>
        )}
      </div>
      <div className="tabs">
        <button
          className={activity ? "" : "on"}
          onClick={() => setActivity("")}
        >
          All<span className="c">{everyone ?? "…"}</span>
        </button>
        {ACTIVITY.map(([k, label, rule]) => (
          <button
            key={k}
            className={activity === k ? "on" : ""}
            title={rule}
            onClick={() => setActivity(k)}
          >
            {label}
            <span className="c">
              {opts?.activities.find((a) => a.key === k)?.count ?? "…"}
            </span>
          </button>
        ))}
      </div>
      <div className="tools">
        <label className="search">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, phone, treatment, email or code"
          />
        </label>
        <select
          className="sel"
          aria-label="Which date"
          value={dateField}
          onChange={(e) => setDateField(e.target.value)}
        >
          {DATE_FIELDS.map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
        <div className="pills" style={{ margin: 0 }} aria-label="Date range">
          {PRESETS.map(([label, days]) => (
            <button
              key={label}
              type="button"
              className={`pill${preset === days ? " on" : ""}`}
              onClick={() => range(days)}
            >
              {label}
            </button>
          ))}
        </div>
        <input
          className="sel"
          type="date"
          aria-label="From"
          value={from}
          max={to || undefined}
          onChange={(e) => {
            setFrom(e.target.value);
            setPreset("custom");
          }}
        />
        <span className="sub2">to</span>
        <input
          className="sel"
          type="date"
          aria-label="To"
          value={to}
          min={from || undefined}
          onChange={(e) => {
            setTo(e.target.value);
            setPreset("custom");
          }}
        />
      </div>
      <div className="tools">
        <Select label="All stages" value={stage} onChange={setStage}>
          {Object.entries(STAGE_LABEL).map(([k, [label]]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </Select>
        <Select label="All sources" value={source} onChange={setSource}>
          {Object.entries(SOURCES).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
        <Select label="All campaigns" value={campaign} onChange={setCampaign}>
          {opts?.campaigns.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
        <Select
          label="All treatments"
          value={treatment}
          onChange={setTreatment}
        >
          {opts?.treatments.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
        <Select label="All doctors" value={doctor} onChange={setDoctor}>
          {opts?.doctors.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </Select>
        <Select
          label="Assigned to anyone"
          value={assigned}
          onChange={setAssigned}
        >
          <option value="none">Unassigned</option>
          {opts?.staff.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </Select>
        <Select label="No-shows: any" value={noShows} onChange={setNoShows}>
          <option value="yes">Has no-shows</option>
          <option value="no">No no-shows</option>
        </Select>
        <Select
          label="Next appointment: any"
          value={upcoming}
          onChange={setUpcoming}
        >
          <option value="yes">Has one booked</option>
          <option value="no">Nothing booked</option>
        </Select>
        <Select label="Consent: any" value={consent} onChange={setConsent}>
          <option value="yes">Agreed to contact</option>
          <option value="no">No consent recorded</option>
        </Select>
        <span className="sub2">Visits</span>
        <input
          className="sel"
          style={{ width: 72 }}
          type="number"
          min={0}
          aria-label="Visits from"
          placeholder="From"
          value={visitsMin}
          onChange={(e) => setVisitsMin(e.target.value)}
        />
        <input
          className="sel"
          style={{ width: 72 }}
          type="number"
          min={0}
          aria-label="Visits to"
          placeholder="To"
          value={visitsMax}
          onChange={(e) => setVisitsMax(e.target.value)}
        />
        <button type="button" className="btn g sm" onClick={clearAll}>
          Clear filters
        </button>
      </div>
      {error && <div className="warnbox">{error}</div>}
      {canBulk && picked.size > 0 && (
        <div className="pills" style={{ alignItems: "center" }}>
          <b>
            {picked.size} patient{picked.size === 1 ? "" : "s"} selected
          </b>
          <button
            type="button"
            className="btn g sm"
            disabled={working}
            onClick={exportPicked}
          >
            Export
          </button>
          <select
            className="sel"
            aria-label="Assign to"
            value={assignTo}
            disabled={working}
            onChange={(e) => setAssignTo(e.target.value)}
          >
            <option value="">Assign to…</option>
            {(opts?.owners ?? []).map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn g sm"
            disabled={working || !assignTo}
            onClick={assignPicked}
          >
            Assign
          </button>
          <button
            type="button"
            className="btn g sm"
            style={{ color: "var(--err)" }}
            disabled={working || picked.size > 200}
            onClick={() =>
              openModal({
                title: "Delete patients",
                body: (
                  <ConfirmDelete
                    clinicId={clinicId!}
                    codes={[...picked]}
                    label={
                      picked.size === 1
                        ? [...picked][0]
                        : `${picked.size} patients`
                    }
                    onDone={reload}
                  />
                ),
              })
            }
          >
            Delete selected
          </button>
          <button
            type="button"
            className="btn g sm"
            disabled={working}
            onClick={() => setPicked(new Set())}
          >
            Clear
          </button>
        </div>
      )}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              {canBulk && (
                <th style={{ width: 36 }}>
                  <input
                    type="checkbox"
                    aria-label="Select all patients on this page"
                    checked={pageTicked}
                    onChange={(e) =>
                      setPicked(
                        e.target.checked
                          ? new Set([...picked, ...onPage])
                          : new Set(
                              [...picked].filter((c) => !onPage.includes(c)),
                            ),
                      )
                    }
                  />
                </th>
              )}
              {head("name", "Patient")}
              <th>Source</th>
              <th>Treatment</th>
              <th>Stage</th>
              <th>Status</th>
              {head("visits", "Visits")}
              {head("first_visit", "First visit")}
              {head("last_visit", "Last visit")}
              {head("next_visit", "Next")}
              {head("added", "Added")}
            </tr>
          </thead>
          <tbody>
            {!d && !error && (
              <tr>
                <td colSpan={COLUMNS}>
                  <Loading />
                </td>
              </tr>
            )}
            {d && !d.items.length && (
              <tr>
                <td colSpan={COLUMNS}>No patients match.</td>
              </tr>
            )}
            {d?.items.map((p) => {
              const tag = ACTIVITY.find(([k]) => k === p.activity);
              return (
                <tr
                  key={p.code}
                  style={canOpen ? undefined : { cursor: "default" }}
                  onClick={() => {
                    if (canOpen)
                      router.push(`/leads?open=${encodeURIComponent(p.code)}`);
                  }}
                >
                  {canBulk && (
                    <td
                      style={{ cursor: "default" }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        aria-label={`Select ${p.name}`}
                        checked={picked.has(p.code)}
                        onChange={(e) => tick(p.code, e.target.checked)}
                      />
                    </td>
                  )}
                  <td>
                    <div className="nm">{p.name}</div>
                    <div className="pn">
                      {p.code} · {p.phone ?? p.email}
                    </div>
                  </td>
                  <td>
                    {SOURCES[p.source] ?? p.source}
                    {p.campaign && <div className="pn">{p.campaign}</div>}
                  </td>
                  <td>
                    {p.treatment ?? "—"}
                    {p.doctor && <div className="pn">{p.doctor}</div>}
                  </td>
                  <td>
                    <span className={`badge ${STAGE_LABEL[p.stage]?.[1]}`}>
                      {STAGE_LABEL[p.stage]?.[0] ?? p.stage}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${tag?.[3]}`} title={tag?.[2]}>
                      {tag?.[1] ?? p.activity}
                    </span>
                  </td>
                  <td>
                    {p.visits}
                    {p.no_shows > 0 && (
                      <div className="pn">
                        {p.no_shows} no-show{p.no_shows === 1 ? "" : "s"}
                      </div>
                    )}
                  </td>
                  <td>{day(p.first_visit)}</td>
                  <td>{day(p.last_visit)}</td>
                  <td>{day(p.next_visit)}</td>
                  <td>{day(p.created_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {d && d.total > 0 && (
        <Pager
          page={page}
          size={PAGE_SIZE}
          shown={d.items.length}
          total={d.total}
          onPage={goPage}
        />
      )}
    </>
  );
}
