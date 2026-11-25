/**
 * Obsidian markdown for the reading view: frontmatter, [[wikilinks]],
 * ![[embeds]], #tags and > [!callouts], turned into plain markdown with
 * private link schemes that the renderer maps to components.
 *
 * Code blocks are left untouched. Nothing here is a security boundary: the
 * text was already allowed by the backend; this only decides how it looks.
 */

export const LINK = "sop-link:";
export const EMBED = "sop-embed:";
export const TAG = "sop-tag:";
export const MARK = "sop-mark:";
export const CALLOUT = "sop-callout:";

export type CalloutTone = "blue" | "green" | "amber" | "red" | "grey";
const TONES: Record<string, CalloutTone> = {
  note: "blue", info: "blue", todo: "blue", abstract: "blue", summary: "blue", tldr: "blue",
  question: "blue", help: "blue", faq: "blue",
  tip: "green", hint: "green", important: "green", success: "green", check: "green", done: "green",
  warning: "amber", caution: "amber", attention: "amber",
  danger: "red", error: "red", failure: "red", fail: "red", missing: "red", bug: "red",
  example: "grey", quote: "grey", cite: "grey",
};
/** Colour family of an Obsidian callout type (unknown types read as a note). */
export const calloutTone = (kind: string): CalloutTone => TONES[kind.toLowerCase()] ?? "blue";

export function splitFrontmatter(text: string): { frontmatter: string; body: string } {
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text);
  return m ? { frontmatter: m[1] ?? "", body: text.slice(m[0].length) } : { frontmatter: "", body: text };
}

// Markdown link text can't hold unescaped brackets.
const escapeText = (s: string) => s.replace(/([[\]\\])/g, "\\$1");

function transformProse(text: string): string {
  return (
    text
      // > [!warning] Title  ->  a callout header the renderer colours by type
      .replace(/^(\s*>\s*)\[!(\w+)\][+-]?\s*(.*)$/gm, (_m, lead: string, kind: string, title: string) => {
        const label = kind.charAt(0).toUpperCase() + kind.slice(1).toLowerCase();
        const text = title.trim() ? `${label}: ${title.trim()}` : label;
        return `${lead}[${escapeText(text)}](${CALLOUT}${kind.toLowerCase()})`;
      })
      // ![[target]] (embed: a deck, PDF or note shown as a card)
      .replace(/!\[\[([^\]\n]+?)\]\]/g, (_m, inner: string) => {
        const target = inner.split("|")[0]!.trim();
        return `[${escapeText(target)}](${EMBED}${encodeURIComponent(target)})`;
      })
      // [[target]], [[target|alias]], [[target#heading]]
      .replace(/\[\[([^\]\n]+?)\]\]/g, (_m, inner: string) => {
        const [target = "", alias] = inner.split("|");
        const shown = (alias ?? target.split("#")[0] ?? "").trim();
        return `[${escapeText(shown)}](${LINK}${encodeURIComponent(target.trim())})`;
      })
      // ==highlight== (Obsidian), shown as a highlight
      .replace(/==([^=\n]+)==/g, (_m, inner: string) => `[${escapeText(inner)}](${MARK})`)
      // #tag (a letter right after #, so "# Heading" is left alone)
      .replace(/(^|[\s(])#([A-Za-z][\w/-]*)/g, (_m, pre: string, tag: string) => {
        return `${pre}[#${tag}](${TAG}${encodeURIComponent(tag)})`;
      })
  );
}

/** Apply the Obsidian transforms everywhere except inside fenced code blocks. */
export function toMarkdown(body: string): string {
  const parts = body.split(/^(```[\s\S]*?^```|~~~[\s\S]*?^~~~)/m);
  return parts.map((p, i) => (i % 2 === 1 ? p : transformProse(p))).join("");
}

export type Linkable = { id: string; title: string; vault_path: string; kind: string };

const basename = (path: string) => path.split("/").pop() ?? path;
const stem = (name: string) => name.replace(/\.[^.]+$/, "");

/**
 * Find the document a link points to, among the documents this user can see.
 * Obsidian links by file name (with or without extension); titles are tried
 * last. Unknown and unreadable targets both return null, deliberately alike.
 */
export function makeResolver(docs: Linkable[]) {
  const index = new Map<string, Linkable>();
  const add = (key: string, d: Linkable) => {
    const k = key.trim().toLowerCase();
    if (k && !index.has(k)) index.set(k, d);
  };
  for (const d of docs) {
    add(basename(d.vault_path), d);
    add(stem(basename(d.vault_path)), d);
    add(stem(d.vault_path), d);
    add(d.vault_path, d);
  }
  for (const d of docs) add(d.title, d);
  return (target: string): Linkable | null => {
    const clean = target.split("#")[0]!.trim().toLowerCase();
    return index.get(clean) ?? null;
  };
}

/** Frontmatter values like "[[Signature Personal Brand Programme]]" shown as plain names. */
export const plainName = (value: string | null | undefined) =>
  value ? value.replace(/^\[\[|\]\]$/g, "").split("|").pop()!.trim() : null;
