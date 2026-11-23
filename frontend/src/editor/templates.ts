/**
 * Starting text for new notes (frontend spec §6). The SOP one matches the
 * vault's `_templates/SOP.md` sections, so notes started here and in Obsidian look alike.
 */
export const TEMPLATES = {
  sop: ["Purpose", "When to use it", "Steps", "Done when"],
  checklist: ["Before", "During", "After"],
  "run-sheet": ["Before the session", "Running order", "Materials", "After the session"],
  playbook: ["Who it's for", "What the client gets", "How we deliver it", "Hand-offs", "Done when"],
  note: [],
} as const;

export type Template = keyof typeof TEMPLATES;
export const TEMPLATE_NAMES = Object.keys(TEMPLATES) as Template[];

export function templateBody(kind: Template, title: string, related: string[] = []): string {
  const lines = [`# ${title.trim()}`, ""];
  for (const h of TEMPLATES[kind]) lines.push(`## ${h}`, "", "");
  if (related.length) lines.push("## Related", "", ...related.map((r) => `- [[${r}]]`), "");
  return lines.join("\n").replace(/\n+$/, "\n");
}
