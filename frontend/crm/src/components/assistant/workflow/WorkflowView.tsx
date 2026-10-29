"use client";

import "@xyflow/react/dist/style.css";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
} from "@xyflow/react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type DragEvent,
  useRef,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useCrm } from "@/components/crm/CrmProvider";
import { api, ApiError } from "@/lib/api";
import {
  arrange,
  buttonsOf,
  exitsOf,
  GROUPS,
  KINDS,
  looseEnds,
  newId,
  type Flow,
  type FlowButton,
  type FlowNode,
  type Problem,
  ACTION_TAG,
  pruneLines,
  BUILT_IN_FIELDS,
  DEFAULT_GLOBALS,
  type FieldDef,
  type FlowCheck,
  type Globals,
} from "./blocks";
import BlockSettings from "./BlockSettings";
import TestChat from "./TestChat";

// Dashboard → Menu buttons: the workflow canvas (like n8n). Blocks from the library on the left, lines from
// each button or exit to the next block, the selected block's settings on the right. One draft per clinic:
// Save keeps it, Publish makes it live (blocked while a button leads nowhere). Plan: WORKFLOW-CANVAS-PLAN.md.

export type Service = {
  name: string;
  category: string;
  price: number | null;
  show_price: boolean;
  show: boolean;
};
type Settings = {
  draft: {
    flow: Flow;
    services: { items: Service[] };
    chat?: { canvas: boolean }; // the chatbot runs on this canvas (after Publish)
  };
  published?: { chat?: { canvas: boolean } };
  changed: boolean;
  flow_problems: Problem[];
};
type BlockData = {
  block: FlowNode;
  problems: number;
  services: Service[];
  live: boolean; // the test chat is on this block
  typed: number; // approved typed phrases leading to its buttons (or to it, a Typed trigger)
};

function Block({ data, selected }: NodeProps<Node<BlockData>>) {
  const b = data.block;
  const kind = KINDS[b.type];
  const exits = exitsOf(b);
  const text = String(
    b.settings.message ??
      b.settings.text ??
      b.settings.welcome ??
      b.settings.treatment ??
      b.settings.doctor ??
      b.settings.topic ??
      b.settings.url ??
      b.settings.number ??
      "",
  );
  return (
    <div
      className={`wf-block${selected ? " on" : ""}${data.problems ? " bad" : ""}${b.enabled === false ? " off" : ""}${data.live ? " live-at" : ""}${b.type === "note" ? ` note ${String(b.settings.color ?? "yellow")}` : ""}`}
      style={{ borderTopColor: kind?.color }}
    >
      {b.type !== "opening" && b.type !== "typed" && b.type !== "note" && (
        <Handle type="target" position={Position.Left} />
      )}
      <div className="wf-kind" style={{ color: kind?.color }}>
        {kind?.label ?? b.type}
        {data.problems > 0 && <span className="wf-bad">{data.problems}</span>}
        {data.typed > 0 && (
          <span className="wf-state typed" title="Approved typed phrases">
            Typed: {data.typed}
          </span>
        )}
        {b.enabled === false ? (
          <span className="wf-state">OFF</span>
        ) : b.show_from || b.show_until || b.clinic_hours_only ? (
          <span className="wf-state sched">Scheduled</span>
        ) : null}
      </div>
      <b className="wf-title">{b.title || b.id}</b>
      {text && (
        <p className="wf-text">
          {text.length > 70 ? text.slice(0, 70) + "…" : text}
        </p>
      )}
      {b.settings.mode !== undefined && (
        <p className="wf-text">
          {b.settings.mode === "form" ? "Form" : "Step by step"}
        </p>
      )}
      {/* A treatment list's treatments, live from Clinic info → Services (each opens its card). */}
      {b.type === "treatment_list" &&
        data.services
          .filter((t) => t.show && t.category === b.settings.category)
          .map((t) => (
            <div key={t.name} className="wf-exit live">
              <span>{t.name}</span>
              <i className="wf-tag">
                {t.show_price && t.price != null
                  ? `₹${t.price.toLocaleString("en-IN")}`
                  : "card"}
              </i>
            </div>
          ))}
      {b.type === "treatment_list" && !b.settings.category && (
        <p className="wf-text">Choose a category in the settings.</p>
      )}
      {b.type === "doctor_card" &&
        String(b.settings.treatments_label ?? "") && (
          <div className="wf-exit live">
            <span>{String(b.settings.treatments_label)}</span>
            <i className="wf-tag">
              {((b.settings.treatments as string[]) ?? []).length} treatments
            </i>
          </div>
        )}
      {b.type === "faq" &&
        ((b.settings.items as { question: string }[]) ?? []).map((f, i) => (
          <div key={i} className="wf-exit live">
            <span>{f.question}</span>
            <i className="wf-tag">answer</i>
          </div>
        ))}
      {b.type === "media" && (
        <p className="wf-text">
          {String(b.settings.kind ?? "image")}:{" "}
          {String(b.settings.url ?? "").slice(0, 40)}
        </p>
      )}
      {b.type === "carousel" &&
        (b.settings.source === "custom"
          ? ((b.settings.cards as { title: string }[]) ?? []).map((c, i) => (
              <div key={i} className="wf-exit live">
                <span>{c.title || "Card"}</span>
                <i className="wf-tag">card</i>
              </div>
            ))
          : data.services
              .filter(
                (t) =>
                  t.show &&
                  (!b.settings.category || t.category === b.settings.category),
              )
              .map((t) => (
                <div key={t.name} className="wf-exit live">
                  <span>{t.name}</span>
                  <i className="wf-tag">card</i>
                </div>
              )))}
      {b.type === "goto" && (
        <p className="wf-text">
          → {String(b.settings.target || "choose a block")}
        </p>
      )}
      {(b.type === "location" || b.type === "reviews") && (
        <p className="wf-text">
          Live from Clinic info →{" "}
          {b.type === "location" ? "Contact & hours" : "Reviews"}
        </p>
      )}
      {/* Every button in order: one that leads on has a dot for its line; one that does its own job shows a tag. */}
      {buttonsOf(b).map((x) => (
        <div
          key={x.id}
          className={`wf-exit${x.visible === false ? " off" : ""}`}
        >
          <span>{x.label}</span>
          {x.action ? (
            <i className="wf-tag">{ACTION_TAG[x.action] ?? x.action}</i>
          ) : (
            <Handle type="source" position={Position.Right} id={x.id} />
          )}
        </div>
      ))}
      {exits
        .filter((x) => !buttonsOf(b).some((btn) => btn.id === x.id))
        .map((x) => (
          <div
            key={x.id}
            className={`wf-exit${x.id === "no_match" ? " soft" : ""}`}
          >
            <span>{x.label}</span>
            <Handle type="source" position={Position.Right} id={x.id} />
          </div>
        ))}
    </div>
  );
}
const NODE_TYPES = { block: Block };

export default function WorkflowView() {
  return (
    <ReactFlowProvider>
      <Canvas />
    </ReactFlowProvider>
  );
}

const noSubscription = () => () => {};
const FIT = { padding: 0.04, maxZoom: 1 };
const NONE: Service[] = [];
const DASHED = { strokeDasharray: "5 5", opacity: 0.5 };

function Canvas() {
  const { clinic, me, toast } = useCrm();
  const clinicId = me?.clinics.find((c) => c.name === clinic)?.id;
  const { screenToFlowPosition, fitView } = useReactFlow();
  const [loaded, setLoaded] = useState<{
    clinic: string;
    s?: Settings;
    error?: string;
  }>({ clinic: "" });
  const [flow, setFlow] = useState<Flow | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [liveAt, setLiveAt] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [find, setFind] = useState("");
  // React Flow measures each block and shows it only once its size is known (kept here, not in the flow).
  const [sizes, setSizes] = useState<
    Record<string, { width: number; height: number }>
  >({});
  // The canvas's buttons sit in the CRM's top bar (its empty middle), so the canvas gets the whole page.
  const slot = useSyncExternalStore(
    noSubscription,
    () => document.getElementById("tb-slot"),
    () => null,
  );
  const bar = (el: ReactNode) => (slot ? createPortal(el, slot) : el);
  const [side, setSide] = useState(false); // the right panel: a block's settings or the problems
  const box = useRef<HTMLDivElement>(null);
  // Show the whole workflow (the canvas waits for the blocks to be measured).
  const firstView = useCallback(() => void fitView(FIT), [fitView]);
  // Fit only once every block has been measured; fitting earlier leaves blocks off screen.
  // Fit once per loaded workflow; after that the zoom and position stay where the user put them.
  const measured = useNodesInitialized();
  const fitted = useRef("");
  useEffect(() => {
    const id = loaded.clinic + (loaded.s ? "|ok" : "");
    if (measured && loaded.s && fitted.current !== id) {
      fitted.current = id;
      firstView();
    }
  }, [measured, firstView, loaded]);

  useEffect(() => {
    if (!clinicId) return;
    let live = true;
    api<Settings>(`/v1/crm/console/${clinicId}/settings`).then(
      (s) => {
        if (!live) return;
        setLoaded({ clinic: clinicId, s });
        setSizes({});
        setFlow(s.draft.flow);
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
  const services = useMemo(() => s?.draft.services?.items ?? NONE, [s]);
  const dirty =
    !!s && !!flow && JSON.stringify(flow) !== JSON.stringify(s.draft.flow);
  const problems = useMemo<Problem[]>(
    () => (flow ? (dirty ? looseEnds(flow) : (s?.flow_problems ?? [])) : []),
    [flow, dirty, s],
  );
  const errors = problems.filter((p) => p.level === "error");

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const nodes = useMemo<Node<BlockData>[]>(
    () =>
      (flow?.nodes ?? []).map((n) => ({
        id: n.id,
        type: "block",
        position: { x: n.x, y: n.y },
        data: {
          block: n,
          problems: problems.filter((p) => p.node === n.id).length,
          services:
            n.type === "treatment_list" || n.type === "carousel"
              ? services
              : NONE,
          live: n.id === liveAt,
          typed: (flow?.phrases ?? []).filter(
            (p) =>
              p.status === "approved" &&
              (p.target === n.id || p.target.startsWith(n.id + ":")),
          ).length,
        },
        selected: n.id === selected,
        deletable: n.type !== "opening",
        measured: sizes[n.id],
      })),
    [flow, problems, selected, sizes, services, liveAt],
  );
  const edges = useMemo<Edge[]>(
    () =>
      (flow?.edges ?? []).map((e) => ({
        id: `${e.source}|${e.exit}`,
        source: e.source,
        sourceHandle: e.exit,
        target: e.target,
        // a line into an OFF block is dashed: that button is hidden from patients
        style:
          flow?.nodes.find((n) => n.id === e.target)?.enabled === false
            ? DASHED
            : undefined,
      })),
    [flow],
  );

  const onNodesChange = useCallback(
    (changes: NodeChange<Node<BlockData>>[]) => {
      setFlow((f) => {
        if (!f) return f;
        let nodes = f.nodes;
        let edges = f.edges;
        for (const c of changes) {
          if (c.type === "dimensions" && c.dimensions) {
            const d = c.dimensions;
            setSizes((z) =>
              z[c.id]?.width === d.width && z[c.id]?.height === d.height
                ? z
                : { ...z, [c.id]: d },
            );
          }
          if (c.type === "position" && c.position)
            nodes = nodes.map((n) =>
              n.id === c.id
                ? {
                    ...n,
                    x: Math.round(c.position!.x),
                    y: Math.round(c.position!.y),
                  }
                : n,
            );
          if (c.type === "remove") {
            nodes = nodes.filter((n) => n.id !== c.id || n.type === "opening");
            edges = edges.filter(
              (e) =>
                nodes.some((n) => n.id === e.source) &&
                nodes.some((n) => n.id === e.target),
            );
          }
          if (c.type === "select" && c.selected) setSelected(c.id);
        }
        // Keep the rest of the flow (phrases, checks, fields, settings); unchanged when only sizes or the
        // selection changed, so drawing the canvas never counts as an unsaved change.
        return nodes === f.nodes && edges === f.edges ? f : { ...f, nodes, edges };
      });
    },
    [],
  );
  const onEdgesDelete = useCallback((gone: Edge[]) => {
    const ids = new Set(gone.map((e) => e.id));
    setFlow((f) =>
      f
        ? {
            ...f,
            edges: f.edges.filter((e) => !ids.has(`${e.source}|${e.exit}`)),
          }
        : f,
    );
  }, []);
  const onConnect = useCallback((c: Connection) => {
    if (!c.source || !c.target || !c.sourceHandle || c.source === c.target)
      return;
    // One line per exit: a new line from the same exit replaces the old one.
    setFlow((f) =>
      f
        ? {
            ...f,
            edges: [
              ...f.edges.filter(
                (e) => !(e.source === c.source && e.exit === c.sourceHandle),
              ),
              { source: c.source!, exit: c.sourceHandle!, target: c.target! },
            ],
          }
        : f,
    );
  }, []);

  function addBlock(type: string, at?: { x: number; y: number }) {
    if (!flow) return;
    if (type === "opening" && flow.nodes.some((n) => n.type === "opening"))
      return toast("A flow has one Opening block.");
    const id = newId(flow, type);
    const pos = at ?? {
      x: 0,
      y: Math.max(0, ...flow.nodes.map((n) => n.y)) + 160,
    };
    setFlow({
      ...flow,
      nodes: [
        ...flow.nodes,
        {
          id,
          type,
          title: KINDS[type].label,
          x: Math.round(pos.x),
          y: Math.round(pos.y),
          settings: structuredClone(KINDS[type].start),
        },
      ],
    });
    setSelected(id);
  }
  // Copy / paste / duplicate one block: its settings, not its lines or typed phrases (a phrase leads to
  // one place only). Ctrl+C, Ctrl+V, Ctrl+D on the canvas (not while typing in a box).
  const clipboard = useRef<FlowNode | null>(null);
  function duplicate(source: FlowNode | null | undefined) {
    if (!flow || !source) return;
    if (source.type === "opening")
      return toast("A flow has one Opening block.");
    const id = newId(flow, source.type);
    setFlow({
      ...flow,
      nodes: [
        ...flow.nodes,
        {
          ...structuredClone(source),
          id,
          title:
            `${source.title || KINDS[source.type]?.label || source.type} (copy)`.slice(
              0,
              60,
            ),
          x: source.x + 40,
          y: source.y + 40,
        },
      ],
    });
    setSelected(id);
  }
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement;
      if (
        !(e.ctrlKey || e.metaKey) ||
        el.closest("input, textarea, select, [contenteditable]")
      )
        return;
      const k = e.key.toLowerCase();
      const current = flow?.nodes.find((n) => n.id === selected);
      if (k === "c" && current) {
        clipboard.current = structuredClone(current);
        toast("Block copied");
      } else if (k === "v" && clipboard.current) {
        duplicate(clipboard.current);
      } else if (k === "d" && current) {
        e.preventDefault();
        duplicate(current);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  function onDrop(e: DragEvent) {
    e.preventDefault();
    const type = e.dataTransfer.getData("application/x-block");
    if (KINDS[type])
      addBlock(type, screenToFlowPosition({ x: e.clientX, y: e.clientY }));
  }

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
      setSizes({}); // a new flow: React Flow measures its blocks again
      setFlow(next.draft.flow);
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
  if (!s || !flow) return <p className="sub2">Loading…</p>;
  const block = flow.nodes.find((n) => n.id === selected);
  const setBlock = (patch: Partial<FlowNode>) =>
    setFlow({
      ...flow,
      nodes: flow.nodes.map((n) =>
        n.id === selected ? { ...n, ...patch } : n,
      ),
    });
  // Removing a button also removes the line from it.
  const setButtons = (buttons: FlowButton[]) => {
    const keep = new Set(buttons.map((b) => b.id));
    setFlow({
      ...flow, // keep the phrases, checks, fields and settings
      nodes: flow.nodes.map((n) =>
        n.id === selected ? { ...n, settings: { ...n.settings, buttons } } : n,
      ),
      edges: flow.edges.filter(
        (e) =>
          e.source !== selected ||
          keep.has(e.exit) ||
          !buttonsOf(block!).some((b) => b.id === e.exit),
      ),
    });
  };

  return (
    <>
      {bar(
        <div className="row wf-actions">
          <button
            className={`badge ${errors.length ? "b-lo" : "b-vi"}`}
            style={{ border: 0, cursor: "pointer" }}
            title="Show the problems"
            onClick={() => {
              setSelected(null);
              setSide(!side || !!block);
            }}
          >
            {errors.length ? `${errors.length} to fix` : "No problems"}
          </button>
          <button
            className="pill"
            disabled={busy}
            onClick={() => {
              if (
                window.confirm(
                  "Replace this draft with a fresh one built from today's chat? Draft changes to the workflow are lost; the published one is kept.",
                )
              ) {
                void call(
                  "flow/rebuild",
                  "POST",
                  undefined,
                  "Rebuilt from today's chat",
                );
              }
            }}
          >
            Rebuild
          </button>
          <button className="pill" onClick={() => setFlow(arrange(flow))}>
            Auto-arrange
          </button>
          <button className="pill" onClick={() => setTesting((t) => !t)}>
            Test chat
          </button>
          <label
            className={`pill${s.draft.chat?.canvas ? " on" : ""}`}
            style={{ display: "inline-flex", gap: 6, alignItems: "center" }}
            title="On: patients get this canvas's buttons and flow (after Publish). Off: the chatbot as before."
          >
            <input
              type="checkbox"
              disabled={busy}
              checked={!!s.draft.chat?.canvas}
              onChange={(e) => {
                if (dirty) {
                  // Switching reloads the saved canvas, which would lose these edits.
                  toast("Save changes first, then switch.");
                  return;
                }
                void call(
                  "settings/chat",
                  "PUT",
                  { canvas: e.target.checked },
                  e.target.checked
                    ? "On: Publish to make the chatbot run on this canvas"
                    : "Off: Publish to go back to the chatbot as before",
                );
              }}
            />
            Chatbot runs on this canvas
            {s.published?.chat?.canvas ? " (live)" : " (not live)"}
          </label>
          <button
            className="pill"
            disabled={busy || !dirty}
            onClick={() =>
              call("settings/flow", "PUT", pruneLines(flow), "Draft saved")
            }
          >
            Save changes
          </button>
          <button
            className="btn"
            disabled={busy || dirty || !s.changed || errors.length > 0}
            onClick={() => call("publish", "POST", undefined, "Published")}
          >
            Publish
          </button>
        </div>,
      )}
      {error && <div className="warnbox">{error}</div>}
      {testing && clinicId && (
        <TestChat
          clinicId={clinicId}
          dirty={dirty}
          onAt={setLiveAt}
          onClose={() => setTesting(false)}
          onSaveCheck={(c) => {
            setFlow({ ...flow, checks: [...(flow.checks ?? []), c] });
            toast("Check added. Save changes to keep it.");
          }}
        />
      )}
      <div className={`wf${block || side ? "" : " no-side"}`}>
        <aside className="wf-lib">
          <input
            className="f"
            placeholder="Find a block"
            value={find}
            onChange={(e) => setFind(e.target.value)}
          />
          {GROUPS.map((g) => {
            const items = Object.entries(KINDS).filter(
              ([, k]) =>
                k.group === g &&
                (k.label + k.hint).toLowerCase().includes(find.toLowerCase()),
            );
            if (!items.length) return null;
            return (
              <div key={g}>
                <h4>{g}</h4>
                {items.map(([type, k]) => (
                  <button
                    key={type}
                    className="wf-item"
                    draggable
                    title={k.hint}
                    onDragStart={(e) =>
                      e.dataTransfer.setData("application/x-block", type)
                    }
                    onClick={() => addBlock(type)}
                    style={{ borderLeftColor: k.color }}
                  >
                    <b>{k.label}</b>
                    <span>{k.hint}</span>
                  </button>
                ))}
              </div>
            );
          })}
          <p className="sub2" style={{ fontSize: 11 }}>
            Drag a block onto the canvas, or click to add it. Drag from a dot on
            the right of a button to the next block. Select a line or block and
            press Delete to remove it.
          </p>
        </aside>
        <div
          ref={box}
          className="wf-canvas"
          onDragOver={(e) => e.preventDefault()}
          onDrop={onDrop}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={NODE_TYPES}
            onNodesChange={onNodesChange}
            onEdgesDelete={onEdgesDelete}
            onConnect={onConnect}
            onPaneClick={() => setSelected(null)}
            minZoom={0.15}
            deleteKeyCode={["Delete", "Backspace"]}
          >
            <Background gap={20} />
            <MiniMap
              pannable
              zoomable
              nodeColor={(n) =>
                KINDS[(n.data as BlockData).block.type]?.color ?? "#999"
              }
            />
            <Controls />
          </ReactFlow>
        </div>
        {(block || side) && (
          <aside className="wf-side">
            <button
              className="wf-close"
              aria-label="Close"
              onClick={() => {
                setSelected(null);
                setSide(false);
              }}
            >
              ✕
            </button>
            {block ? (
              <>
                <BlockSettings
                  key={block.id}
                  block={block}
                  clinicId={clinicId}
                  services={services}
                  blocks={flow.nodes}
                  fields={[
                    ...BUILT_IN_FIELDS,
                    ...(flow.fields ?? []).map((f) => f.key),
                  ]}
                  onChange={setBlock}
                  onButtons={setButtons}
                  phrases={flow.phrases ?? []}
                  onPhrases={(phrases) => setFlow({ ...flow, phrases })}
                  onApprove={(ids) =>
                    call(
                      "flow/phrases/approve",
                      "POST",
                      { ids },
                      "Phrases approved",
                    )
                  }
                  dirty={dirty}
                />
                <div className="wf-save">
                  <button
                    className="btn"
                    disabled={busy || !dirty}
                    onClick={() =>
                      call(
                        "settings/flow",
                        "PUT",
                        pruneLines(flow),
                        "Draft saved",
                      )
                    }
                  >
                    {dirty ? "Save changes" : "Saved"}
                  </button>
                  {block.type !== "opening" && (
                    <button
                      className="pill"
                      title="Ctrl+D. A copy has no lines and no typed phrases."
                      onClick={() => duplicate(block)}
                    >
                      Duplicate
                    </button>
                  )}
                </div>
              </>
            ) : (
              <>
                <h3 style={{ marginTop: 0 }}>Problems</h3>
                {problems.length === 0 && (
                  <p className="sub2">None. Every button leads somewhere.</p>
                )}
                {problems.map((p, i) => (
                  <button
                    key={i}
                    className="wf-problem"
                    onClick={() => setSelected(p.node)}
                  >
                    <span
                      className={`badge ${p.level === "error" ? "b-lo" : "b-fu"}`}
                    >
                      {p.level === "error" ? "Fix" : "Note"}
                    </span>
                    <span>
                      <b>
                        {flow.nodes.find((n) => n.id === p.node)?.title ||
                          p.node}
                      </b>{" "}
                      · {p.message}
                    </span>
                  </button>
                ))}
                <FieldsPanel
                  fields={flow.fields ?? []}
                  onChange={(fields) => setFlow({ ...flow, fields })}
                />
                <div style={{ marginTop: 14 }}>
                  <h3 style={{ margin: "0 0 6px" }}>Typed phrases</h3>
                  <p
                    className="sub2"
                    style={{ margin: "0 0 6px", fontSize: 11.5 }}
                  >
                    {
                      (flow.phrases ?? []).filter(
                        (p) => p.status === "approved",
                      ).length
                    }{" "}
                    approved,{" "}
                    {
                      (flow.phrases ?? []).filter((p) => p.status === "pending")
                        .length
                    }{" "}
                    pending.
                  </p>
                  <button
                    className="pill"
                    disabled={busy || dirty}
                    title={
                      dirty
                        ? "Save changes first"
                        : "Adds the phrases staff approved for the live chat; existing ones are not changed"
                    }
                    onClick={() =>
                      call(
                        "flow/phrases/import-live",
                        "POST",
                        undefined,
                        "Live chat phrases imported",
                      )
                    }
                  >
                    Import live chat phrases
                  </button>
                </div>
                <ChecksPanel
                  clinicId={clinicId}
                  checks={flow.checks ?? []}
                  dirty={dirty}
                  onChange={(checks) => setFlow({ ...flow, checks })}
                />
                <GlobalsPanel
                  globals={flow.globals ?? DEFAULT_GLOBALS}
                  blocks={flow.nodes}
                  onChange={(globals) => setFlow({ ...flow, globals })}
                />
                <p className="sub2" style={{ marginTop: 12 }}>
                  {flow.nodes.length} blocks · {flow.edges.length} lines. Click
                  a block to edit it.
                </p>
              </>
            )}
          </aside>
        )}
      </div>
    </>
  );
}

/** Publish checks: saved test chats, replayed on the draft; all must pass before Publish. */
function ChecksPanel({
  clinicId,
  checks,
  dirty,
  onChange,
}: {
  clinicId: string | undefined;
  checks: FlowCheck[];
  dirty: boolean;
  onChange: (c: FlowCheck[]) => void;
}) {
  const [results, setResults] = useState<
    { name: string; ok: boolean; message: string }[] | null
  >(null);
  const [err, setErr] = useState("");
  return (
    <div style={{ marginTop: 14 }}>
      <h3 style={{ margin: "0 0 6px" }}>Publish checks</h3>
      {!checks.length && (
        <p className="sub2" style={{ margin: 0, fontSize: 11.5 }}>
          None yet. In the test chat, click &quot;Save as a check&quot; after a
          good run.
        </p>
      )}
      {checks.map((c, i) => {
        const r = results?.[i];
        return (
          <div key={i} className="wf-btn" style={{ fontSize: 12.5 }}>
            {r && (
              <span className={`badge ${r.ok ? "b-vi" : "b-in"}`}>
                {r.ok ? "Pass" : "Fail"}
              </span>
            )}
            <b style={{ flex: 1 }}>
              {c.name}{" "}
              <span className="sub2">
                {r && !r.ok
                  ? r.message
                  : `${c.steps.length} steps → ${c.expect_at}`}
              </span>
            </b>
            <button
              aria-label="Remove"
              onClick={() => {
                setResults(null);
                onChange(checks.filter((_, k) => k !== i));
              }}
            >
              ✕
            </button>
          </div>
        );
      })}
      {!!checks.length && (
        <button
          className="pill"
          style={{ marginTop: 6 }}
          disabled={dirty || !clinicId}
          title={
            dirty ? "Save changes first: checks run on the saved draft" : ""
          }
          onClick={async () => {
            setErr("");
            try {
              setResults(
                await api(`/v1/crm/console/${clinicId}/flow/checks`, {
                  method: "POST",
                }),
              );
            } catch (e) {
              setErr(
                e instanceof ApiError ? e.message : "Could not run the checks.",
              );
            }
          }}
        >
          Run checks
        </button>
      )}
      {err && <p className="warnbox">{err}</p>}
      <p className="sub2" style={{ margin: "4px 0 0", fontSize: 11 }}>
        They run as if the clinic is open at 11 AM.
      </p>
      <TestSets clinicId={clinicId} dirty={dirty} />
    </div>
  );
}

type SetResult = {
  name: string;
  total: number;
  passed: number;
  bar: number; // Publish needs at least this
  failures: {
    message: string;
    expected: string;
    got: string;
    word: string;
    reply: string;
  }[];
};

/** The clinic's typed-message test sets, sent to the saved draft: the score and what failed. */
function TestSets({
  clinicId,
  dirty,
}: {
  clinicId: string | undefined;
  dirty: boolean;
}) {
  const [sets, setSets] = useState<SetResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [err, setErr] = useState("");
  return (
    <div style={{ marginTop: 10 }}>
      <button
        className="pill"
        disabled={busy || dirty || !clinicId}
        title={dirty ? "Save changes first" : ""}
        onClick={async () => {
          setBusy(true);
          setErr("");
          try {
            setSets(
              await api<SetResult[]>(
                `/v1/crm/console/${clinicId}/flow/test-sets`,
                { method: "POST" },
              ),
            );
          } catch (e) {
            setErr(
              e instanceof ApiError
                ? e.message
                : "Could not run the test sets.",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Running test sets… (about a minute)" : "Run test sets"}
      </button>
      {err && <p className="warnbox">{err}</p>}
      {sets && !sets.length && (
        <p className="sub2" style={{ fontSize: 11.5 }}>
          This clinic has no test sets yet.
        </p>
      )}
      {sets?.map((s) => (
        <div key={s.name} style={{ marginTop: 6, fontSize: 12.5 }}>
          <button
            className="wf-btn"
            style={{ width: "100%", textAlign: "left", cursor: "pointer" }}
            onClick={() => setOpen(open === s.name ? null : s.name)}
          >
            <span className={`badge ${s.passed >= s.bar ? "b-vi" : "b-in"}`}>
              {s.passed}/{s.total}
            </span>
            <b style={{ flex: 1 }}>
              {s.name}{" "}
              {s.bar > 0 && (
                <span className="sub2">
                  {s.passed >= s.bar
                    ? "· publish OK"
                    : `· below the bar (${s.bar})`}
                </span>
              )}
            </b>
            {s.failures.length > 0 && (open === s.name ? "▾" : "▸")}
          </button>
          {open === s.name &&
            s.failures.map((f, i) => (
              <p
                key={i}
                className="sub2"
                style={{ margin: "3px 0 0 8px", fontSize: 11.5 }}
              >
                “{f.message}” — expected {f.expected}
                {f.word ? ` with “${f.word}”` : ""}, got {f.got}
                {f.reply ? `: ${f.reply.slice(0, 90)}` : ""}
              </p>
            ))}
        </div>
      ))}
    </div>
  );
}

const TRIGGER_LABEL: Record<string, string> = {
  main_menu: "Main menu",
  start_again: "Start again (clears the fields)",
  talk_to_person: "Get a call back (to your Call back block)",
  emergency: "Emergency",
};

/** Whole flow: the no-reply reminder and the triggers that work from anywhere (typed or tapped). */
function GlobalsPanel({
  globals,
  blocks,
  onChange,
}: {
  globals: Globals;
  blocks: FlowNode[];
  onChange: (g: Globals) => void;
}) {
  const nr = globals.no_reply;
  const setNr = (patch: Partial<Globals["no_reply"]>) =>
    onChange({ ...globals, no_reply: { ...nr, ...patch } });
  return (
    <div style={{ marginTop: 14 }}>
      <h3 style={{ margin: "0 0 6px" }}>Whole flow</h3>
      <label className="wf-btn" style={{ fontSize: 12.5 }}>
        <input
          type="checkbox"
          checked={nr.enabled}
          onChange={(e) => setNr({ enabled: e.target.checked })}
        />
        No reply: remind after
        <select
          value={nr.minutes}
          onChange={(e) => setNr({ minutes: Number(e.target.value) })}
        >
          {[1, 2, 3, 5, 10, 15, 30].map((m) => (
            <option key={m} value={m}>
              {m} min
            </option>
          ))}
        </select>
        <select
          value={nr.reminders}
          onChange={(e) => setNr({ reminders: Number(e.target.value) })}
        >
          <option value={1}>once</option>
          <option value={2}>twice</option>
        </select>
      </label>
      {nr.enabled && (
        <textarea
          rows={2}
          maxLength={300}
          style={{ width: "100%" }}
          value={nr.message}
          onChange={(e) => setNr({ message: e.target.value })}
        />
      )}
      <label className="wf-btn" style={{ fontSize: 12.5 }}>
        <input
          type="checkbox"
          checked={(globals.request_stage ?? "follow_up") === "follow_up"}
          onChange={(e) =>
            onChange({
              ...globals,
              request_stage: e.target.checked ? "follow_up" : "new",
            })
          }
        />
        A booking request moves the lead to Follow Up
      </label>
      <label className="wf-btn" style={{ fontSize: 12.5 }}>
        <input
          type="checkbox"
          checked={globals.emergency_alert !== false}
          onChange={(e) =>
            onChange({ ...globals, emergency_alert: e.target.checked })
          }
        />
        Emergency alerts the staff (urgent call back in the Inbox, email to the
        manager)
      </label>
      <p className="sub2" style={{ margin: "8px 0 4px", fontSize: 11.5 }}>
        Work from anywhere in the chat, typed or tapped:
      </p>
      {globals.triggers.map((t, i) => (
        <div key={t.kind} className="wf-btn" style={{ fontSize: 12.5 }}>
          <input
            type="checkbox"
            checked={t.enabled}
            onChange={(e) =>
              onChange({
                ...globals,
                triggers: globals.triggers.map((x, k) =>
                  k === i ? { ...x, enabled: e.target.checked } : x,
                ),
              })
            }
          />
          <b style={{ flex: 1 }}>{TRIGGER_LABEL[t.kind]}</b>
          <select
            value={t.target}
            onChange={(e) =>
              onChange({
                ...globals,
                triggers: globals.triggers.map((x, k) =>
                  k === i ? { ...x, target: e.target.value } : x,
                ),
              })
            }
          >
            <option value="">
              {t.kind === "main_menu" || t.kind === "start_again"
                ? "Opening"
                : "Choose a block…"}
            </option>
            {blocks
              .filter((b) => b.type !== "opening")
              .map((b) => (
                <option key={b.id} value={b.id}>
                  {b.title || b.id}
                </option>
              ))}
          </select>
        </div>
      ))}
    </div>
  );
}

/** The clinic's own fields (beside the built-in ones), used in messages as {key} and by Set field blocks. */
function FieldsPanel({
  fields,
  onChange,
}: {
  fields: FieldDef[];
  onChange: (f: FieldDef[]) => void;
}) {
  const [key, setKey] = useState("");
  const [label, setLabel] = useState("");
  const ok =
    /^[a-z][a-z0-9_]{1,29}$/.test(key) &&
    !BUILT_IN_FIELDS.includes(key) &&
    !fields.some((f) => f.key === key);
  return (
    <div style={{ marginTop: 14 }}>
      <h3 style={{ margin: "0 0 6px" }}>Fields</h3>
      <p className="sub2" style={{ margin: "0 0 6px", fontSize: 11.5 }}>
        Built in: {BUILT_IN_FIELDS.map((f) => `{${f}}`).join(" ")}
      </p>
      {fields.map((f) => (
        <div key={f.key} className="wf-btn" style={{ fontSize: 12.5 }}>
          <b style={{ flex: 1 }}>
            {`{${f.key}}`} <span className="sub2">{f.label}</span>
          </b>
          <button
            aria-label="Remove"
            onClick={() => onChange(fields.filter((x) => x.key !== f.key))}
          >
            ✕
          </button>
        </div>
      ))}
      <div className="wf-btn" style={{ marginTop: 6 }}>
        <input
          placeholder="key, e.g. interest"
          value={key}
          onChange={(e) =>
            setKey(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))
          }
        />
        <input
          placeholder="Label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <button
          className="pill"
          disabled={!ok || !label.trim()}
          onClick={() => {
            onChange([...fields, { key, label: label.trim(), kind: "text" }]);
            setKey("");
            setLabel("");
          }}
        >
          Add
        </button>
      </div>
    </div>
  );
}
