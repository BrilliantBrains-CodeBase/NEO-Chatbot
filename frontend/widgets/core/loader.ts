// The small file each clinic website includes. It draws only the launcher and loads the
// full widget (<id>.app.js) the first time the patient opens the chat. Must stay under 5 KB gzip,
// so no Preact here, plain DOM only.
import launcherCss from './styles/launcher.css?inline';
import { launcher_label, open_chat, close_chat } from './i18n/en.json';
import { createShadowHost, injectStyles, loadFont } from './shadow';
import { getHandle, setHandle, type WidgetHandle } from './registry';
import type { Appearance, ClinicContact, MenuTemplate } from './types';

const FONT_URL = 'https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&display=swap';
const LABEL_DELAY_MS = 8000;
const SEEN_KEY = 'neo_seen';
const DEV_API = 'http://127.0.0.1:8000';

export interface LoaderOptions {
  clinicId: string;
  // Clinic colour tokens as CSS, for example ":host{--rose:#3D203F;...}"
  themeCss: string;
  loadApp: (handle: WidgetHandle) => Promise<unknown>;
}

export function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error(`Could not load ${src}`));
    document.head.appendChild(s);
  });
}

function seen(set?: boolean): boolean {
  try {
    if (set) sessionStorage.setItem(SEEN_KEY, '1');
    return sessionStorage.getItem(SEEN_KEY) === '1';
  } catch {
    return !!set;
  }
}

// Dashboard → Appearance as CSS over the built-in look: the colours, the launcher's colour and place.
const SIZES = { small: [340, 540, 48], medium: [380, 580, 54], large: [420, 640, 60] };
const FONTS = {
  Figtree: FONT_URL,
  Inter: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap',
  System: '',
};

function lookCss(a: Appearance): string {
  const c = a.colours;
  const l = a.launcher;
  const w = a.widget;
  const [side, other] = l.position === 'bottom_left' ? ['left', 'right'] : ['right', 'left'];
  const [width, height] = SIZES[w.size];
  const orb = SIZES[l.size][2];
  const font = w.font === 'System' ? 'system-ui' : `'${w.font}', system-ui`;
  return (
    `:host{--font:${font},-apple-system,'Segoe UI',Roboto,sans-serif}` +
    `@media (min-width:641px){.nb-panel{width:${width}px;height:${height}px;` +
    `border-radius:${{ square: 8, rounded: 20, round: 28 }[w.radius]}px;` +
    `border:${{ none: '0', subtle: '1px solid var(--line)', strong: '2px solid var(--rose)' }[w.border]};` +
    `box-shadow:${{ none: 'none', soft: `0 24px 48px -20px ${c.main}66`, strong: `0 30px 60px -14px ${c.main}aa` }[w.shadow]}}` +
    (l.opens_as === 'full'
      ? '.nb-panel{inset:0;width:auto;height:auto;max-height:none;border-radius:0}'
      : '') +
    '}' +
    (a.look.header_arc ? '' : '.nb-head::after{display:none}') +
    `.nb-launch .orb{width:${l.shape === 'pill' ? orb * 1.6 : orb}px;height:${orb}px;` +
    `border-radius:${l.shape === 'rounded' ? '30%' : '999px'};` +
    `border:${{ none: '0', subtle: '2px solid #ffffff99', strong: '3px solid #fff' }[l.border]}}` +
    '.nb-launch .orb img{width:62%;height:62%;border-radius:50%;object-fit:cover}' +
    (l.notification_dot ? '' : '.nb-launch .dot{display:none}') +
    (l.mobile_label ? '@media (max-width:640px){.nb-launch.show-label .lbl{display:block}}' : '') +
    (c.dark_mode
      ? `@media (prefers-color-scheme:dark){:host{--surface:${c.dark_card};--ink:${c.dark_text};` +
        `--line:${c.dark_line};--mute:${c.dark_text}}.nb-panel{background:${c.dark_page}}` +
        `.nb-chip,.nb-menu .nb-tile,.nb-launch .lbl{background:${c.dark_card};color:${c.dark_text}}}`
      : '') +
    `:host{--rose:${c.main};--rose-d:${c.main_dark};--blush:${c.accent};--tint:${c.tint};--honey:${c.highlight};` +
    `--surface:${c.surface};--line:${c.line};--ink:${c.text};--mute:${c.muted};--wa:${c.whatsapp}}` +
    `.nb-launch .orb{background:${l.background};color:${l.icon_color}}` +
    `.nb-launch{${other}:auto;${side}:${l.offset_x}px;bottom:${l.offset_y}px` +
    (side === 'left' ? ';flex-direction:row-reverse}' : '}') +
    `@media (min-width:641px){.nb-panel{${other}:auto;${side}:${l.offset_x}px;bottom:${l.offset_y + 76}px}}` +
    `@media (max-width:640px){.nb-launch{${side}:${l.mobile_offset_x}px;bottom:${l.mobile_offset_y}px}}`
  );
}

export function boot({ clinicId, themeCss, loadApp }: LoaderOptions) {
  if (getHandle(clinicId)) return;

  // Only valid while this file first runs, so read it before anything async.
  const script = document.currentScript as HTMLScriptElement | null;
  const src = script?.src || '';
  const apiBase = script?.dataset.api || (src ? new URL(src).origin : location.origin);
  const appUrl = src.replace(/\.js(\?.*)?$/, '.app.js$1');

  const start = (
    appearance: Appearance | null,
    template: MenuTemplate | null = null,
    contact: ClinicContact | null = null,
  ) => {
    if (appearance && !appearance.look.enabled) return; // switched off in the Dashboard
    const css = appearance ? lookCss(appearance) : '';
    const font = appearance ? FONTS[appearance.widget.font] : FONT_URL;
    if (font) loadFont(font);
    const { shadow } = createShadowHost(clinicId);
    // Clinic theme last, so it can override shared tokens such as --honey.
    injectStyles(shadow, launcherCss + themeCss + css);

    const root = document.createElement('div');
    root.className = 'nb' + (seen() ? ' seen' : '');
    const mountPoint = document.createElement('div');
    const launcher = document.createElement('button');
    launcher.type = 'button';
    launcher.className = 'nb-launch';
    launcher.setAttribute('aria-label', open_chat);
    launcher.setAttribute('aria-expanded', 'false');
    launcher.innerHTML =
      '<span class="lbl"></span>' +
      '<span class="orb"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z"/></svg><span class="dot"></span></span>';
    // Text and the logo address from the Dashboard go in as text and an attribute, never as HTML.
    launcher.querySelector('.lbl')!.textContent = appearance?.launcher.label_text || launcher_label;
    if (appearance?.launcher.icon === 'logo' && appearance.look.logo) {
      const img = document.createElement('img');
      img.src = appearance.look.logo;
      img.alt = '';
      launcher.querySelector('svg')!.replaceWith(img);
    }
    root.append(mountPoint, launcher);
    shadow.appendChild(root);

    // Desktop: the "Chat with us" label after the set seconds (8 by default).
    const label = appearance?.launcher;
    if (!label || label.label_on) {
      setTimeout(
        () => launcher.classList.add('show-label'),
        label ? label.label_after_s * 1000 : LABEL_DELAY_MS,
      );
    }

    let loading: Promise<unknown> | null = null;
    const handle: WidgetHandle = {
      clinicId,
      shadow,
      mountPoint,
      apiBase,
      appUrl,
      isOpen: false,
      appearance,
      lookCss: css,
      template,
      contact,
      setOpen(open) {
        handle.isOpen = open;
        root.classList.toggle('is-open', open);
        launcher.setAttribute('aria-expanded', String(open));
        launcher.setAttribute('aria-label', open ? close_chat : open_chat);
        // Closing removes the panel, so give keyboard focus back to the launcher instead of losing it.
        if (!open) launcher.focus();
        if (open && !seen()) {
          root.classList.add('seen');
          seen(true);
        }
        if (handle.onOpenChange) return handle.onOpenChange(open);
        if (open && !loading) {
          loading = loadApp(handle).catch((err) => {
            loading = null;
            handle.setOpen(false);
            console.warn('[neo-widget]', err);
          });
        }
      },
    };
    setHandle(handle);
    launcher.addEventListener('click', () => handle.setOpen(!handle.isOpen));
    // Desktop only, the first visit in this browser session: opens by itself (Dashboard → Appearance).
    if (appearance?.launcher.open_on_first_visit && !seen() && !matchMedia('(max-width: 640px)').matches) {
      handle.setOpen(true);
    }
  };

  // Shown only where the clinic allows it: its approved website, and the pages set in the Dashboard.
  // Then the clinic's published look (the built-in look if that fails).
  const look = (base: string) =>
    fetch(`${base}/v1/widget/config/${clinicId}`)
      .then((r) => r.json())
      .then(
        (r: { appearance?: Appearance | null; template?: MenuTemplate | null; contact?: ClinicContact }) =>
          start(r.appearance ?? null, r.template ?? null, r.contact ?? null),
      )
      .catch(() => start(null));
  const ready = () => {
    // dev playground: no approved website to check; the look comes from the local backend (or ?api=)
    if (import.meta.env.DEV) return look(new URLSearchParams(location.search).get('api') || DEV_API);
    fetch(`${apiBase}/v1/widget/show?clinic=${clinicId}&path=${encodeURIComponent(location.pathname)}`)
      .then((r) => r.json())
      .then((r: { show?: boolean }) => (r.show ? look(apiBase) : undefined))
      .catch((err) => console.warn('[neo-widget]', err));
  };
  if (document.body) ready();
  else document.addEventListener('DOMContentLoaded', ready);
}
