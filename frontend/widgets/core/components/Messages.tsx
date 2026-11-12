import { useEffect, useRef } from 'preact/hooks';
import { Rich } from '../rich';
import type { UiBlock } from '../types';
import { Block, type OnChoose } from './Blocks';
import t from '../i18n/en.json';

export type Entry =
  // error: a request failed; the bubble offers "Try again".
  | { id: number; from: 'bot' | 'me'; text: string; error?: boolean }
  // locked: a calendar or time grid of a booking, cancel or reschedule that is finished (never tapped again).
  | { id: number; from: 'ui'; block: UiBlock; locked?: boolean };

interface Props {
  entries: Entry[];
  busy: boolean;
  onRetry: () => void;
  onChoose: OnChoose;
}

// The conversation: bubbles, blocks (menu, buttons, pickers), typing dots, kept scrolled to the newest item.
export function Messages({ entries, busy, onRetry, onChoose }: Props) {
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Scroll the chat body only. scrollIntoView could also scroll the clinic's page.
    const body = end.current?.parentElement;
    if (body) body.scrollTop = body.scrollHeight;
  }, [entries, busy]);

  return (
    <>
      {entries.map((e, i) =>
        e.from === 'ui' ? (
          <Block
            key={e.id}
            block={e.block}
            onChoose={onChoose}
            answered={entries.slice(i + 1).some((x) => x.from === 'me')}
            locked={e.locked}
          />
        ) : (
          <div key={e.id} class={`nb-msg ${e.from}`}>
            {/* Patient text is shown as typed; only bot text may contain **bold**. */}
            {e.from === 'bot' ? <Rich text={e.text} /> : e.text}
            {e.error && (
              <button type="button" class="nb-retry" onClick={onRetry} disabled={busy}>
                {t.try_again}
              </button>
            )}
          </div>
        ),
      )}
      {busy && (
        <div class="nb-msg bot nb-typing" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      )}
      <div ref={end} />
    </>
  );
}
