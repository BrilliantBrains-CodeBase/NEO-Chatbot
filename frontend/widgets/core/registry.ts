// Shared handle between the loader (<id>.js) and the full widget (<id>.app.js).
// The loader creates it; the widget picks it up from window.__neoWidgets when its file runs.

export interface WidgetHandle {
  clinicId: string;
  shadow: ShadowRoot;
  mountPoint: HTMLElement;
  apiBase: string;
  appUrl: string;
  isOpen: boolean;
  setOpen(open: boolean): void;
  // Set by the widget once mounted, so the loader can tell it when the launcher is clicked.
  onOpenChange?: (open: boolean) => void;
}

declare global {
  interface Window {
    __neoWidgets?: Record<string, WidgetHandle>;
  }
}

export function getHandle(clinicId: string): WidgetHandle | undefined {
  return window.__neoWidgets?.[clinicId];
}

export function setHandle(handle: WidgetHandle) {
  (window.__neoWidgets ??= {})[handle.clinicId] = handle;
}
