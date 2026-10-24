// Mock backend: answers like the real FastAPI backend will, using the contract in core/types.ts.
// Used by the dev playground and the Playwright tests only; it is never part of a clinic's widget file.
// Arya (CL01) has the full flows; Navya and Diya only greet until their faces are built.
import type { ChatRequest, ChatResponse, Choice, UiBlock } from '../core/types';
import { addDays, fmtDate, fmtTime, weekday } from '../core/dates';
import { ARYA, BOOKING_OPTION, BRIEF, MENU, NODES, TREATMENT_INFO, TYPE, treatmentCard } from './arya';
import {
  ALL_TREATMENTS,
  IDENTITY,
  MORE_OF_LIST,
  NOT_A_NAME,
  NOT_OFFERED,
  REFUSAL,
  route,
  smallTalk,
  treatmentIn,
} from './router';
import { isMenu, isYes, matchOption, parseDate, parseTime } from './typing';

const GREETING: Record<string, string> = {
  CL01: ARYA.greeting,
  CL02: "Hi, I'm Navya, Neo Fertility's AI assistant. How can I help you today?",
  CL03: "Hi, I'm Diya, Derma Solutions' AI assistant. How can I help you today?",
};

// Nothing known: a call back is offered first; the form starts only on yes (same as the real backend).
const NO_ANSWER =
  "I don't have a confirmed answer for that yet. Would you like our team to call you back with the right information?";
const OFFER_UI: UiBlock = {
  type: 'chips',
  options: [
    { label: 'Yes, call me back', action: 'ask_team', primary: true },
    { label: 'No, thanks', action: 'menu' },
  ],
};
// A service the clinic does not offer. Never names another clinic.
const NOT_OFFERED_SHORT = "We focus on hair and scalp treatments, so this isn't something we offer here.";
const NOT_OFFERED_TEXT = `${NOT_OFFERED_SHORT} Would you like our team to call you back?`;
const WHICH = 'Sure. Which one would you like to know more about?';
const STOPPED = 'No problem. How else can I help you?';
// A question typed in the middle of a flow that has no answer: noted for the team, then the step continues.
const NOTED = "I don't have a confirmed answer for that yet. I have noted your question for our team.";
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
  questions?: string[]; // typed mid-flow without an answer; the real backend saves them on the lead
  reason?: string; // Other: what they are looking for. Callback: the topic. Question: what they typed.
  bookedDate?: string; // cancel and reschedule: the date of the existing booking
  date?: string; // YYYY-MM-DD
  time?: string; // HH:MM or "any"
}

const sessions = new Map<string, Flow | null>();

// What the bot remembers of the chat (C1): its last reply's buttons, the treatment talked about in the last
// turn, and a question waiting for "would you like our team to call you back?".
interface Memory {
  lastUi: UiBlock | null;
  topicNow: string | null;
  pendingQ: string | null;
}
const memory = new Map<string, Memory>();
// Set while one turn is worked out (handle is synchronous), then saved in memory.
let turn: { topic: string | null; pending: string | null } = { topic: null, pending: null };

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

// Typed text with no flow open: rules decide; nothing matched (or medical): a call back is offered.
function answer(session: string, text: string): ChatResponse {
  const r = route(text);
  switch (r.to) {
    case 'emergency':
      return NODES.emergency;
    case 'start':
      return startTyped(session, r.kind, text);
    case 'node':
      return NODES[r.key];
    case 'card':
      return treatmentCard(r.treatment)!;
    case 'lead':
      turn.pending = text;
      return reply([NO_ANSWER], OFFER_UI);
  }
}

// A flow started by typing. A booking that names a treatment ("book for PRP") starts with it filled in.
function startTyped(session: string, kind: Kind, text: string): ChatResponse {
  const named = kind === 'book' ? treatmentIn(text.toLowerCase()) : null;
  if (named) {
    const option = ARYA.treatments.includes(named.name) ? named.name : BOOKING_OPTION[named.name];
    return start(session, 'book', undefined, [], option);
  }
  return start(session, kind);
}

// ---------- the chat so far (C1) ----------

const VAGUE =
  /^((i )?(want|need|would like)( to (know|see|hear))? more( (info|information|details?|about it))?|(tell|show|give) me more( (info|information|details?|about (it|this|that)))?|more( please| pls| info| information| details?)?|(any )?(more|other|another) (options?|ones?)|(something|anything) else|what else|others?|explain( (it|this|that|more))?|details?( please| pls)?|go on|continue|and( then)?|aur( batao| bataiye| bolo)?|aur kuch|detail (me|mein) batao|samjhao)$/;
const isVague = (text: string) =>
  VAGUE.test(
    text
      .toLowerCase()
      .replace(/\s+/g, ' ')
      .replace(/[?.! ]+$/, '')
      .trim(),
  );

const buttonsOf = (ui: UiBlock | null | undefined): Choice[] =>
  choicesOf({ messages: [], ui: ui ?? null, input: TYPE });

// Whether a reply's buttons were a list of treatments (the treatments menu or one of its groups).
const aboutTreatments = (ui: UiBlock | null | undefined) =>
  buttonsOf(ui).some(
    (o) => o.action === 'treat' || (o.action === 'go' && ['treat', 'ht', 'hf'].includes(o.value ?? '')),
  );

// Every treatment the clinic offers, by group, built from its own treatment buttons.
function allTreatments(): ChatResponse {
  const lines: string[] = [];
  const alone: string[] = [];
  let count = 0;
  for (const o of buttonsOf(NODES.treat.ui)) {
    const group = o.action === 'go' ? buttonsOf(NODES[o.value ?? '']?.ui) : [];
    const names = group.filter((x) => x.action === 'treat').map((x) => x.value!);
    if (names.length) {
      lines.push(`**${o.label}:** ${names.join(', ')}`);
      count += names.length;
    } else if (o.action === 'treat') alone.push(o.value!);
  }
  if (alone.length) {
    lines.push(`**Also:** ${alone.join(', ')}`);
    count += alone.length;
  }
  const text = `We offer ${count} treatments:\n${lines.join('\n')}\nTap a group or type a treatment to learn more.`;
  return reply([text], NODES.treat.ui);
}

// "Tell me more" after a treatment: what about it.
function topicMore(topic: string): ChatResponse {
  const site = buttonsOf(treatmentCard(topic)?.ui).find((o) => o.href);
  return reply([`What would you like to know about **${topic}**?`], {
    type: 'chips',
    options: [
      { label: 'Cost', action: 'ask', value: `cost of ${topic}` },
      { label: `Book for ${topic}`, action: 'book_for', value: topic, primary: true },
      { label: 'Ask our team', action: 'callback', value: `Question about ${topic}` },
      ...(site ? [{ label: 'Read more on our website', href: site.href }] : []),
    ],
    main: true,
  });
}

// "Tell me more", "something else": read from the bot's last reply what "more" is about.
function vague(f: Flow | null, mem: Memory | undefined): ChatResponse {
  if (f) return ask(f); // a booking is open: its step again
  const last = mem?.lastUi ?? null;
  if (aboutTreatments(last)) return allTreatments();
  const topic = mem?.topicNow;
  const isCard = buttonsOf(last).some((o) => o.action === 'book_for');
  const choices = buttonsOf(last).filter((o) => o.action !== 'menu');
  if (topic && TREATMENT_INFO[topic] && (isCard || !choices.length || last?.type === 'menu'))
    return topicMore(topic);
  if (choices.length) return reply([WHICH], last);
  return menu('CL01', 'How can I help you today?');
}

// A question typed in the middle of a flow: answered briefly (or noted), then the same step is asked
// again with everything entered so far kept. An emergency, or asking for another flow, takes over.
function midFlow(session: string, f: Flow, text: string): ChatResponse {
  const r = route(text);
  if (r.to === 'emergency') {
    sessions.set(session, null);
    return NODES.emergency;
  }
  if (r.to === 'start' && r.kind !== f.kind) return startTyped(session, r.kind, text);
  if (r.to === 'node' && BRIEF[r.key]) return ask(f, [BRIEF[r.key]]);
  if (r.to === 'card') return ask(f, [`**${r.treatment}**\n${TREATMENT_INFO[r.treatment].text}`]);
  if (r.to === 'node' && r.key === 'book') return ask(f);
  (f.questions ??= []).push(text);
  return ask(f, [NOTED]);
}

const INPUT_STEPS: Step[] = ['name', 'phone', 'email', 'reason', 'cb_reason'];

// Typed text while a step is open.
function typed(session: string, f: Flow, text: string, cc?: string): ChatResponse {
  const finish = (res: ChatResponse) => {
    sessions.set(session, null);
    return res;
  };
  const value = text.trim();
  // At a typing step the text is the answer, unless it is an emergency or clearly a question. At the name step,
  // words no name has ("clinic location") make it a question too.
  const question = value.includes('?') || (f.step === 'name' && NOT_A_NAME.test(value.toLowerCase()));
  if (INPUT_STEPS.includes(f.step) && (question || route(value).to === 'emergency')) {
    return midFlow(session, f, value);
  }
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
      // Booked from a treatment card: the treatment is already chosen.
      return advance(f, f.treatment ? 'date' : 'treatment');
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
      // A treatment typed by name is accepted; anything else at a picker step is a question.
      const match = ARYA.treatments.find((t) => t.toLowerCase() === value.toLowerCase());
      if (f.step === 'treatment' && match) return pickTreatment(f, match);
      return midFlow(session, f, value);
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
      if (f.step === 'booked_date') return ask(f);
      if (!bookable(value)) return ask(f, [NOT_AVAILABLE_DATE]); // e.g. fully booked since it was shown
      f.date = value;
      f.time = undefined;
      f.step = 'time';
      return ask(f);
    case 'time':
      if (!f.date) return ask(f);
      if (value !== 'any' && !slotsFor(f.date).includes(value)) return ask(f, [NOT_AVAILABLE_TIME]); // just taken
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

function start(
  session: string,
  kind: Kind,
  reason?: string,
  lead: string[] = [],
  treatment?: string,
): ChatResponse {
  sessions.set(session, { kind, step: 'name', reason, treatment });
  return reply([...lead, INTRO[kind]], null, { mode: 'text', placeholder: 'Your full name' });
}

// ---------- typed text that means a tap ----------

// The buttons on screen after the last reply, per session, so typed text can stand for a tap.
const shown = new Map<string, Choice[]>();

function choicesOf(res: ChatResponse): Choice[] {
  const ui = res.ui;
  if (!ui || (ui.type !== 'menu' && ui.type !== 'chips' && ui.type !== 'doctor_card')) return [];
  if (ui.type === 'menu') return ui.items;
  return [
    ...ui.options,
    ...(ui.back ? [{ ...ui.back, label: 'Back' }] : []),
    ...(ui.main ? [{ label: 'Main menu', action: 'menu' }] : []),
  ];
}

const THANKS = "You're welcome! Is there anything else I can help you with?";
const BYE = 'Thank you for chatting with us. Take care!';
const NOT_AVAILABLE_DATE = 'That date is not available. Please choose another date.';
const NOT_AVAILABLE_TIME = 'That time is not available. Please choose one of the times shown.';

// A tap the typed text stands for, a reply when it names a date or time that cannot be booked, or
// null to handle it as text. Emergencies always go the normal way, so they are never mistaken for a tap.
function typedTap(
  session: string,
  f: Flow | null,
  text: string,
): ChatRequest['payload'] | ChatResponse | null {
  if (route(text).to === 'emergency') return null;
  if (isMenu(text)) return { action: 'menu' };
  if (f && (f.step === 'date' || f.step === 'booked_date')) {
    const day = parseDate(text, ist().today);
    if (day) {
      const ok = f.step === 'date' ? bookable(day) : validBookedDate(day);
      return ok ? { action: f.step, value: day } : ask(f, [NOT_AVAILABLE_DATE]);
    }
  }
  if (f && f.step === 'time' && f.date) {
    const time = parseTime(text);
    if (time) {
      const ok = time === 'any' || slotsFor(f.date).includes(time);
      return ok ? { action: 'time', value: time } : ask(f, [NOT_AVAILABLE_TIME]);
    }
  }
  if (f && f.step === 'summary' && isYes(text)) return { action: 'confirm' };
  const option = matchOption(text, shown.get(session) ?? []);
  return option ? { action: option.action, value: option.value } : null;
}

// ---------- entry ----------

export function handle(req: ChatRequest): ChatResponse {
  turn = { topic: null, pending: null };
  const res = respond(req);
  shown.set(req.session_id, choicesOf(res));
  memory.set(req.session_id, { lastUi: res.ui ?? null, topicNow: turn.topic, pendingQ: turn.pending });
  return res;
}

function respond(req: ChatRequest): ChatResponse {
  const client = req.client_id;
  const flow = sessions.get(req.session_id) ?? null;
  const mem = memory.get(req.session_id);
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
    if (action === 'treat') {
      sessions.set(req.session_id, null);
      turn.topic = value;
      return treatmentCard(value) ?? menu(client, 'How can I help you today?');
    }
    // Yes to "would you like our team to call you back?": the form, with the question as the reason.
    if (action === 'ask_team')
      return start(req.session_id, 'question', mem?.pendingQ ?? 'Asked our team a question');
    // A button that asks a question ("Cost" after a treatment): as if typed.
    if (action === 'ask' && value) return respond({ ...req, event: 'text', payload: { text: value } });
    // Book for <treatment>: the matching booking option is preselected; without one the step is asked.
    if (action === 'book_for') {
      turn.topic = value;
      const option = ARYA.treatments.includes(value) ? value : BOOKING_OPTION[value];
      return start(req.session_id, 'book', undefined, [], option);
    }
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

  // Typed text. First: does it stand for a tap (a button on screen, a date, a time, yes, menu)?
  const text = (req.payload.text ?? '').trim();
  const low = text.toLowerCase().replace(/\s+/g, ' ');
  if (route(text).to !== 'emergency') {
    // "no" to a form question ends the form; nothing is saved.
    if (flow && INPUT_STEPS.includes(flow.step) && REFUSAL.test(low)) {
      sessions.set(req.session_id, null);
      return menu(client, 'No problem. How else can I help you?');
    }
    // A service the clinic does not offer: a clear reply, never a lookalike answer.
    if (NOT_OFFERED.test(low) && !(flow && INPUT_STEPS.includes(flow.step))) {
      if (flow) return ask(flow, [NOT_OFFERED_SHORT]);
      turn.pending = text;
      return reply([NOT_OFFERED_TEXT], OFFER_UI);
    }
    // Another request while a form is open ("reschedule my appointment" while cancelling): switch to it.
    // One word switches only when it is a clear action; "Online" alone may be a name.
    const r = route(text);
    if (flow && ['name', 'phone', 'email'].includes(flow.step) && r.to === 'start' && r.kind !== flow.kind) {
      if (low.split(' ').length > 1 || r.kind === 'cancel' || r.kind === 'reschedule')
        return startTyped(req.session_id, r.kind, text);
    }
    if (IDENTITY.test(low)) return flow ? ask(flow, [ARYA.greeting]) : menu(client, ARYA.greeting);
  }
  const tap = typedTap(req.session_id, flow, text);
  if (tap && 'messages' in tap) return tap;
  if (tap) return respond({ ...req, event: 'button', payload: tap });
  turn.topic = treatmentIn(low)?.name ?? null;
  if (mem?.pendingQ && !flow) {
    // Typed answer to "would you like our team to call you back?".
    if (isYes(text)) return respond({ ...req, event: 'button', payload: { action: 'ask_team' } });
    if (REFUSAL.test(low)) return menu(client, STOPPED);
  }
  const inForm = !!flow && INPUT_STEPS.includes(flow.step);
  if (!inForm && (ALL_TREATMENTS.test(low) || (MORE_OF_LIST.test(low) && aboutTreatments(mem?.lastUi)))) {
    const all = allTreatments(); // "more treatments", "only 4 or more?"
    return flow ? ask(flow, [all.messages[0].text]) : all;
  }
  if (!inForm && isVague(text)) return vague(flow, mem);
  const chat = smallTalk(low);
  if (chat && !(flow && INPUT_STEPS.includes(flow.step))) {
    const said = { greeting: ARYA.greeting, thanks: THANKS, bye: BYE, ok: 'How can I help you today?' }[
      chat
    ]!;
    if (flow) return ask(flow, chat === 'ok' ? [] : [said]); // a booking stays open: the same step again
    return menu(client, said);
  }
  if (flow) return typed(req.session_id, flow, text, req.payload.cc);
  return answer(req.session_id, text);
}
