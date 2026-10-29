import type { Choice, ClinicContact } from '../types';
import t from '../i18n/en.json';
import { Tap, type OnChoose } from './Blocks';

// Mobile only (Dashboard → Appearance → Mobile contact row): Call, Book and WhatsApp under the chat, in the
// clinic's order. Call and WhatsApp use Clinic info → Contact & hours; one that is not set there is left out.
export function ContactRow({
  buttons,
  contact,
  onChoose,
}: {
  buttons: ('call' | 'book' | 'whatsapp')[];
  contact: ClinicContact | null;
  onChoose: OnChoose;
}) {
  const choices = buttons
    .map((b): Choice | null => {
      if (b === 'book') return { label: t.contact_book, icon: 'cal', action: 'start', value: 'book' };
      if (b === 'call')
        return contact?.phone ? { label: t.contact_call, icon: 'phone', href: 'tel:' + contact.phone } : null;
      return contact?.whatsapp
        ? { label: t.contact_whatsapp, icon: 'chat', href: contact.whatsapp, variant: 'wa' }
        : null;
    })
    .filter((c): c is Choice => c !== null);
  if (!choices.length) return null;
  return (
    <div class="nb-contact" style={{ '--n': choices.length }}>
      {choices.map((c) => (
        <Tap
          key={c.label}
          choice={c}
          class={`nb-cbtn${c.action ? ' book' : ''}${c.variant ? ' ' + c.variant : ''}`}
          onChoose={(choice) => onChoose({ ...choice, label: t.contact_book_said })}
        />
      ))}
    </div>
  );
}
