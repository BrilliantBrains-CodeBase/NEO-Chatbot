// Typed text that means the same as a tap: dates, times, yes, main menu, and the labels of the
// buttons on screen (with typos). The real backend does the same with dateparser and rapidfuzz.
import type { Choice } from '../core/types';
import { addDays, weekday } from '../core/dates';

const norm = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

export const isMenu = (text: string) => /^(main menu|menu|home|start over|go to menu)$/.test(norm(text));
export const isYes = (text: string) =>
  /^(yes|y|yeah|yep|ok|okay|confirm|confirmed|confirm it|book it|go ahead|sure|done|correct)$/.test(
    norm(text),
  );

const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const DAYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];

function ymd(y: number, m: number, d: number): string | null {
  const date = new Date(Date.UTC(y, m - 1, d));
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== m - 1 || date.getUTCDate() !== d) return null;
  return date.toISOString().slice(0, 10);
}

// A date without a year is this year's, or next year's when that is closer (e.g. "2 Jan" in December).
function withYear(m: number, d: number, today: string): string | null {
  const year = Number(today.slice(0, 4));
  const thisYear = ymd(year, m, d);
  const nextYear = ymd(year + 1, m, d);
  if (!thisYear || !nextYear) return null;
  return thisYear >= addDays(today, -180) ? thisYear : nextYear;
}

const monthOf = (word: string) => MONTHS.indexOf(word.slice(0, 3)) + 1;

// "today", "tomorrow", "friday", "28 oct", "oct 28", "28/10", "28-10-2026", "2026-10-28". Day first (India).
export function parseDate(text: string, today: string): string | null {
  const t = norm(text);
  if (t === 'today') return today;
  if (t === 'tomorrow' || t === 'tmrw' || t === 'tmr') return addDays(today, 1);
  if (t === 'day after tomorrow') return addDays(today, 2);
  const wd = t.match(/^(?:next |this |on )?(sun|mon|tue|wed|thu|fri|sat)[a-z]*$/);
  if (wd) {
    const target = DAYS.indexOf(wd[1]);
    return addDays(today, (target - weekday(today) + 7) % 7);
  }
  let m = t.match(/^(\d{4}) (\d{1,2}) (\d{1,2})$/);
  if (m) return ymd(+m[1], +m[2], +m[3]);
  m = t.match(/^(\d{1,2}) (\d{1,2})(?: (\d{2}|\d{4}))?$/);
  if (m) {
    if (!m[3]) return withYear(+m[2], +m[1], today);
    const year = m[3].length === 2 ? 2000 + +m[3] : +m[3];
    return ymd(year, +m[2], +m[1]);
  }
  m = t.match(/^(\d{1,2})(?:st|nd|rd|th)?(?: of)? ([a-z]{3,9})(?: (\d{4}))?$/);
  if (m && monthOf(m[2]))
    return m[3] ? ymd(+m[3], monthOf(m[2]), +m[1]) : withYear(monthOf(m[2]), +m[1], today);
  m = t.match(/^([a-z]{3,9}) (\d{1,2})(?:st|nd|rd|th)?(?: (\d{4}))?$/);
  if (m && monthOf(m[1]))
    return m[3] ? ymd(+m[3], monthOf(m[1]), +m[2]) : withYear(monthOf(m[1]), +m[2], today);
  return null;
}

// "10:30", "10.30 am", "2 pm", "2:15pm", "14:15", "noon", "any time". Without am/pm, 1 to 8 means
// afternoon or evening (the clinic is closed at 1 to 8 AM). Returns HH:MM, or "any".
export function parseTime(text: string): string | null {
  const raw = text.toLowerCase().trim();
  if (/^(any ?time|anytime|any)$/.test(raw)) return 'any';
  if (raw === 'noon') return '12:00';
  const m = raw.match(/^(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?$/);
  if (!m) return null;
  let h = +m[1];
  const min = m[2] ? +m[2] : 0;
  const ampm = m[3]?.replace(/\./g, '');
  if (h > 23 || min > 59 || (ampm && (h < 1 || h > 12))) return null;
  if (ampm === 'pm' && h < 12) h += 12;
  if (ampm === 'am' && h === 12) h = 0;
  if (!ampm && h >= 1 && h <= 8) h += 12;
  return `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
}

function distance(a: string, b: string): number {
  const row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let prev = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cur = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = cur;
    }
  }
  return row[b.length];
}

// The button the patient meant: same label, a small typo (about 1 in 6 letters), or a part of the label
// (4+ letters) that fits only one button. Links (call, WhatsApp, website) are not matched.
export function matchOption(text: string, options: Choice[]): Choice | null {
  const t = norm(text);
  const usable = options.filter((o) => o.action);
  if (t.length < 2 || !usable.length) return null;
  const exact = usable.find((o) => norm(o.label) === t);
  if (exact) return exact;
  const close = usable.filter((o) => distance(norm(o.label), t) <= Math.max(1, Math.floor(t.length / 6)));
  if (close.length === 1) return close[0];
  if (t.length >= 4) {
    const part = usable.filter((o) => norm(o.label).includes(t));
    if (part.length === 1) return part[0];
  }
  return null;
}
