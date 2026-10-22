// The "regular" layer of the answering pipeline for typed text: keyword rules, in priority order.
// The real backend adds typo tolerance, the medical classifier, knowledge base search and the LLM.
import { TREATMENT_ALIASES, TREATMENT_INFO } from './arya';

export type Route =
  | { to: 'emergency' }
  | { to: 'lead' } // medical, or nothing matched: never answered, taken as a lead
  | { to: 'start'; kind: 'online' | 'cancel' | 'reschedule' | 'callback' }
  | { to: 'node'; key: string }
  | { to: 'card'; treatment: string };

const EMERGENCY =
  /\b(emergency|bleed(ing)?|faint(ed|ing)?|unconscious|can'?t breathe|breathing (problem|difficulty)|chest pain|allergic|anaphyla\w*|severe (swelling|pain)|high fever)\b/;

// Healthcare and medicine questions are never answered (client decision): they always become a lead.
const MEDICAL =
  /\b(medicines?|medication|tablets?|pills?|doses?|dosage|side ?effects?|safe for me|suitable for me|right for me|is it normal|minoxidil|finasteride|biotin|steroids?|diabet\w*|blood pressure|thyroid|pregnan\w*|pain(ful)?|itch(y|ing)?|rash|infection|swelling|diagnos\w*|symptoms?|cure)\b/;

const INTENTS: [RegExp, Route][] = [
  [/\b(online|video ?call|from home|google meet|virtual)\b/, { to: 'start', kind: 'online' }],
  [/\bcancel/, { to: 'start', kind: 'cancel' }],
  [
    /\b(reschedul\w*|postpone|change (my )?(appointment|booking|date|slot))\b/,
    { to: 'start', kind: 'reschedule' },
  ],
  [/\b(call ?back|callback)\b/, { to: 'start', kind: 'callback' }],
  [/\b(cost|price|fees?|charges?|package|emi|how much|rates?)\b/, { to: 'node', key: 'cost' }],
  [/\b(book\w*|appointment|consult\w*|slots?)\b/, { to: 'node', key: 'book' }],
  [/\b(results?|before and after|before after|gallery|photos?)\b/, { to: 'node', key: 'results' }],
  [
    /\b(timings?|hours|open|address|location|where|directions?|map|landmark)\b/,
    { to: 'node', key: 'clinic' },
  ],
  [/\b(call|whatsapp|contact|number|phone|talk)\b/, { to: 'node', key: 'talk' }],
  [/\b(doctors?|dr|sandeep|surgeons?)\b/, { to: 'node', key: 'about' }],
  [/\b(international|abroad|overseas|travel|fly|nri)\b/, { to: 'node', key: 'intl' }],
];

function treatmentIn(text: string): string | null {
  const byName = Object.keys(TREATMENT_INFO).find((name) => text.includes(name.toLowerCase()));
  if (byName) return byName;
  const alias = Object.keys(TREATMENT_ALIASES).find((a) => new RegExp(`\\b${a}\\b`).test(text));
  return alias ? TREATMENT_ALIASES[alias] : null;
}

export function route(raw: string): Route {
  const text = raw.toLowerCase().replace(/\s+/g, ' ').trim();
  if (EMERGENCY.test(text)) return { to: 'emergency' };
  if (MEDICAL.test(text)) return { to: 'lead' };
  for (const [re, target] of INTENTS) if (re.test(text)) return target;
  const treatment = treatmentIn(text);
  if (treatment) return { to: 'card', treatment };
  if (/\b(treatments?|explore|options|procedures?)\b/.test(text)) return { to: 'node', key: 'treat' };
  return { to: 'lead' };
}

// Saying no to a form question ("no", "skip", "not now"): the whole message, so "no 98..." is not caught.
export const REFUSAL =
  /^(no|nope|nah|na|no thanks|no thank you|not now|later|skip|cancel|stop|leave it|not interested|(i )?(don'?t|do not) want( to)?( share| give)?( it)?|nahi|nahin|nai|rehne do|mat)[.! ]*$/;

// Questions about the bot itself.
export const IDENTITY =
  /\b(who are you|what are you|who is this|who am i (talking|chatting) (to|with)|are you an? (bot|robot|human|real person|person|ai)|are you (a )?(bot|robot|human|real|ai)|what'?s your name|what is your name|your name)\b/;
