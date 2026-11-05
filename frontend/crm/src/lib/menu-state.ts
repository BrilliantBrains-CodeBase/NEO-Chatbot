// Whether the left menu is collapsed to its icon strip, remembered per browser. The setting lives on <html>
// as an attribute so crm.css can apply it before the first paint (a reload never shows the menu jumping).
const KEY = "neo-crm-menu-mini";
const ATTR = "data-menu-mini";
const WIDE = "(min-width:861px)"; // phones keep the slide-in menu (same width as crm.css)

/** Runs in <head> on every full page load, before anything is drawn. */
export const MENU_BOOT = `try{if(localStorage.getItem("${KEY}")==="1")document.documentElement.setAttribute("${ATTR}","")}catch(e){}`;

const listeners = new Set<() => void>();

export function subscribeMenu(onChange: () => void) {
  const screen = window.matchMedia(WIDE);
  listeners.add(onChange);
  screen.addEventListener("change", onChange);
  return () => {
    listeners.delete(onChange);
    screen.removeEventListener("change", onChange);
  };
}

/** True while the menu is showing as the icon strip (collapsed, on a wide screen). */
export const isMenuRail = () =>
  document.documentElement.hasAttribute(ATTR) && window.matchMedia(WIDE).matches;

export function toggleMenuMini() {
  const mini = document.documentElement.toggleAttribute(ATTR);
  try {
    localStorage.setItem(KEY, mini ? "1" : "0");
  } catch {
    // Private windows may refuse storage: the menu still collapses, it just is not remembered.
  }
  listeners.forEach((fn) => fn());
}
