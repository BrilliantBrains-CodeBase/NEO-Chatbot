// Calendar dates as YYYY-MM-DD strings, computed in UTC so the browser's own time zone never shifts a day.

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

export const toUtc = (ymd: string) => new Date(ymd + 'T00:00:00Z');
export const ymdOf = (d: Date) => d.toISOString().slice(0, 10);
export const addDays = (ymd: string, n: number) => ymdOf(new Date(toUtc(ymd).getTime() + n * 86400000));
export const weekday = (ymd: string) => toUtc(ymd).getUTCDay();

// "2026-10-17" -> "17 Oct 2026"
export function fmtDate(ymd: string): string {
  const d = toUtc(ymd);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

// "14:30" -> "2:30 PM"
export function fmtTime(hm: string): string {
  const [h, m] = hm.split(':').map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
}
