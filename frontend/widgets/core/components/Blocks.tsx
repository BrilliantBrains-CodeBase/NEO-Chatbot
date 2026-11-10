import { useState } from 'preact/hooks';
import type { ChipsBlock, Choice, DoctorCardBlock, MenuBlock, MenuTemplate, UiBlock } from '../types';
import { Icon } from '../icons';
import t from '../i18n/en.json';
import { Calendar } from './Calendar';
import { TimeGrid } from './TimeGrid';

export type OnChoose = (choice: Choice) => void;

// A tappable choice: a link when it has href (call, WhatsApp, website), otherwise a button that sends an event.
export function Tap({ choice, class: cls, onChoose }: { choice: Choice; class: string; onChoose: OnChoose }) {
  const body = (
    <>
      {choice.icon && (
        <span class="ic">
          <Icon name={choice.icon} />
        </span>
      )}
      <span>{choice.label}</span>
    </>
  );
  if (choice.href) {
    const external = !choice.href.startsWith('tel:');
    return (
      <a
        class={cls}
        href={choice.href}
        target={external ? '_blank' : undefined}
        rel={external ? 'noopener noreferrer' : undefined}
      >
        {body}
      </a>
    );
  }
  return (
    <button type="button" class={cls} onClick={() => onChoose(choice)}>
      {body}
    </button>
  );
}

// The clinic's published Dashboard → Templates (set once when the widget mounts); null: the built-in menu.
let menuTemplate: MenuTemplate | null = null;
export const setMenuTemplate = (tpl: MenuTemplate | null) => (menuTemplate = tpl);

// Main menu. Built in (Arya): 3-column cards, Emergency across the full row. With a template: tiles, pills or
// cards, its columns, and its main button filled.
function Menu({ block, onChoose }: { block: MenuBlock; onChoose: OnChoose }) {
  const tpl = menuTemplate;
  return (
    <div
      class={`nb-menu ${tpl ? 't-' + tpl.id : block.layout}`}
      style={tpl ? { '--cols': tpl.columns } : undefined}
    >
      {block.items.map((item) => (
        <Tap
          key={item.label}
          choice={item}
          class={`nb-tile${item.variant ? ' ' + item.variant : ''}${tpl && item.label === tpl.filled_button ? ' fill' : ''}`}
          onChoose={onChoose}
        />
      ))}
    </div>
  );
}

// Sub buttons as pills. The tapped pill turns solid; the group stays usable so a wrong pick can be changed.
// Back and Main menu show as grey text links under the group.
function Chips({ block, onChoose }: { block: ChipsBlock; onChoose: OnChoose }) {
  const [picked, setPicked] = useState<number | null>(null);
  const back = block.back;
  return (
    <div class="nb-chips">
      {block.options.map((choice, i) => {
        const cls = ['nb-chip', choice.primary || picked === i ? 'sel' : '', choice.variant ?? '']
          .filter(Boolean)
          .join(' ');
        return (
          <Tap
            key={choice.label}
            choice={choice}
            class={cls}
            onChoose={(c) => {
              setPicked(i);
              onChoose(c);
            }}
          />
        );
      })}
      {(back || block.main) && (
        <div class="nb-nav">
          {back && (
            <button type="button" class="nb-ghost" onClick={() => onChoose({ ...back, label: t.back })}>
              <Icon name="back" />
              {t.back}
            </button>
          )}
          {block.main && (
            <button
              type="button"
              class="nb-ghost"
              onClick={() => onChoose({ label: t.main_menu, action: 'menu' })}
            >
              <Icon name="menu" />
              {t.main_menu}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// About Doctor profile (Arya mockup): name, role, qualifications and a 3-column stats grid in one bubble,
// then its buttons.
function DoctorCard({ block, onChoose }: { block: DoctorCardBlock; onChoose: OnChoose }) {
  return (
    <>
      <div class="nb-msg bot nb-doc">
        <div class="nb-doc-h">
          {block.photo && <img class="nb-doc-photo" src={block.photo} alt="" loading="lazy" />}
          <div>
            <b>{block.name}</b>
            {block.title && <div>{block.title}</div>}
            {block.quals && <span class="nb-q">{block.quals}</span>}
          </div>
        </div>
        {block.about && <p class="nb-doc-about">{block.about}</p>}
        {block.stats.length > 0 && (
          <div class="nb-stats">
            {block.stats.map((s) => (
              <div key={s.label}>
                <b>{s.value}</b>
                <span>{s.label}</span>
              </div>
            ))}
          </div>
        )}
        {block.profile_url && (
          <a class="nb-doc-link" href={block.profile_url} target="_blank" rel="noopener noreferrer">
            {t.view_profile}
          </a>
        )}
        {block.today && <p class="nb-doc-today">{block.today}</p>}
      </div>
      <Chips
        block={{ type: 'chips', options: block.options, back: block.back, main: block.main }}
        onChoose={onChoose}
      />
    </>
  );
}

// Every block stays visible and usable after a choice, so the patient can change their mind.
export function Block({ block, onChoose }: { block: UiBlock; onChoose: OnChoose }) {
  switch (block.type) {
    case 'menu':
      return <Menu block={block} onChoose={onChoose} />;
    case 'chips':
      return <Chips block={block} onChoose={onChoose} />;
    case 'month_calendar':
      return <Calendar block={block} onChoose={onChoose} />;
    case 'time_grid':
      return <TimeGrid block={block} onChoose={onChoose} />;
    case 'doctor_card':
      return <DoctorCard block={block} onChoose={onChoose} />;
  }
}
