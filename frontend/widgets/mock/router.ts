// The "regular" layer of the answering pipeline for typed text: keyword rules, in priority order. Kept in step
// with the real backend (backend/app/chat/understand.py). The backend also has the approved knowledge base,
// meaning (semantic) matching and the approved example phrases, which need the database; the mock has none.
import { TREATMENT_ALIASES, TREATMENT_INFO } from './arya';
import { distance } from './typing';

export type Route =
  | { to: 'emergency' }
  | { to: 'lead' } // medical, or nothing matched: never answered, a call back is offered
  | { to: 'start'; kind: 'book' | 'online' | 'cancel' | 'reschedule' | 'callback' }
  | { to: 'node'; key: string }
  | { to: 'card'; treatment: string };

const EMERGENCY =
  /\b(emergency|bleed(ing)?|faint(ed|ing)?|unconscious|can'?t breathe|breathing (problem|difficulty)|chest pain|allergic|anaphyla\w*|severe (swelling|pain)|high fever)\b/;

// Healthcare and medicine questions are never answered (client decision): pain, medicines, suitability,
// aftercare, the cause of the patient's problem or whether it is normal.
const AFTER = '(after|before) (the |my |a )?(surgery|transplant|procedure|prp|gfc|treatment|session)';
const CARE =
  '(alcohol|drink\\w*|smok\\w*|wash\\w*|shampoo\\w*|gym|exercise|workout|swim\\w*|helmet|sleep\\w*|diet|sex)';
export const MEDICAL = new RegExp(
  '\\b(medicines?|medication|tablets?|pills?|doses?|dosage|side ?effects?|safe for me|suitab\\w*|candidate|' +
    'eligib\\w*|how many grafts|right for me|is it normal|minoxidil|finasteride|biotin|steroids?|diabet\\w*|' +
    'blood pressure|thyroid|pregnan\\w*|pain(ful)?|itch(y|ing)?|rash|infection|swelling|diagnos\\w*|symptoms?|' +
    'cure[ds]?|hurts?|hurting|risks?|why (is|are|am|do|does|did) (my|i)|is (my|this|it) [a-z ]{0,25}normal|' +
    'should i (get|go for|take|do|use|try)|should i choose (?!you|your|neo|this clinic)|' +
    'do i need (a |an )?(transplant|surgery|prp|gfc|qr678|exosomes?|treatment|grafts?)|' +
    '(best|better|right) for me|which (one|treatment) (is|should)|' +
    'which (shampoo|oil|serum|vitamins?|supplements?) should|' +
    `${CARE}\\b.*\\b${AFTER}|${AFTER}\\b.*\\b${CARE})\\b`,
);

// Services a hair clinic does not offer: a clear reply, never a lookalike answer ("laser hair removal").
export const NOT_OFFERED =
  /\b(hair removal|laser removal|botox|fillers?|tattoo removal|skin whitening|skin lightening|skin pigmentation|acne|pimples?|chemical peel|facials?|hydrafacial|teeth|dental|weight loss|liposuction|rhinoplasty|nose job|breast)\b/;

// The cost options of the cost menu, when the patient names their pattern with the cost question.
const COST_OPTIONS: [string, RegExp][] = [
  ['cost_beard', /\b(beard|eyebrows?|moustache|mustache)\b/],
  [
    'cost_front_crown',
    /\b(front|hairline)\b.*\b(crown|top|back of (my |the )?head)\b|\b(crown|top)\b.*\bfront\b|\bboth\b/,
  ],
  ['cost_crown', /\b(crown|vertex|top of (my |the )?head|bald (spot|patch) (on|at) (the )?(top|crown))\b/],
  ['cost_receding', /\b(receding|hairline|temples?|forehead)\b/],
  ['cost_advanced', /\b(completely bald|fully bald|very (little|less) hair|no hair|advanced|full head)\b/],
];

const INTENTS: [RegExp, Route][] = [
  // "online" alone is not a video consultation: "estimate online", "online hair test" are other things.
  [
    /^(?!.*\b(estimates?|calculator|cost|price|assessment|analysis|test|brochure)\b).*\b(online|video( ?call| consult\w*)?|from home|google meet|virtual)\b/,
    { to: 'start', kind: 'online' },
  ],
  [/\bcancel/, { to: 'start', kind: 'cancel' }],
  [
    /\b(reschedul\w*|postpone|(change|move|shift|push) (my |the )?(appointment|booking|date|slot|visit))\b/,
    { to: 'start', kind: 'reschedule' },
  ],
  [
    /\b(call ?back|callback|call me back|exact (quote|price|cost)|get a quote|quotation)\b/,
    { to: 'start', kind: 'callback' },
  ],
  [
    /\b(cost|price|fees?|charges?|package|emi|how much|rates?|kharcha|lagega|kitna (hoga|paisa|lagta)|kitne (ka|ki|ke|paise|rupaye))\b/,
    { to: 'node', key: 'cost' },
  ],
  // A clear wish to book starts the in-clinic booking at once; "consultation" alone may be a question.
  [
    /\b(book\w*|appointment|slots?|(want|like|need|can i|could i|may i) (to )?(come in|come to the clinic|visit|get checked|see the doctor|meet the doctor))\b/,
    { to: 'start', kind: 'book' },
  ],
  [/\bconsult\w*\b/, { to: 'node', key: 'book' }],
  // Photos to be checked or sent are not the results gallery.
  [
    /^(?!.*\b(check|assess\w*|analy\w*|send|share|upload|privacy|private)\b).*\b(results?|before and after|before after|gallery|photos?|videos?)\b/,
    { to: 'node', key: 'results' },
  ],
  [
    /\b(timings?|hours|open|opening|closed?|address|adres+|location|where|directions?|map|landmark|kahan|floor|pin ?code|holiday|weekly off|working days|kitne baje|khul\w*|band (hota|hoti|rehta))\b/,
    { to: 'node', key: 'clinic' },
  ],
  // "talk in kannada", "gst number" are not a wish to call: only contact words and asking to talk to us.
  [
    /\b(call( me)?|whatsapp|contact|(phone|mobile|contact|clinic|your|whatsapp) (number|no)|phone|(talk|speak) (to|with) (someone|a human|a person|the team|your team|you|the doctor|doctor))\b/,
    { to: 'node', key: 'talk' },
  ],
  [/\b(doctors?|dr|sandeep|surgeons?)\b/, { to: 'node', key: 'about' }],
  [/\b(international|abroad|overseas|travel|fly|nri)\b/, { to: 'node', key: 'intl' }],
];

// Long action words patients often misspell. Only words of 7+ letters, so "cancer" never becomes "cancel".
const SPELLED = [
  'reschedule',
  'appointment',
  'consultation',
  'emergency',
  'treatment',
  'transplant',
  'location',
  'callback',
  'postpone',
  'timings',
];
const CANCEL_TYPOS = /\b(cancle|cansel|cancell|cancl|cencel|cancal)\b/g;

export function spelled(text: string): string {
  return text
    .replace(CANCEL_TYPOS, 'cancel')
    .split(' ')
    .map((w) => {
      if (w.length < 7 || SPELLED.includes(w)) return w;
      const near = SPELLED.filter((s) => distance(w, s) <= (w.length < 9 ? 1 : 2));
      return near.length === 1 ? near[0] : w;
    })
    .join(' ');
}

// The treatment a message names, with the words that named it.
export function treatmentIn(text: string): { name: string; words: string } | null {
  const byName = Object.keys(TREATMENT_INFO).find((name) => text.includes(name.toLowerCase()));
  if (byName) return { name: byName, words: byName.toLowerCase() };
  for (const alias of Object.keys(TREATMENT_ALIASES)) {
    const m = text.match(new RegExp(`\\b${alias}\\b`));
    if (m) return { name: TREATMENT_ALIASES[alias], words: m[0] };
  }
  return null;
}

export function route(raw: string): Route {
  const text = spelled(raw.toLowerCase().replace(/\s+/g, ' ').trim());
  if (EMERGENCY.test(text)) return { to: 'emergency' };
  if (MEDICAL.test(text)) return { to: 'lead' };
  for (const [re, target] of INTENTS) {
    if (!re.test(text)) continue;
    if (target.to === 'node' && target.key === 'cost') {
      const exact = COST_OPTIONS.find(([, p]) => p.test(text));
      if (exact) return { to: 'node', key: exact[0] };
    }
    return target;
  }
  const treatment = treatmentIn(text);
  if (treatment) return { to: 'card', treatment: treatment.name };
  if (/\b(treatments?|explore|options|services)\b/.test(text)) return { to: 'node', key: 'treat' };
  return { to: 'lead' };
}

// Saying no to a form question ("no", "skip", "not now"): the whole message, so "no 98..." is not caught.
export const REFUSAL =
  /^(no|nope|nah|na|no thanks|no thank you|not now|later|skip|cancel|stop|leave it|not interested|(i )?(don'?t|do not) want( to)?( share| give)?( it)?|nahi|nahin|nai|rehne do|mat)[.! ]*$/;

// Questions about the bot itself.
export const IDENTITY =
  /\b(who are you|what are you|who is this|who am i (talking|chatting) (to|with)|are you an? (bot|robot|human|real person|person|ai)|are you (a )?(bot|robot|human|real|ai)|what'?s your name|what is your name|your name|(human|person|bot|robot|ai|machine|real)( or | ya |\/)(human|person|bot|robot|ai|machine|real)|(is this|am i (talking|chatting|speaking) (to|with)) (an? )?(bot|robot|human|real person|person|ai|machine)|(real|actual) (person|human)|chatbot)\b/;

// Words no name has: at the name step, "clinic location" is a question, not a patient called "Clinic".
export const NOT_A_NAME =
  /\b(clinic|location|address|where|what|when|why|how|which|timings?|hours|open|cost|price|fees?|charges?|emi|book\w*|appointment|consult\w*|treatments?|transplant|hair|prp|gfc|beard|eyebrows?|doctor|parking|results?|offer|available|tell|more|info|details?|help|menu|call|number|phone|whatsapp|need|want)\b/;

// Asking for every treatment ("more treatments", "list of your services"), not their cost.
export const ALL_TREATMENTS =
  /^(?!.*\b(cost|price|fees?|charges?)\b).*(\b(all|more|other|full|complete|entire|rest of( the)?)\b[a-z ]{0,20}\b(treatments?|services|procedures)\b|\blist of (treatments?|services|procedures)\b|\bhow many (treatments?|services)\b)/;
// Asking whether a list is complete ("only 4 or more?", "is that all?"): about the last list.
export const MORE_OF_LIST =
  /^(only (\d+|these|this|that|four|five)|(is|are) (that|these|this) (all|it|the only)|that'?s all|any (more|others?)|(\d+|four|five) (only|or more))\b|\bor more\W*$/;

// Small talk: the whole message only, so "hi, what does PRP cost?" is still a question.
const SMALL_TALK: [string, RegExp][] = [
  [
    'greeting',
    /^(hi+|hey+|hello+|helo|hlo|namaste|namaskar|good (morning|afternoon|evening))( there| arya)?[!. ]*$/,
  ],
  [
    'thanks',
    /^(thanks?|thank (you|u)|thx|ty|dhanyavad|shukriya|great thanks)( a lot| so much| very much)?[!. ]*$/,
  ],
  ['bye', /^(bye+|bye bye|good ?bye|see (you|ya)|take care|tata)[!. ]*$/],
  ['ok', /^(ok+|okay|fine|cool|alright|got it|hmm+|sure|great|nice)[!. ]*$/],
];

export const smallTalk = (text: string) => SMALL_TALK.find(([, re]) => re.test(text))?.[0] ?? null;
