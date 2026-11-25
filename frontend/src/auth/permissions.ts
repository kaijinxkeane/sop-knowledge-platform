import type { Schemas } from "@/api/client";

export type Me = Schemas["MeOut"];

export type Section = "ask" | "library" | "write" | "review" | "retain" | "handovers" | "projects" | "admin";

/**
 * Which top-bar sections a user sees (frontend spec §2). This is cosmetic:
 * the backend still enforces every permission, so a hidden menu is a
 * convenience, never the control.
 */
export function visibleSections(me: Me): Section[] {
  const spaceActions = new Set(Object.values(me.space_actions).flat());
  const global = new Set(me.global_actions);
  const sections: Section[] = ["ask", "library"];
  if (spaceActions.has("contribute")) sections.push("write");
  // Authors see Review too: their own submitted changes and unplaced notes.
  if (["review", "approve", "contribute"].some((a) => spaceActions.has(a))) sections.push("review");
  if (spaceActions.has("approve") || spaceActions.has("review") || global.has("view_gap_reports")) sections.push("retain");
  if (spaceActions.has("contribute")) sections.push("handovers");
  if (spaceActions.has("contribute") || spaceActions.has("approve")) sections.push("projects");
  if (global.has("manage_users") || global.has("view_audit") || global.has("manage_spaces")) sections.push("admin");
  return sections;
}
