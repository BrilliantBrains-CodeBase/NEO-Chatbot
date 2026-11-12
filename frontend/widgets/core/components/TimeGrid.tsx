import { useState } from 'preact/hooks';
import type { TimeGridBlock } from '../types';
import { fmtTime } from '../dates';
import type { OnChoose } from './Blocks';
import t from '../i18n/en.json';

const ANY = 'any';

// Time slots, 4 per row (Arya mockup). The first few show with "Any time" and "More times";
// "More times" opens the rest. The backend sends only free slots, with past times already removed for today.
// Locked once its booking or reschedule is saved, like the calendar: an old time is never booked again.
export function TimeGrid({
  block,
  onChoose,
  locked = false,
}: {
  block: TimeGridBlock;
  onChoose: OnChoose;
  locked?: boolean;
}) {
  const [all, setAll] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const shown = all ? block.slots : block.slots.slice(0, block.first);

  const pick = (value: string, label: string) => {
    setPicked(value);
    onChoose({ label, action: block.action, value });
  };
  const cls = (value: string, extra = '') =>
    ['nb-chip', extra, picked === value ? 'sel' : ''].filter(Boolean).join(' ');

  return (
    <div class={locked ? 'nb-times nb-locked' : 'nb-times'} aria-disabled={locked}>
      {shown.map((hm) => (
        <button
          key={hm}
          type="button"
          class={cls(hm)}
          disabled={locked}
          onClick={() => pick(hm, fmtTime(hm))}
        >
          {fmtTime(hm)}
        </button>
      ))}
      {block.any_time && (
        <button
          type="button"
          class={cls(ANY, 'wide')}
          disabled={locked}
          onClick={() => pick(ANY, t.any_time)}
        >
          {t.any_time}
        </button>
      )}
      {!all && block.slots.length > block.first && (
        <button type="button" class="nb-chip wide more" disabled={locked} onClick={() => setAll(true)}>
          {t.more_times}
        </button>
      )}
    </div>
  );
}
