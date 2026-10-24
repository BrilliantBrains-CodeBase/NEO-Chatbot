// SAMPLE DATA for the screens-first steps, ported from the approved design's own generator so every count
// and list looks the same as there. Replaced screen by screen when each one is connected to the backend.

export const CLINICS = ["Derma Solutions", "Neo Fertility", "Neo Follicle"] as const;
export type Clinic = (typeof CLINICS)[number];

export const CLINIC_CONTENT: Record<Clinic, { docs: string[]; tr: string[] }> = {
  "Derma Solutions": {
    docs: ["Dr Sandeep Mahapatra", "Dr Sumedha Tirthani", "Dr Thyagaraj", "Dr Chandhana Vishal N"],
    tr: ["HydraFacial", "Laser Hair Removal", "Botox", "Acne Scar Treatment", "Chemical Peels", "Dermal Fillers", "Liposuction", "GFC Hair Treatment"],
  },
  "Neo Fertility": {
    docs: ["Dr Payal Mahapatra"],
    tr: ["IVF", "IUI", "ICSI", "Fertility consultation", "Egg freezing", "PCOS or PCOD", "Pregnancy care"],
  },
  "Neo Follicle": {
    docs: ["Dr Sandeep Mahapatra"],
    tr: ["Hair Transplant for Men", "Female Hair Transplant", "Beard Transplant", "Eyebrow Restoration", "Failed Hair Transplant Repair", "Non-Surgical Treatment (GFC, PRP, QR678)"],
  },
};

/** Opening hours as decimal hours and the weekly closed day (0 Sunday ... 6 Saturday, -1 none). */
export const CLINIC_HOURS: Record<Clinic, { open: [number, number]; closed: number }> = {
  "Derma Solutions": { open: [10, 20], closed: 2 },
  "Neo Fertility": { open: [9.5, 18.5], closed: -1 },
  "Neo Follicle": { open: [10, 19], closed: 2 },
};

export type Stage = "new" | "fu" | "bk" | "vi" | "lo" | "in";
export const STAGES: { key: Stage; label: string; badge: string }[] = [
  { key: "new", label: "New", badge: "b-new" },
  { key: "fu", label: "Follow Up", badge: "b-fu" },
  { key: "bk", label: "Booked", badge: "b-bk" },
  { key: "vi", label: "Visited", badge: "b-vi" },
  { key: "lo", label: "Lost", badge: "b-lo" },
  { key: "in", label: "Invalid", badge: "b-in" },
];

export const SOURCES = ["Chatbot", "Meta Ads", "Google Ads", "Manual", "WhatsApp"] as const;
const CAMPAIGN: Record<string, string> = {
  "Meta Ads": "Diwali glow offer",
  "Google Ads": "Search, brand",
  Chatbot: "Website chat",
  Manual: "Walk-in",
  WhatsApp: "WhatsApp chat",
};
export const STAFF: [initials: string, name: string][] = [
  ["PS", "Priya S"],
  ["RK", "Ravi K"],
  ["AM", "Asha M"],
  ["", "Unassigned"],
];
const NAMES = ["Priya Sharma", "Rahul Verma", "Ananya Rao", "Karthik Reddy", "Sneha Iyer", "Vikram Singh", "Meera Nair", "Arjun Patel", "Divya Menon", "Rohan Gupta", "Kavya Shetty", "Aditya Kumar", "Pooja Joshi", "Nikhil Das", "Lakshmi Pillai", "Sameer Khan", "Ishita Bose", "Varun Hegde", "Neha Kapoor", "Siddharth Jain", "Anjali Desai", "Manoj Rao", "Ritika Malhotra", "Harish Gowda", "Tanvi Kulkarni", "Deepak Yadav", "Shreya Ghosh", "Akash Mehta", "Bhavana Murthy", "Gautam Sen"];

export type Lead = {
  id: number;
  name: string;
  phone: string;
  email: string;
  src: string;
  camp: string;
  tr: string;
  doc: string;
  type: "In-clinic" | "Online";
  st: Stage;
  appt: Date | null;
  fu: Date | null;
  as: [string, string];
  created: Date;
  last: string;
  unread: boolean;
  tl: [string, string][];
};

export function sampleLeads(clinic: Clinic, now = new Date()): Lead[] {
  const cfg = CLINIC_CONTENT[clinic];
  const STG_ORDER: Stage[] = ["new", "new", "new", "fu", "fu", "bk", "bk", "bk", "vi", "vi", "vi", "vi", "lo", "in"];
  const LAST = ["Called, no answer", "Chat completed", "WhatsApp sent", "Note added", "Booked by front desk"];
  return NAMES.map((name, i) => {
    const st = STG_ORDER[i % 14];
    const src = SOURCES[i % 5];
    const ap = new Date(now);
    ap.setDate(now.getDate() + (st === "vi" ? -(i % 9) - 1 : i % 6));
    ap.setHours(10 + (i % 8), i % 2 ? 30 : 0, 0, 0);
    const fu = new Date(now);
    fu.setDate(now.getDate() + ((i % 5) - 2));
    const as = STAFF[i % 4];
    return {
      id: i + 1,
      name,
      phone: "+91 9" + String(800000000 + i * 3456789).slice(0, 9),
      email: name.split(" ")[0].toLowerCase() + "@example.com",
      src,
      camp: CAMPAIGN[src],
      tr: cfg.tr[i % cfg.tr.length],
      doc: cfg.docs[i % cfg.docs.length],
      type: i % 4 === 1 ? "Online" : "In-clinic",
      st,
      appt: st === "bk" || st === "vi" ? ap : null,
      fu: st === "fu" ? fu : null,
      as,
      created: new Date(now.getTime() - ((i * 37) % (60 * 24 * 4)) * 60000),
      last: LAST[i % 5],
      unread: st === "new" && i % 3 !== 2,
      tl: [
        ["Lead created from " + src, "2d ago"],
        ["Assigned to " + as[1], "2d ago"],
        ["Called, no answer", "1d ago"],
        ["Note: prefers evening slots", "5h ago"],
      ],
    };
  });
}

export type ReqKind = "appt" | "online" | "cancel" | "resch" | "cb" | "chat";
export const REQUEST_TABS: { key: ReqKind; label: string }[] = [
  { key: "appt", label: "Booking requests" },
  { key: "online", label: "Online consults" },
  { key: "cancel", label: "Cancellations" },
  { key: "resch", label: "Reschedules" },
  { key: "cb", label: "Callbacks" },
  { key: "chat", label: "Chatbot chats" },
];

export type Req = {
  id: string;
  kind: ReqKind;
  lead: number | null;
  status: "pending" | "done";
  created: Date;
  doc?: string;
  tr?: string;
  src?: string;
  when?: Date;
  old?: Date;
  reason?: string;
  attempts?: number;
  outcome?: string;
  by?: string;
  msgs?: number;
  visitor?: string;
};

export function sampleRequests(clinic: Clinic, leads: Lead[], now = new Date()): Req[] {
  const hours = CLINIC_HOURS[clinic];
  const out: Req[] = [];
  const day = (n: number, h: number, m = 0) => {
    const x = new Date(now);
    x.setDate(now.getDate() + n);
    while (x.getDay() === hours.closed) x.setDate(x.getDate() + 1);
    x.setHours(h < hours.open[0] ? Math.ceil(hours.open[0]) : h, m, 0, 0);
    return x;
  };
  const mk = (kind: ReqKind, i: number, extra: Partial<Req> = {}) => {
    const l = leads[i];
    out.push({
      id: kind + i,
      kind,
      lead: l.id,
      doc: l.doc,
      tr: l.tr,
      src: l.src,
      status: "pending",
      created: new Date(now.getTime() - (((i * 53) % 170) + 8) * 60000),
      ...extra,
    });
  };
  mk("appt", 0, { when: day(1, 11) });
  mk("appt", 3, { when: day(1, 16, 30) });
  mk("appt", 10, { when: day(2, 12) });
  mk("online", 1, { when: day(1, 17) });
  mk("cancel", 5, { when: leads[5].appt ?? day(2, 11, 30), reason: "Not feeling well" });
  mk("resch", 6, { old: leads[6].appt ?? day(1, 15), when: day(3, 12, 30) });
  mk("cb", 2, { reason: "What is the cost of " + leads[2].tr + "?", attempts: 0, created: new Date(now.getTime() - 104 * 60000) });
  mk("cb", 7, { reason: "Is the treatment painful?", attempts: 1, created: new Date(now.getTime() - 26 * 60000) });
  const chats: [string, number][] = [["Lead created", 0], ["FAQ answered", -1], ["Lead created", 4], ["Handoff to callback", 2], ["AI answered", -1], ["Abandoned", -1]];
  chats.forEach(([outcome, li], i) => {
    out.push({
      id: "chat" + i,
      kind: "chat",
      lead: li >= 0 ? leads[li].id : null,
      status: "pending",
      outcome,
      msgs: 6 + i * 2,
      created: new Date(now.getTime() - (i * 41 + 12) * 60000),
      visitor: li >= 0 ? leads[li].name : "Visitor " + (1040 + i),
    });
  });
  mk("appt", 12, { when: day(-1, 12), status: "done", outcome: "Approved", by: "Ravi K" });
  mk("cb", 9, { reason: "Timings", status: "done", outcome: "Answered", by: "Priya S", attempts: 1 });
  return out;
}
