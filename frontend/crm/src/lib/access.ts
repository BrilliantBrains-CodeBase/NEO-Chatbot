import type { Me } from "./api";

// Who sees what (Dashboard → Team & access): each person's level per screen in a clinic, from GET /v1/crm/me.
// BB Admin always edits. Without levels (an older backend), nothing is hidden: the backend still decides.
export type Level = "hidden" | "view" | "edit";

/** The screen a page belongs to: /leads → "leads", /assistant/appearance → "dash_appearance". */
export function screenOf(path: string): string | null {
  const [, first, second] = path.split("/");
  if (first === "assistant") return second ? `dash_${second}` : "dash_open";
  return first || null;
}

export function level(
  me: Me | null,
  clinic: string,
  screen: string | null,
): Level {
  if (!me || !screen || me.bb_admin) return "edit";
  const access = me.clinics.find((c) => c.name === clinic || c.id === clinic)?.access;
  if (!access || Object.keys(access).length === 0) return "edit";
  const own = (access[screen] as Level | undefined) ?? "edit";
  // A Dashboard tab needs the Dashboard itself open.
  if (
    screen.startsWith("dash_") &&
    screen !== "dash_open" &&
    access.dash_open === "hidden"
  )
    return "hidden";
  return own;
}

export const canSee = (me: Me | null, clinic: string, path: string) =>
  level(me, clinic, screenOf(path)) !== "hidden";
