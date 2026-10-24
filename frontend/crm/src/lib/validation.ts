// Form rules of the sign-in design (same messages), shared by its forms.

export const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
export const INDIAN_MOBILE = /^[6-9]\d{9}$/;

/** Password strength 0-4: 8+ characters, a capital, a number, a symbol. 3 or more is accepted. */
export function passwordScore(p: string): number {
  let s = 0;
  if (p.length >= 8) s++;
  if (/[A-Z]/.test(p)) s++;
  if (/[0-9]/.test(p)) s++;
  if (/[^A-Za-z0-9]/.test(p)) s++;
  return s;
}

export const STRENGTH_COLOR = ["#C62828", "#C62828", "#B26A00", "#3E6FD9", "#1F8A4C"];
export const STRENGTH_HINT = [
  "Use 8+ characters with a number and a capital letter.",
  "Too weak",
  "Fair",
  "Good",
  "Strong",
];

export type Errors<K extends string> = Partial<Record<K, string>>;
