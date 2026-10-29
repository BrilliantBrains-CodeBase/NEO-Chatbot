import type { ComponentChildren } from 'preact';
import { useEffect, useRef, useState } from 'preact/hooks';
import { Icon } from '../icons';
import t from '../i18n/en.json';
import type { Appearance } from '../types';

const SWIPE_CLOSE_PX = 80;
// Same breakpoint as the mobile rules in base.css.
const MOBILE_QUERY = '(max-width: 640px)';

interface Props {
  botName: string;
  // Dashboard → Appearance as published; null: the built-in header and footer.
  appearance?: Appearance | null;
  onClose: () => void;
  onRestart: () => void;
  // The typing bar, shown between the messages and the footer text.
  composer?: ComponentChildren;
  children?: ComponentChildren;
}

// Desktop: floating panel. Mobile (640 px and below): bottom sheet with backdrop, closed by X,
// tapping the backdrop, swiping the header down, or Escape.
export function Panel({ botName, appearance, onClose, onRestart, composer, children }: Props) {
  const panel = useRef<HTMLDivElement>(null);
  const brandLink = appearance?.widget.footer_link || 'https://brilliantbrains.ai/';
  const startY = useRef<number | null>(null);
  // Mobile: the sheet goes full height when the patient starts typing and stays so until the chat is
  // closed. Shrinking it again on blur would move the buttons mid-tap and the tap would miss.
  const [full, setFull] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const onTouchStart = (e: TouchEvent) => {
    // Swipe to close only on the mobile sheet, not on a desktop touch screen.
    if (matchMedia(MOBILE_QUERY).matches) startY.current = e.touches[0].clientY;
  };
  const onTouchMove = (e: TouchEvent) => {
    if (startY.current === null || !panel.current) return;
    const dy = Math.max(0, e.touches[0].clientY - startY.current);
    panel.current.style.transform = dy ? `translateY(${dy}px)` : '';
  };
  const onTouchEnd = (e: TouchEvent) => {
    if (startY.current === null || !panel.current) return;
    const dy = e.changedTouches[0].clientY - startY.current;
    startY.current = null;
    panel.current.style.transform = '';
    if (dy > SWIPE_CLOSE_PX) onClose();
  };

  return (
    <>
      <div class="nb-backdrop" onClick={onClose} />
      <div
        class={full ? 'nb-panel full' : 'nb-panel'}
        role="dialog"
        aria-label={`${botName} chat`}
        ref={panel}
        onFocusIn={(e) => (e.target as HTMLElement).classList.contains('nb-in') && setFull(true)}
      >
        <div class="nb-head" onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}>
          <span class="nb-grip" />
          <div class="nb-ava" aria-hidden="true">
            {appearance?.look.logo ? (
              <img
                src={appearance.look.logo}
                alt=""
                style={{ width: '100%', height: '100%', borderRadius: '50%', objectFit: 'cover' }}
              />
            ) : (
              appearance?.look.avatar_letter || 'N'
            )}
          </div>
          <div class="nb-title">
            <b>{botName}</b>
            {appearance?.look.location && <span>{appearance.look.location}</span>}
            <span>
              {appearance?.look.tagline || t.subtitle}
              <span class="nb-pw">
                {' · '}
                {t.header_powered_by}{' '}
                <a href={brandLink} target="_blank" rel="noopener noreferrer">
                  {t.footer_brand}
                </a>
              </span>
            </span>
          </div>
          <button
            type="button"
            class="nb-x"
            aria-label={t.restart_chat}
            title={t.restart_chat}
            onClick={onRestart}
          >
            <Icon name="restart" />
          </button>
          <button type="button" class="nb-x" aria-label={t.close_chat} onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        <div class="nb-body" aria-live="polite">
          {children}
        </div>
        {composer}
        {(appearance?.widget.footer_on ?? true) && (
          <div class="nb-legal">
            {appearance?.widget.footer_text || t.footer_disclaimer}
            {' · '}
            {t.footer_powered_by}{' '}
            <a href={brandLink} target="_blank" rel="noopener noreferrer">
              {t.footer_brand}
            </a>
          </div>
        )}
      </div>
    </>
  );
}
