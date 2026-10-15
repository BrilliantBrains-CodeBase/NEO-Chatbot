// The small file each clinic website includes. It draws only the launcher and loads the
// full widget (<id>.app.js) the first time the patient opens the chat. Must stay under 5 KB gzip,
// so no Preact here, plain DOM only.
import launcherCss from './styles/launcher.css?inline';
import { launcher_label, open_chat, close_chat } from './i18n/en.json';
import { createShadowHost, injectStyles, loadFont } from './shadow';
import { getHandle, setHandle, type WidgetHandle } from './registry';

const FONT_URL = 'https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&display=swap';
const LABEL_DELAY_MS = 8000;
const SEEN_KEY = 'neo_seen';

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

export function boot({ clinicId, themeCss, loadApp }: LoaderOptions) {
  if (getHandle(clinicId)) return;

  // Only valid while this file first runs, so read it before anything async.
  const script = document.currentScript as HTMLScriptElement | null;
  const src = script?.src || '';
  const apiBase = script?.dataset.api || (src ? new URL(src).origin : location.origin);
  const appUrl = src.replace(/\.js(\?.*)?$/, '.app.js$1');

  const start = () => {
    loadFont(FONT_URL);
    const { shadow } = createShadowHost(clinicId);
    injectStyles(shadow, themeCss + launcherCss);

    const root = document.createElement('div');
    root.className = 'nb' + (seen() ? ' seen' : '');
    const mountPoint = document.createElement('div');
    const launcher = document.createElement('button');
    launcher.type = 'button';
    launcher.className = 'nb-launch';
    launcher.setAttribute('aria-label', open_chat);
    launcher.setAttribute('aria-expanded', 'false');
    launcher.innerHTML =
      `<span class="lbl">${launcher_label}</span>` +
      '<span class="orb"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z"/></svg><span class="dot"></span></span>';
    root.append(mountPoint, launcher);
    shadow.appendChild(root);

    // Desktop: show the "Chat with us" label after 8 seconds. Never auto open the panel.
    setTimeout(() => launcher.classList.add('show-label'), LABEL_DELAY_MS);

    let loading: Promise<unknown> | null = null;
    const handle: WidgetHandle = {
      clinicId,
      shadow,
      mountPoint,
      apiBase,
      appUrl,
      isOpen: false,
      setOpen(open) {
        handle.isOpen = open;
        root.classList.toggle('is-open', open);
        launcher.setAttribute('aria-expanded', String(open));
        launcher.setAttribute('aria-label', open ? close_chat : open_chat);
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

  if (document.body) start();
  else document.addEventListener('DOMContentLoaded', start);
}
