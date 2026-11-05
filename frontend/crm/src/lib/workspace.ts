// Which side of the CRM / Dashboard switch is open. Team belongs to both: opening it keeps the side (and its menu)
// you came from, so the switch never moves under you.
const SHARED = ["/team"];
let dashboard = false;

export function inDashboard(path: string): boolean {
  // Remembered in the browser only: a server handles many people, and a first page load starts on the CRM side.
  if (typeof window === "undefined") return path.startsWith("/assistant");
  if (!SHARED.includes(path)) dashboard = path.startsWith("/assistant");
  return dashboard;
}
