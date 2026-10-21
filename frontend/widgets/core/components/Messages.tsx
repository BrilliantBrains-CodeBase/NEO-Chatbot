import { useEffect, useRef } from 'preact/hooks';
import { Rich } from '../rich';

export interface Entry {
  id: number;
  from: 'bot' | 'me';
  text: string;
}

// The conversation: bot and patient bubbles, typing dots while waiting, kept scrolled to the newest message.
export function Messages({ entries, busy }: { entries: Entry[]; busy: boolean }) {
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Scroll the chat body only. scrollIntoView could also scroll the clinic's page.
    const body = end.current?.parentElement;
    if (body) body.scrollTop = body.scrollHeight;
  }, [entries, busy]);

  return (
    <>
      {entries.map((e) => (
        <div key={e.id} class={`nb-msg ${e.from}`}>
          {/* Patient text is shown as typed; only bot text may contain **bold**. */}
          {e.from === 'bot' ? <Rich text={e.text} /> : e.text}
        </div>
      ))}
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
