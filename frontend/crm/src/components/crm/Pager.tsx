"use client";

/** Below a list: which rows are shown, the page, and the boxed arrows (off where there is nowhere to go). */
export default function Pager({
  page,
  size,
  shown,
  total,
  onPage,
}: {
  page: number;
  size: number;
  shown: number;
  total: number;
  onPage: (n: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / size));
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        flexWrap: "wrap",
        marginTop: 12,
      }}
    >
      <span className="sub2">
        Showing {(page - 1) * size + 1}–{(page - 1) * size + shown} of {total}
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className="sub2">
          Page {page} of {pages}
        </span>
        {(
          [
            ["Previous page", "‹", page - 1, page <= 1],
            ["Next page", "›", page + 1, page >= pages],
          ] as [string, string, number, boolean][]
        ).map(([label, mark, to, off]) => (
          <button
            key={label}
            type="button"
            className="btn g sm"
            aria-label={label}
            title={label}
            disabled={off}
            style={{
              width: 34,
              height: 34,
              padding: 0,
              justifyContent: "center",
              fontSize: "var(--fs-section)",
              lineHeight: 1,
              opacity: off ? 0.45 : 1,
              cursor: off ? "not-allowed" : "pointer",
            }}
            onClick={() => onPage(to)}
          >
            {mark}
          </button>
        ))}
      </div>
    </div>
  );
}
