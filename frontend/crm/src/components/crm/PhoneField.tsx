"use client";

import { COUNTRY_CODES } from "@/lib/countries";

// A phone number as the backend stores it (+919876543210): a country code list and the number. The same
// rule as the chatbot: India 10 digits starting 6 to 9, other countries 6 to 12 digits.

const BY_LENGTH = [...COUNTRY_CODES].sort((a, b) => b.code.length - a.code.length);

function split(value: string): { code: string; digits: string } {
  const found = BY_LENGTH.find((c) => value.startsWith(c.code));
  return found ? { code: found.code, digits: value.slice(found.code.length) } : { code: "+91", digits: value.replace(/^\+/, "") };
}

/** The number to save: null when only a country code is chosen. */
export function phoneValue(value: string): string | null {
  return split(value).digits ? value : null;
}

/** A message when the number is not right, or "" (an empty number is fine). */
export function phoneError(value: string): string {
  const { code, digits } = split(value);
  if (!digits) return "";
  const ok = code === "+91" ? /^[6-9]\d{9}$/.test(digits) : /^\d{6,12}$/.test(digits);
  return ok ? "" : "That number does not look right. Please check it.";
}

export default function PhoneField({
  value,
  onChange,
  disabled,
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  label: string;
}) {
  const { code, digits } = split(value);
  return (
    <span className="st-phone">
      <select
        className="f"
        aria-label={`${label}: country code`}
        value={code}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value + digits)}
      >
        {COUNTRY_CODES.map((c) => (
          <option key={c.code} value={c.code}>
            {c.label}
          </option>
        ))}
      </select>
      <input
        className="f"
        type="tel"
        inputMode="numeric"
        aria-label={label}
        placeholder="Mobile number"
        maxLength={12}
        value={digits}
        disabled={disabled}
        onChange={(e) => onChange(code + e.target.value.replace(/\D/g, ""))}
      />
    </span>
  );
}
