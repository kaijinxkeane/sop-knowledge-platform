/**
 * Compare two versions of a note by block (headings, paragraphs, list items,
 * tables, quotes, callouts), so the change can be shown formatted, the way the
 * note reads, instead of as raw lines. The frontmatter (the note's details)
 * is compared field by field.
 */
import type { Root, RootContent } from "mdast";
import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import { unified } from "unified";
import { splitFrontmatter } from "@/lib/obsidian";
import { seqDiff, type Row } from "./diff";

const parser = unified().use(remarkParse).use(remarkGfm);

/** The note body cut into blocks; each list item is its own block. */
export function blocks(body: string): string[] {
  const tree = parser.parse(body) as Root;
  const slice = (n: { position?: { start: { offset?: number }; end: { offset?: number } } }) =>
    body.slice(n.position?.start.offset ?? 0, n.position?.end.offset ?? 0);
  const out: string[] = [];
  for (const node of tree.children as RootContent[]) {
    if (node.type === "list") {
      // Keep the numbering: an ordered item renders with its own number.
      for (const item of node.children) out.push(slice(item));
    } else {
      out.push(slice(node));
    }
  }
  return out.map((b) => b.replace(/\s+$/, "")).filter(Boolean);
}

export type DetailChange = { key: string; before: string | null; after: string | null };

/** Top-level `key: value` fields of the frontmatter (continuation lines kept with their key). */
function fields(frontmatter: string): Map<string, string> {
  const map = new Map<string, string>();
  let key: string | null = null;
  for (const line of frontmatter.split(/\r?\n/)) {
    const m = /^([A-Za-z_][\w-]*):\s?(.*)$/.exec(line);
    if (m) {
      key = m[1]!;
      map.set(key, m[2]!.trim());
    } else if (key && line.trim()) {
      map.set(key, `${map.get(key)} ${line.trim()}`.trim());
    }
  }
  return map;
}

export function detailChanges(before: string, after: string): DetailChange[] {
  const a = fields(splitFrontmatter(before).frontmatter);
  const b = fields(splitFrontmatter(after).frontmatter);
  const keys = [...new Set([...a.keys(), ...b.keys()])];
  return keys
    .filter((k) => a.get(k) !== b.get(k))
    .map((k) => ({ key: k, before: a.get(k) ?? null, after: b.get(k) ?? null }));
}

export function blockDiff(before: string, after: string): Row[] {
  return seqDiff(blocks(splitFrontmatter(before).body), blocks(splitFrontmatter(after).body));
}
