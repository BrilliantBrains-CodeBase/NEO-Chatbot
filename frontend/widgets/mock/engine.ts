// Mock backend: answers like the real FastAPI backend will, using the contract in core/types.ts.
// Used by the dev playground and the Playwright tests only; it is never part of a clinic's widget file.
// Arya (CL01) has the full flows; Navya and Diya only greet until their faces are built.
import type { ChatRequest, ChatResponse, Choice, UiBlock } from '../core/types';
import { addDays, fmtDate, fmtTime, weekday } from '../core/dates';
import { ARYA, MENU, NODES, TYPE } from './arya';

const GREETING: Record<string, string> = {
  CL01: ARYA.greeting,
  CL02: "Hi, I'm Navya, Neo Fertility's AI assistant. How can I help you today?",
  CL03: "Hi, I'm Diya, Derma Solutions' AI assistant. How can I help you today?",
};

const NO_ANSWER =
  "I don't have a confirmed answer for that yet. Share your number and our team will call you back with the right information.";
const CONSENT = 'By confirming, you agree to be contacted by phone, WhatsApp or email.';

// The clock can be set by tests, so date and slot rules are checked at a fixed time.
export const clock = { now: () => new Date() };

// India time (UTC+5:30): today's date and minutes since midnight.
function ist() {
  const d = new Date(clock.now().getTime() + 330 * 60000);
  return { today: d.toISOString().slice(0, 10), minutes: d.getUTCHours() * 60 + d.getUTCMinutes() };
}

const hm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;

// Free slots for a day. Every slot is free in the mock; past times are removed for today.
function slotsFor(ymd: string): string[] {
  if (ARYA.closedWeekdays.includes(weekday(ymd))) return [];
  const { today, minutes } = ist();
  const out: string[] = [];
  for (let m = ARYA.firstSlot; m <= ARYA.lastSlot; m += ARYA.slotMinutes) {
    if (ymd !== today || m > minutes) out.push(hm(m));
  }
  return out;
}

// New booking: today (if a slot is left) up to the end of the booking window.
function newDateRange() {
  const { today } = ist();
  return {
    today,
    min: slotsFor(today).length ? today : addDays(today, 1),
    max: addDays(today, ARYA.bookingWindowDays),
  };
}

function newDateCalendar(action: string): UiBlock {
  return { type: 'month_calendar', action, ...newDateRange(), closed_weekdays: ARYA.closedWeekdays };
}

function bookable(ymd: string): boolean {
  const { min, max } = newDateRange();
  return ymd >= min && ymd <= max && slotsFor(ymd).length > 0;
}

// ---------- conversation state ----------

// question: a typed question the bot cannot answer becomes a lead (name, number, email; the question is the reason).
type Kind = 'book' | 'online' | 'cancel' | 'reschedule' | 'callback' | 'question';
type Step =
  | 'name'
  | 'phone'
  | 'email'
  | 'treatment'
  | 'reason'
  | 'cb_reason'
  | 'booked_date'
  | 'date'
  | 'time'
  | 'summary';

interface Flow {
  kind: Kind;
  step: Step;
  // After a "Change ..." button, return to the summary instead of continuing step by step.
  backToSummary?: boolean;
  name?: string;
  phone?: string; // "+91 9876543210"
  email?: string;
  treatment?: string;
  reason?: string; // Other: what they are looking for. Callback: the topic. Question: what they typed.
  bookedDate?: string; // cancel and reschedule: the date of the existing booking
  date?: string; // YYYY-MM-DD
  time?: string; // HH:MM or "any"
}

const sessions = new Map<string, Flow | null>();

// ---------- validation (same rules the real backend will use) ----------

const validName = (s: string) => /^\p{L}[\p{L} .'-]*\p{L}$/u.test(s.trim());
const validEmail = (s: string) => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(s.trim());
function normalPhone(text: string, cc = '+91'): string | null {
  const digits = text.replace(/[\s()-]/g, '');
  const ok = cc === '+91' ? /^[6-9]\d{9}$/.test(digits) : /^\d{6,12}$/.test(digits);
  return ok ? `${cc} ${digits}` : null;
}
const firstName = (name: string) => name.trim().split(/\s+/)[0];

// ---------- replies ----------

const reply = (texts: string[], ui: UiBlock | null = null, input = TYPE): ChatResponse => ({
  messages: texts.map((text) => ({ type: 'text', text })),
  ui,
  input,
});

const INTRO: Record<Kind, string> = {
  book: "Sure, let's book your appointment. May I know your full name?",
  online: "Sure, let's book your online video consultation. May I know your full name?",
  cancel: 'Sure, I can help you cancel your appointment. May I know your full name?',
  reschedule: 'Sure, I can help you reschedule your appointment. May I know your full name?',
  callback: 'Sure, I can arrange a callback. May I know your full name?',
  question: 'May I know your full name?',
};

// Cancel and reschedule: the booked date can be up to 2 months back or up to the booking window ahead.
function bookedDateRange() {
  const { today } = ist();
  return {
    today,
    min: addDays(today, -ARYA.bookedDateBackDays),
    max: addDays(today, ARYA.bookingWindowDays),
  };
}

function bookedDateCalendar(): UiBlock {
  return {
    type: 'month_calendar',
    action: 'booked_date',
    ...bookedDateRange(),
    closed_weekdays: ARYA.closedWeekdays,
  };
}

function validBookedDate(ymd: string): boolean {
  const { min, max } = bookedDateRange();
  return ymd >= min && ymd <= max && !ARYA.closedWeekdays.includes(weekday(ymd));
}

// The question for a step, with its input or picker. Also used to ask a step again.
function ask(f: Flow, lead: string[] = []): ChatResponse {
  switch (f.step) {
    case 'name':
      return reply([...lead, 'May I know your full name?'], null, {
        mode: 'text',
        placeholder: 'Your full name',
      });
    case 'phone':
      return reply([...lead, `Thanks, ${firstName(f.name!)}. What is your contact number?`], null, {
        mode: 'phone',
        placeholder: 'Mobile number',
      });
    case 'email':
      return reply([...lead, 'What is your email address?'], null, {
        mode: 'email',
        placeholder: 'name@example.com',
      });
    case 'treatment':
      return reply([...lead, 'Which treatment are you looking for?'], {
        type: 'chips',
        options: ARYA.treatments.map((t) => ({ label: t, action: 'treatment', value: t })),
      });
    case 'reason':
      return reply([...lead, 'Please tell us briefly what you are looking for.'], null, {
        mode: 'text',
        placeholder: 'Short reason',
      });
    case 'cb_reason':
      return reply([...lead, 'What would you like to discuss on the call?'], null, {
        mode: 'text',
        placeholder: 'Reason for the call',
      });
    case 'booked_date':
      return reply([...lead, 'Which date is your appointment booked for?'], bookedDateCalendar());
    case 'date':
      return reply(
        [...lead, f.kind === 'reschedule' ? 'Which new date would you prefer?' : 'Which date works for you?'],
        newDateCalendar('date'),
      );
    case 'time':
      return reply(
        [
          ...lead,
          f.kind === 'reschedule' ? 'And what new time would you prefer?' : 'What time would you prefer?',
        ],
        {
          type: 'time_grid',
          action: 'time',
          slots: slotsFor(f.date!),
          first: 4,
          any_time: true,
        },
      );
    case 'summary':
      return summary(f, lead);
  }
}

const treatmentText = (f: Flow) => (f.treatment === 'Other' && f.reason ? f.reason : f.treatment!);
const whenText = (f: Flow) =>
  f.time === 'any' ? `${fmtDate(f.date!)}, any time` : `${fmtDate(f.date!)} at ${fmtTime(f.time!)}`;
const visitText = (f: Flow) =>
  f.kind === 'online' ? 'Online video consultation (Google Meet)' : 'In-clinic visit';

function summary(f: Flow, lead: string[] = []): ChatResponse {
  const text = [
    'Please check your details:',
    `**${f.name}**`,
    f.phone!,
    f.email!,
    treatmentText(f),
    visitText(f),
    whenText(f),
    `**${CONSENT}**`,
  ].join('\n');
  const options: Choice[] = [
    { label: 'Confirm booking', action: 'confirm' },
    { label: 'Change treatment', action: 'change_treatment' },
    { label: 'Change date and time', action: 'change_datetime' },
    ...(f.kind === 'online' ? [{ label: 'Switch to in-clinic visit', action: 'switch_inclinic' }] : []),
    { label: 'Start again', action: 'start_again' },
  ];
  return reply([...lead, text], { type: 'chips', options });
}

const DONE: UiBlock = {
  type: 'chips',
  options: [
    { label: 'Main menu', action: 'menu' },
    { label: 'Talk to us', action: 'go', value: 'talk' },
  ],
};

// Cancel and reschedule end here. The real backend matches name and number to a booking; with or
// without a match the request goes to the clinic team, and the patient sees the same message.
function cancelled(f: Flow): ChatResponse {
  return reply(
    [
      `Thanks, ${firstName(f.name!)}. Your request to cancel the appointment on **${fmtDate(f.bookedDate!)}** is received. Our team will contact you on ${f.phone} to confirm the cancellation.`,
    ],
    DONE,
  );
}

// Callback and typed-question leads end here; the real backend saves the lead to the CRM.
function calledBack(f: Flow): ChatResponse {
  return reply(
    [
      `Thanks, ${firstName(f.name!)}. Our team will call you on ${f.phone} about **${f.reason}** during clinic hours.`,
    ],
    DONE,
  );
}

function leadTaken(f: Flow): ChatResponse {
  return reply([`Thanks, ${firstName(f.name!)}. Our team will contact you on ${f.phone}.`], DONE);
}

function rescheduled(f: Flow): ChatResponse {
  const to = f.time === 'any' ? `${fmtDate(f.date!)} (any time)` : whenText(f);
  return reply(
    [
      `Thanks, ${firstName(f.name!)}. Your request to move your appointment from **${fmtDate(f.bookedDate!)}** to **${to}** is received. Our team will contact you on ${f.phone} to confirm the new slot.`,
    ],
    DONE,
  );
}

function confirmed(f: Flow): ChatResponse {
  const when = f.time === 'any' ? `on ${fmtDate(f.date!)} (any time)` : `on ${whenText(f)}`;
  const text =
    f.kind === 'online'
      ? `Your online consultation request for **${treatmentText(f)}** ${when} is received. You will get the Google Meet link on WhatsApp and email once the clinic confirms.`
      : `Your appointment request for **${treatmentText(f)}** ${when} is received.`;
  return reply([text], DONE);
}

const menu = (client: string, text: string) => reply([text], client === 'CL01' ? MENU : null);

// ---------- steps ----------

// After a step is filled in: the next step, or back to the summary after a "Change ..." button.
function advance(f: Flow, next: Step): ChatResponse {
  f.step = f.backToSummary && next !== 'time' ? 'summary' : next;
  if (f.step === 'summary') f.backToSummary = false;
  return ask(f);
}

// Typed text while a step is open.
function typed(session: string, f: Flow, text: string, cc?: string): ChatResponse {
  const finish = (res: ChatResponse) => {
    sessions.set(session, null);
    return res;
  };
  const value = text.trim();
  switch (f.step) {
    case 'name':
      if (!validName(value))
        return reply(['Please enter your full name.'], null, { mode: 'text', placeholder: 'Your full name' });
      f.name = value.replace(/\s+/g, ' ');
      return advance(f, 'phone');
    case 'phone': {
      const phone = normalPhone(value, cc);
      if (!phone)
        return reply(['That number does not look right. Please check and enter it again.'], null, {
          mode: 'phone',
          placeholder: 'Mobile number',
        });
      f.phone = phone;
      if (f.kind === 'cancel' || f.kind === 'reschedule') return advance(f, 'booked_date');
      // A callback opened with a topic already has its reason.
      if (f.kind === 'callback') return f.reason ? finish(calledBack(f)) : advance(f, 'cb_reason');
      return advance(f, 'email');
    }
    case 'email':
      if (!validEmail(value))
        return reply(['Please enter a valid email address.'], null, {
          mode: 'email',
          placeholder: 'name@example.com',
        });
      f.email = value.toLowerCase();
      if (f.kind === 'question') return finish(leadTaken(f));
      return advance(f, 'treatment');
    case 'reason':
      if (value.length < 3)
        return reply(['Please add a few more words.'], null, { mode: 'text', placeholder: 'Short reason' });
      f.reason = value;
      return advance(f, 'date');
    case 'cb_reason':
      if (value.length < 3)
        return reply(['Please add a few more words.'], null, {
          mode: 'text',
          placeholder: 'Reason for the call',
        });
      f.reason = value;
      return finish(calledBack(f));
    default: {
      // A treatment typed by name is accepted; anything else asks the same step again (questions: piece 8d).
      const match = ARYA.treatments.find((t) => t.toLowerCase() === value.toLowerCase());
      if (f.step === 'treatment' && match) return pickTreatment(f, match);
      return ask(f);
    }
  }
}

function pickTreatment(f: Flow, treatment: string): ChatResponse {
  f.treatment = treatment;
  if (treatment === 'Other') {
    f.step = 'reason';
    return ask(f);
  }
  f.reason = undefined;
  return advance(f, 'date');
}

// Buttons that belong to the booking flow. Earlier pickers stay usable, so they work from any step.
function bookingButton(session: string, f: Flow, action: string, value: string): ChatResponse | null {
  switch (action) {
    case 'treatment':
      return ARYA.treatments.includes(value) ? pickTreatment(f, value) : ask(f);
    case 'booked_date':
      if (f.kind !== 'cancel' && f.kind !== 'reschedule') return ask(f);
      if (!validBookedDate(value)) return ask(f);
      f.bookedDate = value;
      if (f.kind === 'cancel') {
        sessions.set(session, null);
        return cancelled(f);
      }
      if (f.step === 'booked_date') f.step = 'date';
      return ask(f);
    case 'date':
      if (f.step === 'booked_date' || !bookable(value)) return ask(f);
      f.date = value;
      f.time = undefined;
      f.step = 'time';
      return ask(f);
    case 'time':
      if (!f.date || (value !== 'any' && !slotsFor(f.date).includes(value))) return ask(f);
      f.time = value;
      if (f.kind === 'reschedule') {
        sessions.set(session, null);
        return rescheduled(f);
      }
      return advance(f, 'summary');
    case 'change_treatment':
      f.step = 'treatment';
      f.backToSummary = true;
      return ask(f);
    case 'change_datetime':
      f.step = 'date';
      f.backToSummary = true;
      return ask(f);
    case 'switch_inclinic':
      f.kind = 'book';
      return advance(f, 'summary');
    case 'start_again':
      return start(session, f.kind);
    case 'confirm':
      return null; // handled by the caller, which ends the flow
  }
  return ask(f);
}

function start(session: string, kind: Kind, reason?: string, lead: string[] = []): ChatResponse {
  sessions.set(session, { kind, step: 'name', reason });
  return reply([...lead, INTRO[kind]], null, { mode: 'text', placeholder: 'Your full name' });
}

// ---------- entry ----------

export function handle(req: ChatRequest): ChatResponse {
  const client = req.client_id;
  const flow = sessions.get(req.session_id) ?? null;
  const { action = '', value = '' } = req.payload;

  if (req.event === 'start' || req.event === 'restart') {
    sessions.set(req.session_id, null);
    return menu(client, GREETING[client] ?? 'Hi, how can I help you today?');
  }
  if (client !== 'CL01') return reply([NO_ANSWER]);

  if (req.event === 'button') {
    // Main menu and every main card stop the current flow.
    if (action === 'menu') {
      sessions.set(req.session_id, null);
      return menu(client, 'How can I help you today?');
    }
    if (action === 'go') {
      sessions.set(req.session_id, null);
      return NODES[value] ?? reply([NO_ANSWER]);
    }
    if (
      action === 'start' &&
      (value === 'book' || value === 'online' || value === 'cancel' || value === 'reschedule')
    )
      return start(req.session_id, value);
    if (action === 'start' && value === 'callback') return start(req.session_id, 'callback');
    // A callback button with its topic, e.g. "Plan my treatment": the topic is the reason.
    if (action === 'callback') return start(req.session_id, 'callback', value || undefined);
    if (flow) {
      if (action === 'confirm' && flow.step === 'summary') {
        sessions.set(req.session_id, null);
        return confirmed(flow);
      }
      const res = bookingButton(req.session_id, flow, action, value);
      if (res) return res;
    }
    return menu(client, 'How can I help you today?');
  }

  // Typed text.
  const text = (req.payload.text ?? '').trim();
  if (flow) return typed(req.session_id, flow, text, req.payload.cc);
  // No answer for it: take a lead, with the question as the reason. (Answers from rules and the
  // knowledge base come in piece 8d; medical questions always end here.)
  return start(req.session_id, 'question', text, [NO_ANSWER]);
}
