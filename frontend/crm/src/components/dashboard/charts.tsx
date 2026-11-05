"use client";

import { useLayoutEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

// The Dashboard's charts, drawn as SVG (no chart library). One look everywhere: 2px lines, a 10% area wash,
// hairline grid, values in ink (never in the series colour), a crosshair tooltip on hover and on the arrow
// keys, and every chart readable as a table. Colours are the --s1..--s8 and status tokens in crm.css.

/** A box's width in px, kept up to date (0 before the first measure). */
export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const watch = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)));
    watch.observe(el);
    return () => watch.disconnect();
  }, []);
  return [ref, width] as const;
}

export const num = (n: number) => n.toLocaleString("en-IN");
export const dayLabel = (iso: string, long = false) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-IN", long ? { weekday: "short", day: "numeric", month: "short" } : { day: "numeric", month: "short" });

/** Round axis steps: 0, 5, 10, 15 … (whole numbers only: these are counts). */
function axis(max: number): number[] {
  if (max <= 0) return [0, 1];
  const raw = max / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = Math.max(1, [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10);
  const top = Math.ceil(max / step) * step;
  return Array.from({ length: top / step + 1 }, (_, i) => i * step);
}

export type Series = { key: string; label: string; values: number[]; color: string; area?: boolean };

/** Lines over days with a crosshair. The first series with `area` gets the wash. */
export function LineChart({ days, series, height = 230, label }: { days: string[]; series: Series[]; height?: number; label: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [at, setAt] = useState<number | null>(null);
  const n = days.length;
  const L = 36, R = 12, T = 12, B = 26; // prettier-ignore
  const ticks = axis(Math.max(0, ...series.flatMap((s) => s.values)));
  const top = ticks[ticks.length - 1];
  const w = Math.max(0, width - L - R);
  const h = height - T - B;
  const x = (i: number) => L + (n <= 1 ? w / 2 : (i * w) / (n - 1));
  const y = (v: number) => T + h - (v / top) * h;
  const path = (vs: number[]) => vs.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const labelEvery = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(w / 64))));

  const pick = (e: PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const i = n <= 1 ? 0 : Math.round(((e.clientX - box.left - L) / w) * (n - 1));
    setAt(Math.min(n - 1, Math.max(0, i)));
  };
  const keys = (e: KeyboardEvent) => {
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      const step = e.key === "ArrowLeft" ? -1 : 1;
      setAt((i) => Math.min(n - 1, Math.max(0, (i ?? n - 1) + (i === null ? 0 : step))));
    } else if (e.key === "Escape") setAt(null);
  };
  const tipLeft = at === null ? 0 : Math.min(Math.max(x(at) - 80, 0), Math.max(0, width - 170));

  return (
    <div
      ref={ref}
      className="ch-wrap"
      tabIndex={0}
      aria-label={`${label}. Use the left and right arrow keys to read each day.`}
      onKeyDown={keys}
      onFocus={() => setAt((i) => i ?? n - 1)}
      onBlur={() => setAt(null)}
    >
      {width > 0 && (
        <svg width={width} height={height} aria-hidden onPointerMove={pick} onPointerLeave={() => setAt(null)}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={L} x2={L + w} y1={y(t)} y2={y(t)} className={t === 0 ? "ch-base" : "ch-grid"} />
              <text x={L - 8} y={y(t)} dy="0.32em" textAnchor="end" className="ch-tick">
                {num(t)}
              </text>
            </g>
          ))}
          {days.map(
            (d, i) =>
              (i === n - 1 || (i % labelEvery === 0 && n - 1 - i >= labelEvery / 2)) && (
                <text key={d} x={x(i)} y={height - 6} textAnchor={n > 1 && i === n - 1 ? "end" : n > 1 && i === 0 ? "start" : "middle"} className="ch-tick">
                  {dayLabel(d)}
                </text>
              ),
          )}
          {series.map(
            (s) =>
              s.area && (
                <path key={s.key + "-a"} d={`${path(s.values)}L${x(n - 1)},${y(0)}L${x(0)},${y(0)}Z`} fill={s.color} opacity={0.1} />
              ),
          )}
          {[...series].reverse().map((s) => (
            <path key={s.key} d={path(s.values)} stroke={s.color} className="ch-line" />
          ))}
          {n > 0 &&
            series.map((s) => (
              <circle key={s.key + "-end"} cx={x(n - 1)} cy={y(s.values[n - 1])} r={4} fill={s.color} className="ch-dot" />
            ))}
          {at !== null && (
            <g>
              <line x1={x(at)} x2={x(at)} y1={T} y2={T + h} className="ch-cross" />
              {series.map((s) => (
                <circle key={s.key} cx={x(at)} cy={y(s.values[at])} r={5} fill={s.color} className="ch-dot" />
              ))}
            </g>
          )}
        </svg>
      )}
      {at !== null && (
        <div className="ch-tip" style={{ left: tipLeft }} role="status">
          <div className="ch-tip-h">{dayLabel(days[at], true)}</div>
          {series.map((s) => (
            <div key={s.key} className="ch-tip-r">
              <i style={{ background: s.color }} />
              <b>{num(s.values[at])}</b>
              <span>{s.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** A small trend line for a stat tile: one hue, the last day marked. No axis, no hover (the tile has the number). */
export function Sparkline({ values, color = "var(--s1)" }: { values: number[]; color?: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const height = 34;
  const max = Math.max(1, ...values);
  const n = values.length;
  const x = (i: number) => 4 + (n <= 1 ? 0 : (i * (width - 8)) / (n - 1));
  const y = (v: number) => 4 + (height - 8) * (1 - v / max);
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  return (
    <div ref={ref} className="ch-spark" aria-hidden>
      {width > 0 && n > 0 && (
        <svg width={width} height={height}>
          <path d={`${d}L${x(n - 1)},${height}L${x(0)},${height}Z`} fill={color} opacity={0.1} />
          <path d={d} stroke={color} className="ch-line" />
          <circle cx={x(n - 1)} cy={y(values[n - 1])} r={3.5} fill={color} className="ch-dot" />
        </svg>
      )}
    </div>
  );
}

export type Slice = { key: string; label: string; value: number; color: string; icon?: ReactNode; href?: string };

/** A ring split into parts with 2px gaps. The middle shows the total, or the part under the pointer / focus.
 * The legend beside it lists every part with its number and share (so nothing depends on colour or hover). */
export function Donut({
  slices,
  total,
  middle,
  label,
  size = 168,
}: {
  slices: Slice[];
  total?: number;
  middle: { value: string; text: string };
  label: string;
  size?: number;
}) {
  const [on, setOn] = useState<string | null>(null);
  const sum = total ?? slices.reduce((a, s) => a + s.value, 0);
  const stroke = 18;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const shown = slices.filter((s) => s.value > 0);
  const gap = shown.length > 1 ? 2 : 0; // the 2px surface gap between parts
  // Each part's length and where it starts along the ring.
  const arcs = shown.map((s, i) => ({ s, len: (s.value / sum) * circ, start: shown.slice(0, i).reduce((a, p) => a + (p.value / sum) * circ, 0) }));
  const active = slices.find((s) => s.key === on);
  const pct = (v: number) => (sum ? `${Math.round((v / sum) * 100)}%` : "0%");

  return (
    <div className="ch-donut">
      <div className="ch-ring" style={{ width: size, height: size }}>
        <svg width={size} height={size} role="img" aria-label={`${label}: ${slices.map((s) => `${s.label} ${s.value}`).join(", ")}`}>
          <circle cx={size / 2} cy={size / 2} r={r} className="ch-track" strokeWidth={stroke} />
          {arcs.map(({ s, len, start }) => (
              <circle
                key={s.key}
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke={s.color}
                strokeWidth={on === s.key ? stroke + 4 : stroke}
                strokeDasharray={`${Math.max(0.5, len - gap)} ${circ}`}
                transform={`rotate(${(start / circ) * 360 - 90} ${size / 2} ${size / 2})`}
                opacity={on && on !== s.key ? 0.45 : 1}
                onPointerEnter={() => setOn(s.key)}
                onPointerLeave={() => setOn(null)}
                className="ch-seg"
              />
          ))}
        </svg>
        <div className="ch-mid" aria-hidden>
          <b>{active ? num(active.value) : middle.value}</b>
          <span>{active ? active.label : middle.text}</span>
        </div>
      </div>
      <ul className="ch-legend">
        {slices.map((s) => {
          const body = (
            <>
              <i style={{ background: s.color }} />
              {s.icon}
              <span className="ch-l">{s.label}</span>
              <b>{num(s.value)}</b>
              <em>{pct(s.value)}</em>
            </>
          );
          const hover = { onPointerEnter: () => setOn(s.key), onPointerLeave: () => setOn(null), onFocus: () => setOn(s.key), onBlur: () => setOn(null) };
          return (
            <li key={s.key}>
              {s.href ? (
                <a href={s.href} {...hover}>
                  {body}
                </a>
              ) : (
                <span tabIndex={0} {...hover}>
                  {body}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Horizontal bars, one hue, the value at each bar's tip. */
export function Bars({ rows, color = "var(--s1)", empty = "No data in this period." }: { rows: { key: string; label: string; value: number; href?: string }[]; color?: string; empty?: string }) {
  if (!rows.length) return <p className="ch-empty">{empty}</p>;
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="ch-bars">
      {rows.map((r) => (
        <li key={r.key} title={`${r.label}: ${num(r.value)}`}>
          <span className="ch-l">{r.label}</span>
          <span className="ch-track-h">
            <i style={{ width: `${Math.max(r.value ? 2 : 0, (r.value / max) * 100)}%`, background: color }} />
            <b>{num(r.value)}</b>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** "Show as table": the numbers behind a chart, for screen readers and anyone who wants them exact. */
export function ChartTable({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <details className="ch-table">
      <summary>Show as table</summary>
      <div className="ch-table-x">
        <table>
          <thead>
            <tr>
              {head.map((h) => (
                <th key={h} scope="col">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                {r.map((c, j) => (j === 0 ? <th key={j} scope="row">{c}</th> : <td key={j}>{typeof c === "number" ? num(c) : c}</td>))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
