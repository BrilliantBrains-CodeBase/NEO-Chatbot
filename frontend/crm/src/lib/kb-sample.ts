import { allQuestions, STEPS } from "./onboarding";

// Dashboard → Knowledge base: sample CSV files for clinics to fill in (Excel opens them; a BOM keeps ₹ and
// other characters right). The Q&A sample links the facts sample's keys, e.g. {consult_fee}.

const FACTS: string[][] = [
  ["key", "category", "value", "other_wordings"],
  [
    "clinic_timings",
    "clinic_info",
    "Monday to Saturday, 10:00 AM to 7:00 PM. Closed on Sunday.",
    "timings|opening hours|when are you open",
  ],
  [
    "clinic_address",
    "clinic_info",
    "2nd floor, Example Plaza, MG Road, Bengaluru 560001",
    "address|location|where is the clinic",
  ],
  [
    "clinic_phone",
    "clinic_info",
    "+91 98765 43210",
    "phone number|contact number",
  ],
  ["consult_fee", "cost", "₹500", "consultation fee|doctor fee"],
  [
    "emi_options",
    "cost",
    "EMI is available on treatments above ₹20,000, with no hidden charges.",
    "emi|instalments",
  ],
  [
    "languages",
    "clinic_info",
    "English, Hindi and Kannada",
    "languages spoken",
  ],
  [
    "parking",
    "clinic_info",
    "Free parking is available in the building basement.",
    "parking",
  ],
  [
    "cancellation_policy",
    "policy",
    "Please cancel or reschedule at least 4 hours before your appointment.",
    "cancel policy|reschedule policy",
  ],
];

const QA: string[][] = [
  ["question", "other_wordings", "answer", "category", "treatment"],
  [
    "What are the clinic timings?",
    "when are you open|opening hours|is the clinic open on sunday",
    "We are open {clinic_timings}",
    "clinic_info",
    "",
  ],
  [
    "Where is the clinic located?",
    "address please|how do I reach you|clinic location",
    "Our clinic is at {clinic_address}.",
    "clinic_info",
    "",
  ],
  [
    "What is the consultation fee?",
    "doctor fee|how much is the consultation|consultation charges",
    "The consultation fee is {consult_fee}.",
    "cost",
    "",
  ],
  [
    "Do you offer EMI?",
    "can I pay in instalments|emi available",
    "{emi_options}",
    "cost",
    "",
  ],
  [
    "Which languages do you speak?",
    "do you speak hindi|kannada speaking doctor",
    "Our team speaks {languages}.",
    "clinic_info",
    "",
  ],
  [
    "Is parking available?",
    "where can I park|car parking",
    "{parking}",
    "clinic_info",
    "",
  ],
  [
    "How do I cancel my appointment?",
    "cancel booking|reschedule appointment",
    "{cancellation_policy} You can also call us on {clinic_phone}.",
    "policy",
    "",
  ],
  [
    "How long does the consultation take?",
    "consultation duration|how much time for consultation",
    "A consultation usually takes 20 to 30 minutes.",
    "treatment",
    "Consultation",
  ],
];

const HELP: Record<"facts" | "qa", string> = {
  facts:
    "key: small letters, numbers and _ (used as {key} in answers) · category: clinic_info, treatment, cost, doctor, policy or other · other_wordings: separate with |",
  qa: "answer may link a fact as {key} (add the fact first) · category: clinic_info, treatment, cost, doctor, policy or other · other_wordings: separate with | · treatment is optional",
};

function csv(rows: string[][]): string {
  const cell = (v: string) =>
    /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
  return rows.map((r) => r.map(cell).join(",")).join("\r\n");
}

/** Downloads the sample for the tab: facts or Q&A, with a note line on how to fill it. */
export function downloadSample(kind: "facts" | "qa"): void {
  const rows = kind === "facts" ? FACTS : QA;
  const body = `${csv(rows)}\r\n\r\n${csv([[`# ${HELP[kind]}`]])}\r\n`;
  const blob = new Blob(["\uFEFF" + body], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download =
    kind === "facts"
      ? "knowledge-base-facts-sample.csv"
      : "knowledge-base-qa-sample.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/** Downloads the clinic onboarding questionnaire: every question once, in the 10 steps, to fill in. */
export function downloadOnboarding(): void {
  const rows: string[][] = [
    [
      "step",
      "step_name",
      "section",
      "key",
      "question",
      "type",
      "options",
      "answer",
      "repeat_for",
      "note",
    ],
  ];
  for (const { section: s, question: q, gate } of allQuestions()) {
    const note = gate
      ? `Answer Yes to fill the next ${s.questions.length} questions; No skips them.`
      : s.repeat
        ? `Copy these rows for each ${s.repeat}.${s.note ? ` ${s.note}` : ""}`
        : (s.note ?? "");
    rows.push([
      String(s.step),
      STEPS[s.step - 1],
      `${s.n}. ${s.title}`,
      q.key,
      q.text,
      q.type === "yes_no" ? "Yes / No" : q.type,
      (q.options ?? []).join(" | "),
      q.default ?? "",
      s.repeat ?? "",
      note,
    ]);
  }
  const blob = new Blob(["\uFEFF" + csv(rows) + "\r\n"], {
    type: "text/csv;charset=utf-8",
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "clinic-onboarding-questions.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
