// The small file each clinic website includes. It draws only the launcher and loads the
// full widget (<id>.app.js) the first time the patient opens the chat. Must stay under 5 KB gzip,
// so no Preact here, plain DOM only.
import launcherCss from './styles/launcher.css?inline';
import { launcher_label, open_chat, close_chat } from './i18n/en.json';
import { createShadowHost, injectStyles, loadFont } from './shadow';
import { getHandle, setHandle, type WidgetHandle } from './registry';
import type { Appearance } from './types';

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
function lookCss(a: Appearance): string {
  const c = a.colours;
  const l = a.launcher;
  const [side, other] = l.position === 'bottom_left' ? ['left', 'right'] : ['right', 'left'];
  return (
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

  const start = (appearance: Appearance | null) => {
    const css = appearance ? lookCss(appearance) : '';
    loadFont(FONT_URL);
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
      `<span class="lbl">${appearance?.launcher.label_text || launcher_label}</span>` +
      '<span class="orb"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z"/></svg><span class="dot"></span></span>';
    root.append(mountPoint, launcher);
    shadow.appendChild(root);

    // Desktop: show the "Chat with us" label after 8 seconds. Never auto open the panel.
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
  };

  // Shown only where the clinic allows it: its approved website, and the pages set in the Dashboard.
  // Then the clinic's published look (the built-in look if that fails).
  const look = (base: string) =>
    fetch(`${base}/v1/widget/config/${clinicId}`)
      .then((r) => r.json())
      .then((r: { appearance?: Appearance | null }) => start(r.appearance ?? null))
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
