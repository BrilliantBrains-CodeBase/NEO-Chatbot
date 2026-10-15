// Shadow DOM mount, so the clinic website's CSS cannot change the widget and ours cannot leak out.

export function createShadowHost(clinicId: string): { host: HTMLElement; shadow: ShadowRoot } {
  const host = document.createElement('div');
  host.id = `neo-widget-${clinicId}`;
  // Reset inherited styles from the page before anything renders inside.
  host.style.cssText = 'all:initial';
  document.body.appendChild(host);
  const shadow = host.attachShadow({ mode: 'open' });
  return { host, shadow };
}

export function injectStyles(shadow: ShadowRoot, css: string) {
  const style = document.createElement('style');
  style.textContent = css;
  shadow.appendChild(style);
}

// Fonts must be declared on the page; @font-face inside a shadow root is not applied.
export function loadFont(href: string) {
  if (document.querySelector(`link[href="${href}"]`)) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = href;
  document.head.appendChild(link);
}
