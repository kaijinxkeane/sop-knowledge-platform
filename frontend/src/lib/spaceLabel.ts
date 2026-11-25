/**
 * How a department's short name is shown: abbreviations in capitals (hr -> HR,
 * it -> IT), other names with a capital first letter (core -> Core,
 * marketing -> Marketing). Only for display: the name itself never changes.
 */
export function spaceLabel(name: string | null | undefined): string {
  if (!name) return "";
  if (name.length <= 3) return name.toUpperCase();
  return name
    .split("-")
    .map((w) => (w.length <= 2 ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}
