import { useState } from 'preact/hooks';
import { Icon } from '../icons';
import { COUNTRIES } from '../countries';
import type { InputMode } from '../types';
import t from '../i18n/en.json';

interface Props {
  mode: InputMode;
  placeholder: string;
  busy: boolean;
  // cc is the dial code, sent only in phone mode.
  onSend: (text: string, cc?: string) => void;
}

// Keyboard and autofill hints per mode, so phones show the right keyboard.
const FIELD: Record<InputMode, { type: string; inputMode: string; autocomplete: string }> = {
  text: { type: 'text', inputMode: 'text', autocomplete: 'off' },
  phone: { type: 'tel', inputMode: 'tel', autocomplete: 'tel-national' },
  email: { type: 'email', inputMode: 'email', autocomplete: 'email' },
};

// The typing bar. The patient can always type, even when buttons are shown.
// In phone mode a country code selector appears inside the bar (IN +91 by default, changeable).
export function Composer({ mode, placeholder, busy, onSend }: Props) {
  const [text, setText] = useState('');
  const [country, setCountry] = useState(0);
  const field = FIELD[mode];

  const submit = (e: Event) => {
    e.preventDefault();
    const value = text.trim();
    if (!value || busy) return;
    onSend(value, mode === 'phone' ? COUNTRIES[country][1] : undefined);
    setText('');
  };

  return (
    // noValidate: the backend checks the value and answers in the chat ("Please enter a valid email
    // address."). Without it the browser blocks the form with its own popup for type="email".
    <form class="nb-foot" onSubmit={submit} noValidate>
      {mode === 'phone' && (
        <select
          class="nb-cc"
          aria-label={t.country_code}
          value={country}
          onChange={(e) => setCountry(Number(e.currentTarget.value))}
        >
          {COUNTRIES.map(([iso, dial], i) => (
            <option key={iso} value={i}>
              {iso} {dial}
            </option>
          ))}
        </select>
      )}
      <input
        class="nb-in"
        type={field.type}
        inputMode={field.inputMode as 'text' | 'tel' | 'email'}
        autocomplete={field.autocomplete}
        value={text}
        placeholder={placeholder}
        aria-label={placeholder}
        maxLength={mode === 'phone' ? 20 : 500}
        onInput={(e) => setText(e.currentTarget.value)}
      />
      <button type="submit" class="nb-send" aria-label={t.send} disabled={busy || !text.trim()}>
        <Icon name="send" />
      </button>
    </form>
  );
}
