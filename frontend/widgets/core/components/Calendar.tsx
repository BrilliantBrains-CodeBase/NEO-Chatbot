import { useState } from 'preact/hooks';
import type { CalendarBlock } from '../types';
import { MONTH_NAMES, addDays, fmtDate, toUtc, weekday } from '../dates';
import { Icon } from '../icons';
import type { OnChoose } from './Blocks';
import t from '../i18n/en.json';

const WEEK = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
const monthKey = (ymd: string) => ymd.slice(0, 7); // "2026-10"

// Month calendar. The backend sends the clinic's today, the first and last allowed date and the closed
// weekdays, so dates never depend on the patient's own clock or time zone. It stays usable after a pick,
// so the date can still be changed while the times show.
export function Calendar({ block, onChoose }: { block: CalendarBlock; onChoose: OnChoose }) {
  const start = block.today < block.min ? block.min : block.today > block.max ? block.max : block.today;
  const [view, setView] = useState(monthKey(start));
  const [picked, setPicked] = useState<string | null>(null);

  const first = view + '-01';
  const lead = weekday(first);
  const d = toUtc(first);
  const daysInMonth = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate();
  const shift = (n: number) =>
    setView(monthKey(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + n, 1)).toISOString()));

  const open = (ymd: string) =>
    ymd >= block.min && ymd <= block.max && !block.closed_weekdays.includes(weekday(ymd));

  return (
    <div class="nb-cal">
      <div class="nb-cal-h">
        <button
          type="button"
          aria-label={t.prev_month}
          disabled={view <= monthKey(block.min)}
          onClick={() => shift(-1)}
        >
          <Icon name="back" />
        </button>
        <b aria-live="polite">
          {MONTH_NAMES[d.getUTCMonth()]} {d.getUTCFullYear()}
        </b>
        <button
          type="button"
          aria-label={t.next_month}
          disabled={view >= monthKey(block.max)}
          onClick={() => shift(1)}
        >
          <Icon name="next" />
        </button>
      </div>
      <div class="nb-cal-g">
        {WEEK.map((w, i) => (
          <span key={i} aria-hidden="true">
            {w}
          </span>
        ))}
        {Array.from({ length: lead }, (_, i) => (
          <i key={'b' + i} />
        ))}
        {Array.from({ length: daysInMonth }, (_, i) => {
          const ymd = addDays(first, i);
          const cls = [ymd === block.today ? 'today' : '', ymd === picked ? 'sel' : '']
            .filter(Boolean)
            .join(' ');
          return (
            <button
              key={ymd}
              type="button"
              class={cls || undefined}
              disabled={!open(ymd)}
              aria-label={fmtDate(ymd)}
              aria-pressed={ymd === picked}
              onClick={() => {
                setPicked(ymd);
                onChoose({ label: fmtDate(ymd), action: block.action, value: ymd });
              }}
            >
              {i + 1}
            </button>
          );
        })}
      </div>
    </div>
  );
}
