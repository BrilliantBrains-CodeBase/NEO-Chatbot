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
  type FieldDef,
} from "./blocks";
import BlockSettings from "./BlockSettings";

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
  draft: { flow: Flow; services: { items: Service[] } };
  changed: boolean;
  flow_problems: Problem[];
};
type BlockData = { block: FlowNode; problems: number; services: Service[] };

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
      className={`wf-block${selected ? " on" : ""}${data.problems ? " bad" : ""}${b.enabled === false ? " off" : ""}`}
      style={{ borderTopColor: kind?.color }}
    >
      {b.type !== "opening" && b.type !== "typed" && (
        <Handle type="target" position={Position.Left} />
      )}
      <div className="wf-kind" style={{ color: kind?.color }}>
        {kind?.label ?? b.type}
        {data.problems > 0 && <span className="wf-bad">{data.problems}</span>}
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
          services: n.type === "treatment_list" ? services : NONE,
        },
        selected: n.id === selected,
        deletable: n.type !== "opening",
        measured: sizes[n.id],
      })),
    [flow, problems, selected, sizes, services],
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
        return { nodes, edges };
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
                  fields={[
                    ...BUILT_IN_FIELDS,
                    ...(flow.fields ?? []).map((f) => f.key),
                  ]}
                  onChange={setBlock}
                  onButtons={setButtons}
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
