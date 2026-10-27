// The workflow canvas's block types (backend: app/crm/flow.py), how each looks in the library and on the
// canvas, the settings a new block starts with, and its exits (where lines start).

export type FlowButton = {
  id: string;
  label: string;
  icon?: string;
  variant?: string;
  visible?: boolean;
  /** Does its job by itself, with no line: link, call, whatsapp, treatment (card), callback (topic), book. */
  action?: string;
  value?: string;
};
/** The button's own jobs (no line, no extra block), as shown on the canvas and in the settings. */
export const BUTTON_ACTIONS: [string, string, string][] = [
  ["", "Goes to the next block (draw a line)", ""],
  ["treatment", "Shows a treatment card", "Treatment name"],
  ["book", "Books a treatment", "Treatment name"],
  ["callback", "Call back about…", "What it is about"],
  ["link", "Opens a link", "https://…"],
  ["whatsapp", "Opens WhatsApp", "https://wa.me/…"],
  ["call", "Calls a number", "+91…"],
];
export const ACTION_TAG: Record<string, string> = {
  treatment: "card",
  book: "book",
  callback: "call back",
  link: "link",
  whatsapp: "WhatsApp",
  call: "call",
};
export type FlowNode = {
  id: string;
  type: string;
  title: string;
  x: number;
  y: number;
  settings: Record<string, unknown>;
  /** OFF: hidden from patients with the buttons leading to it; schedule: shown only between days / in hours. */
  enabled?: boolean;
  show_from?: string | null;
  show_until?: string | null;
  clinic_hours_only?: boolean;
};
export type FlowEdge = { source: string; exit: string; target: string };
export type FieldDef = {
  key: string;
  label: string;
  kind: string;
  options?: string[];
};
export type Flow = {
  nodes: FlowNode[];
  edges: FlowEdge[];
  fields?: FieldDef[];
};
/** Filled by the chat itself; a clinic adds its own fields beside these. */
export const BUILT_IN_FIELDS = [
  "name",
  "phone",
  "email",
  "treatment",
  "doctor",
  "date",
  "time",
  "booked_date",
  "reason",
  "source",
];
export type Problem = {
  level: "error" | "warning";
  node: string;
  message: string;
};

type Kind = {
  label: string;
  group: string;
  color: string;
  hint: string;
  start: Record<string, unknown>;
};

export const KINDS: Record<string, Kind> = {
  opening: {
    label: "Opening",
    group: "Triggers",
    color: "#3E74D9",
    hint: "Welcome, figures and the main buttons",
    start: { welcome: "", buttons: [] },
  },
  typed: {
    label: "Typed message",
    group: "Triggers",
    color: "#3E74D9",
    hint: "The patient types a topic instead of tapping",
    start: { topic: "topic" },
  },
  choice: {
    label: "Choice",
    group: "Menus",
    color: "#7C3AED",
    hint: "A message with buttons, each its own exit",
    start: { message: "", buttons: [] },
  },
  answer: {
    label: "Answer",
    group: "Menus",
    color: "#7C3AED",
    hint: "Fixed text, optional buttons",
    start: { text: "Your answer", buttons: [] },
  },
  appointment_menu: {
    label: "Appointment options",
    group: "Appointments",
    color: "#0E9F6E",
    hint: "Book, online, cancel, reschedule as buttons",
    start: { message: "What would you like to do?", buttons: [] },
  },
  book: {
    label: "Book appointment",
    group: "Appointments",
    color: "#0E9F6E",
    hint: "In-clinic booking: form or step by step",
    start: {
      mode: "steps",
      fields: ["name", "phone", "treatment", "date", "time"],
    },
  },
  online: {
    label: "Online consultation",
    group: "Appointments",
    color: "#0E9F6E",
    hint: "Video consult with email for the Meet link",
    start: {
      mode: "steps",
      fields: ["name", "phone", "email", "treatment", "date", "time"],
    },
  },
  cancel: {
    label: "Cancel appointment",
    group: "Appointments",
    color: "#0E9F6E",
    hint: "Finds and cancels the booking",
    start: { mode: "steps", fields: ["name", "phone", "booked_date"] },
  },
  reschedule: {
    label: "Reschedule",
    group: "Appointments",
    color: "#0E9F6E",
    hint: "Moves a booking to a new time",
    start: {
      mode: "steps",
      fields: ["name", "phone", "booked_date", "date", "time"],
    },
  },
  callback: {
    label: "Call back",
    group: "Appointments",
    color: "#0E9F6E",
    hint: "Name, phone and what it is about",
    start: { mode: "steps", fields: ["name", "phone", "reason"] },
  },
  check_appointment: {
    label: "Check my appointment",
    group: "Appointments",
    color: "#0E9F6E",
    hint: "Shows upcoming appointments by phone (OTP optional)",
    start: {
      message: "Please share the phone number you booked with.",
      otp: false,
      otp_retries: 2,
    },
  },
  treatment_categories: {
    label: "Treatment categories",
    group: "Treatments",
    color: "#D97706",
    hint: "Main list: e.g. Hair transplant, Hair fall & scalp",
    start: { message: "What would you like to explore?", buttons: [] },
  },
  treatment_list: {
    label: "Treatment list",
    group: "Treatments",
    color: "#D97706",
    hint: "Sub list: the treatments of one category",
    start: {
      message: "Pick a treatment to learn more.",
      category: "",
      buttons: [],
    },
  },
  treatment_card: {
    label: "Treatment card",
    group: "Treatments",
    color: "#D97706",
    hint: "One treatment: price, Book for this, Read more",
    start: { treatment: "Treatment" },
  },
  doctor_list: {
    label: "Doctors",
    group: "Information",
    color: "#0891B2",
    hint: "The doctors as buttons, each to a profile",
    start: {
      message: "Which doctor would you like to know about?",
      buttons: [],
    },
  },
  doctor_card: {
    label: "Doctor card",
    group: "Information",
    color: "#0891B2",
    hint: "A doctor's profile, Book with, View treatments",
    start: {
      doctor: "Dr. ",
      title: "",
      qualifications: "",
      photo: "",
      about: "",
      stats: [],
      book_label: "Book an appointment with {doctor}",
      profile_url: "",
      treatments_label: "",
      treatments: [],
      buttons: [],
    },
  },
  location: {
    label: "Location",
    group: "Information",
    color: "#0891B2",
    hint: "Address, hours and map, live from Contact & hours",
    start: { message: "", map: true, hours: true, buttons: [] },
  },
  reviews: {
    label: "Reviews",
    group: "Information",
    color: "#0891B2",
    hint: "Patient reviews, live from Clinic info → Reviews",
    start: { message: "", count: 3, buttons: [] },
  },
  faq: {
    label: "FAQ list",
    group: "Information",
    color: "#0891B2",
    hint: "Questions as buttons, each shows its answer",
    start: {
      message: "Common questions:",
      items: [{ question: "Is it painful?", answer: "Your answer" }],
      buttons: [],
    },
  },
  knowledge: {
    label: "Knowledge base",
    group: "Information",
    color: "#0891B2",
    hint: "Answers a typed question from approved answers only",
    start: { message: "What would you like to know?", topics: [] },
  },
  question: {
    label: "Question",
    group: "Questions",
    color: "#DB2777",
    hint: "Asks one thing (text, number, date, choice, rating, yes/no, file) and saves it",
    start: {
      question: "Your question?",
      kind: "text",
      field: "reason",
      options: [],
      required: true,
      retries: 2,
    },
  },
  clinic_open: {
    label: "Clinic open / closed",
    group: "Logic",
    color: "#6366F1",
    hint: "One way while open, another while closed",
    start: { hours: "in_clinic" },
  },
  goto: {
    label: "Go to",
    group: "Logic",
    color: "#6366F1",
    hint: "Jumps to another block (no long line)",
    start: { target: "" },
  },
  set_field: {
    label: "Set field",
    group: "Logic",
    color: "#6366F1",
    hint: "Saves a value into a field, then goes on",
    start: { field: "", value: "" },
  },
  link: {
    label: "Link",
    group: "Contact & safety",
    color: "#475569",
    hint: "Opens a web page",
    start: { url: "https://" },
  },
  whatsapp: {
    label: "WhatsApp",
    group: "Contact & safety",
    color: "#1F9D55",
    hint: "Opens WhatsApp with a message",
    start: { url: "https://wa.me/" },
  },
  call: {
    label: "Call",
    group: "Contact & safety",
    color: "#475569",
    hint: "Calls a number",
    start: { number: "+91" },
  },
  emergency: {
    label: "Emergency",
    group: "Contact & safety",
    color: "#DC2626",
    hint: "108 reply, warning signs, call the clinic",
    start: { text: "For a medical emergency, call 108.", buttons: [] },
  },
};
export const GROUPS = [
  "Triggers",
  "Menus",
  "Appointments",
  "Treatments",
  "Information",
  "Contact & safety",
  "Questions",
  "Logic",
];
const LEAD = new Set(["book", "online", "cancel", "reschedule", "callback"]);
/** Blocks that are a message with buttons (each button its own exit). */
export const MENUS = new Set([
  "opening",
  "choice",
  "appointment_menu",
  "treatment_categories",
  "treatment_list",
  "doctor_list",
]);

export const buttonsOf = (n: FlowNode) =>
  (n.settings.buttons as FlowButton[] | undefined) ?? [];

/** Where lines can start from a block (as the backend's exits()). */
export function exitsOf(n: FlowNode): { id: string; label: string }[] {
  const out = buttonsOf(n)
    .filter((b) => !b.action)
    .map((b) => ({ id: b.id, label: b.label }));
  if (n.type === "check_appointment")
    out.push(
      { id: "found", label: "found" },
      { id: "not_found", label: "not found" },
      ...(n.settings.otp ? [{ id: "code_failed", label: "code failed" }] : []),
    );
  if (n.type === "clinic_open")
    out.push({ id: "open", label: "open" }, { id: "closed", label: "closed" });
  if (n.type === "knowledge")
    out.push(
      { id: "answered", label: "answered" },
      { id: "not_found", label: "not found" },
    );
  if (n.type === "question")
    out.push(
      ...(n.settings.kind === "yes_no"
        ? [
            { id: "yes", label: "yes" },
            { id: "no", label: "no" },
          ]
        : [{ id: "next", label: "next" }]),
    );
  if (n.type === "typed" || n.type === "set_field")
    out.push({ id: "next", label: "next" });
  if (LEAD.has(n.type)) out.push({ id: "done", label: "done" });
  if (n.type === "doctor_card" && n.settings.book_label)
    out.push({ id: "book", label: String(n.settings.book_label) });
  if (n.type === "treatment_card")
    out.push(
      { id: "book", label: "Book for this" },
      { id: "more", label: "Read more" },
    );
  if (MENUS.has(n.type))
    out.push({ id: "no_match", label: "no match (typed)" });
  return out;
}

/** The first problems the canvas can see without asking the backend: buttons that lead nowhere. */
export function looseEnds(flow: Flow): Problem[] {
  const linked = new Set(flow.edges.map((e) => `${e.source}|${e.exit}`));
  return flow.nodes.flatMap((n) =>
    buttonsOf(n)
      .filter(
        (b) =>
          b.visible !== false && !b.action && !linked.has(`${n.id}|${b.id}`),
      )
      .map((b) => ({
        level: "error" as const,
        node: n.id,
        message: `Button '${b.label}' leads nowhere.`,
      })),
  );
}

const MENU_TYPES = [
  "opening",
  "choice",
  "appointment_menu",
  "treatment_categories",
  "treatment_list",
  "doctor_list",
];
/** About how tall a block is drawn: header, then one row per button or exit (as the backend's layout). */
const heightOf = (n: FlowNode) =>
  90 +
  26 *
    (buttonsOf(n).length +
      (MENU_TYPES.includes(n.type) ? 1 : 0) +
      (LEAD.has(n.type) || n.type === "typed" ? 1 : 0) +
      (n.type === "treatment_list" ? 12 : 0));

/** One lane per trigger (as the backend's layout): each main button's flow, then each Typed trigger's, depth
 * left to right, blocks stacked by their real height; the lanes packed side by side so the whole flow is about
 * as wide as a screen (16:9), not one tall strip. */
export function arrange(flow: Flow): Flow {
  const next = new Map<string, string[]>();
  flow.edges.forEach((e) =>
    next.set(e.source, [...(next.get(e.source) ?? []), e.target]),
  );
  const byId = new Map(flow.nodes.map((n) => [n.id, n]));
  const placed = new Set<string>();
  const opening = flow.nodes.find((n) => n.type === "opening");
  const firsts: string[] = [];
  if (opening) {
    placed.add(opening.id);
    flow.edges
      .filter((e) => e.source === opening.id)
      .forEach((e) => firsts.push(e.target));
  }
  flow.nodes
    .filter((n) => n.type === "typed")
    .forEach((n) => firsts.push(n.id));
  type Lane = {
    blocks: [string, number, number][];
    cols: number;
    height: number;
  };
  const lanes: Lane[] = [];
  for (const first of firsts) {
    if (placed.has(first)) continue;
    const bottom = new Map<number, number>();
    const blocks: [string, number, number][] = [];
    const todo: [string, number][] = [[first, 0]];
    for (let i = 0; i < todo.length; i++) {
      const [id, col] = todo[i];
      const node = byId.get(id);
      if (placed.has(id) || !node) continue;
      placed.add(id);
      const y = bottom.get(col) ?? 0;
      blocks.push([id, col, y]);
      bottom.set(col, y + heightOf(node) + 40);
      (next.get(id) ?? []).forEach(
        (t) => !placed.has(t) && todo.push([t, col + 1]),
      );
    }
    lanes.push({
      blocks,
      cols: Math.max(...bottom.keys()) + 1,
      height: Math.max(...bottom.values()),
    });
  }
  // Pack the lanes into k side-by-side columns, choosing the k whose shape is closest to 16:9.
  let best: number[][] = [lanes.map((_, i) => i)];
  if (lanes.length) {
    const total = lanes.reduce((a, l) => a + l.height, 0);
    const tallest = Math.max(...lanes.map((l) => l.height));
    let bestScore = Infinity;
    for (let k = 1; k <= lanes.length; k++) {
      const limit = Math.max(total / k, tallest);
      const cols: number[][] = [];
      let cur: number[] = [];
      let used = 0;
      lanes.forEach((l, i) => {
        if (cur.length && used + l.height > limit) {
          cols.push(cur);
          cur = [];
          used = 0;
        }
        cur.push(i);
        used += l.height + 60;
      });
      cols.push(cur);
      const width =
        cols.reduce((a, c) => a + Math.max(...c.map((i) => lanes[i].cols)), 0) *
        340;
      const height = Math.max(
        ...cols.map((c) => c.reduce((a, i) => a + lanes[i].height + 60, 0)),
      );
      const score = Math.abs(width / Math.max(height, 1) - 16 / 9);
      if (score < bestScore) {
        best = cols;
        bestScore = score;
      }
    }
  }
  const pos = new Map<string, { x: number; y: number }>();
  let x0 = opening ? 340 : 0;
  if (opening) pos.set(opening.id, { x: 0, y: 0 });
  for (const packed of best) {
    let y0 = 0;
    for (const i of packed) {
      lanes[i].blocks.forEach(([id, c, y]) =>
        pos.set(id, { x: x0 + c * 340, y: y0 + y }),
      );
      y0 += lanes[i].height + 60;
    }
    x0 += Math.max(0, ...packed.map((i) => lanes[i].cols)) * 340 + 60;
  }
  let k = 0;
  return {
    ...flow,
    nodes: flow.nodes.map((n) => {
      const p = pos.get(n.id) ?? {
        x: x0 + (k % 3) * 340,
        y: Math.floor(k++ / 3) * 260,
      };
      return { ...n, x: p.x, y: p.y };
    }),
  };
}

export function newId(flow: Flow, type: string) {
  const base = type.replace(/_/g, "-");
  let i = 1;
  while (flow.nodes.some((n) => n.id === `${base}-${i}`)) i++;
  return `${base}-${i}`;
}

/** Drops lines whose exit no longer exists (e.g. a doctor card's Book button was removed). */
export function pruneLines(flow: Flow): Flow {
  const ok = new Set(
    flow.nodes.flatMap((n) => exitsOf(n).map((x) => `${n.id}|${x.id}`)),
  );
  return {
    ...flow,
    edges: flow.edges.filter((e) => ok.has(`${e.source}|${e.exit}`)),
  };
}
