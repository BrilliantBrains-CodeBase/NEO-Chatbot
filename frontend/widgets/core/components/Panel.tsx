import type { ComponentChildren } from 'preact';
import { useEffect, useRef } from 'preact/hooks';
import { Icon } from '../icons';
import t from '../i18n/en.json';

const SWIPE_CLOSE_PX = 80;
// Same breakpoint as the mobile rules in base.css.
const MOBILE_QUERY = '(max-width: 640px)';

interface Props {
  botName: string;
  onClose: () => void;
  children?: ComponentChildren;
}

// Desktop: floating panel. Mobile (640 px and below): bottom sheet with backdrop, closed by X,
// tapping the backdrop, swiping the header down, or Escape.
export function Panel({ botName, onClose, children }: Props) {
  const panel = useRef<HTMLDivElement>(null);
  const startY = useRef<number | null>(null);

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
      <div class="nb-panel" role="dialog" aria-label={`${botName} chat`} ref={panel}>
        <div class="nb-head" onTouchStart={onTouchStart} onTouchMove={onTouchMove} onTouchEnd={onTouchEnd}>
          <span class="nb-grip" />
          <div class="nb-ava" aria-hidden="true">
            N
          </div>
          <div class="nb-title">
            <b>{botName}</b>
            <span>{t.subtitle}</span>
          </div>
          <button type="button" class="nb-x" aria-label={t.close_chat} onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        <div class="nb-body" aria-live="polite">
          {children}
        </div>
        <div class="nb-legal">
          {t.footer_disclaimer}
          <br />
          {t.footer_powered_by}{' '}
          <a href="https://brilliantbrains.ai/" target="_blank" rel="noopener noreferrer">
            {t.footer_brand}
          </a>
        </div>
      </div>
    </>
  );
}
