import { useState } from 'preact/hooks';
import type { ChipsBlock, Choice, MenuBlock, UiBlock } from '../types';
import { Icon } from '../icons';
import t from '../i18n/en.json';

export type OnChoose = (choice: Choice) => void;

// A tappable choice: a link when it has href (call, WhatsApp, website), otherwise a button that sends an event.
function Tap({ choice, class: cls, onChoose }: { choice: Choice; class: string; onChoose: OnChoose }) {
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

// Main menu. Arya: 3-column cards, Emergency across the full row.
function Menu({ block, onChoose }: { block: MenuBlock; onChoose: OnChoose }) {
  return (
    <div class={`nb-menu ${block.layout}`}>
      {block.items.map((item) => (
        <Tap
          key={item.label}
          choice={item}
          class={`nb-tile${item.variant ? ' ' + item.variant : ''}`}
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

// Every block stays visible and usable after a choice, so the patient can change their mind.
export function Block({ block, onChoose }: { block: UiBlock; onChoose: OnChoose }) {
  switch (block.type) {
    case 'menu':
      return <Menu block={block} onChoose={onChoose} />;
    case 'chips':
      return <Chips block={block} onChoose={onChoose} />;
    default:
      return null; // added in the next pieces
  }
}
