// Dashboard → Knowledge base → Upload CSV: reads one of the three files the tab gives out (facts sample, Q&A
// sample, onboarding questions) into rows for POST /kb/import, which checks each row and saves drafts.

export type ImportRow = {
  row: number; // the line in the file, for the report
  kind: "fact" | "qa";
  key?: string;
  category?: string;
  value?: string; // a fact's value, or a Q&A's answer
  question?: string;
  variants?: string;
  treatment?: string;
};

/** CSV text → rows of cells (quotes, commas and line breaks inside quotes; a leading BOM is dropped). */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  const s = text.replace(/^\uFEFF/, "");
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (quoted) {
      if (c === '"' && s[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") {
      row.push(cell);
      cell = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && s[i + 1] === "\n") i++;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else cell += c;
  }
  if (cell || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}

// Onboarding sections → Knowledge base categories.
const CATEGORY: Record<number, string> = {
  10: "cost",
  15: "cost",
  16: "cost",
  3: "doctor",
  2: "treatment",
  6: "treatment",
  7: "treatment",
  8: "treatment",
  9: "treatment",
  12: "treatment",
  13: "treatment",
  14: "treatment",
  25: "treatment",
  33: "treatment",
  4: "policy",
  17: "policy",
  18: "policy",
  19: "policy",
  23: "policy",
  24: "policy",
  32: "policy",
  26: "other",
  27: "other",
  28: "other",
  29: "other",
  34: "other",
};

/** The file's rows to import, which file it was, and the rows left out (with why). */
export function toImport(text: string): {
  kind: "facts" | "qa" | "onboarding";
  rows: ImportRow[];
  skipped: string[];
} {
  const all = parseCsv(text);
  const head = (all[0] ?? []).map((h) => h.trim().toLowerCase());
  const col = (name: string) => head.indexOf(name);
  const get = (r: string[], name: string) =>
    col(name) >= 0 ? (r[col(name)] ?? "").trim() : "";
  const wordings = (v: string) =>
    v
      .split("|")
      .map((x) => x.trim())
      .filter(Boolean)
      .join("\n");
  const kind =
    head.includes("step") && head.includes("key")
      ? "onboarding"
      : head.includes("question")
        ? "qa"
        : head.includes("key")
          ? "facts"
          : null;
  if (!kind)
    throw new Error(
      "This file has none of the expected columns. Use a sample from this tab, or the onboarding questions.",
    );
  const rows: ImportRow[] = [];
  const skipped: string[] = [];
  all.slice(1).forEach((r, i) => {
    const line = i + 2;
    if (r.every((c) => !c.trim()) || r[0]?.trim().startsWith("#")) return; // blank, or the how-to note
    if (kind === "facts") {
      rows.push({
        row: line,
        kind: "fact",
        key: get(r, "key"),
        category: get(r, "category"),
        value: get(r, "value"),
        variants: wordings(get(r, "other_wordings")),
      });
    } else if (kind === "qa") {
      rows.push({
        row: line,
        kind: "qa",
        question: get(r, "question"),
        variants: wordings(get(r, "other_wordings")),
        value: get(r, "answer"),
        category: get(r, "category"),
        treatment: get(r, "treatment"),
      });
    } else {
      const answer = get(r, "answer");
      if (!answer) return; // not answered yet
      if (get(r, "repeat_for")) {
        skipped.push(
          `Row ${line}: per ${get(r, "repeat_for")} questions are added in a later step`,
        );
        return;
      }
      const section = Number.parseInt(get(r, "section"), 10);
      rows.push({
        row: line,
        kind: "fact",
        key: get(r, "key"),
        category: CATEGORY[section] ?? "clinic_info",
        value: answer,
        variants: get(r, "question"), // so a patient typing the question finds it
      });
    }
  });
  return { kind, rows, skipped };
}
