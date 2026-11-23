/**
 * Keep untouched blocks byte for byte (plan §8.1: "anything the editor
 * doesn't understand is preserved untouched").
 *
 * The editor re-writes the whole document in its own style. Before saving,
 * each top-level block (paragraph, list, table, heading, ...) of the edited
 * text is compared with the original's blocks by content; every block that is
 * unchanged is replaced by its original source, with its original spacing.
 * Only blocks the person actually changed come out in the editor's style, so
 * a one-word fix shows as a one-line change in review.
 */
import type { Root, RootContent } from "mdast";
import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import remarkStringify, { type Options } from "remark-stringify";
import { unified } from "unified";
import { ATOM, splitText } from "./obsidian";

type Block = { key: string; start: number; end: number };

export const STRINGIFY: Options = { bullet: "-", emphasis: "*", strong: "*", rule: "-", fence: "`", listItemIndent: "one" };

function liftAtoms(node: { children?: unknown[] }) {
  if (!Array.isArray(node.children)) return;
  node.children = node.children.flatMap((child): unknown[] => {
    const c = child as { type: string; value?: string; children?: unknown[] };
    if (c.type === "text") return splitText(c.value ?? "");
    if (c.type !== "code" && c.type !== "inlineCode" && c.type !== "html") liftAtoms(c);
    return [c];
  });
}

const parser = unified().use(remarkParse).use(remarkGfm);
const printer = unified()
  .use(remarkGfm)
  .use(remarkStringify, {
    ...STRINGIFY,
    handlers: { [ATOM]: (node: { value: string }) => node.value } as never,
  });

/** Strip positions so two blocks compare by content only. */
function key(node: RootContent): string {
  const clone = structuredClone(node) as RootContent;
  const strip = (n: { position?: unknown; children?: unknown[] }) => {
    delete n.position;
    n.children?.forEach((c) => strip(c as typeof n));
  };
  strip(clone as never);
  return printer.stringify({ type: "root", children: [clone] } as Root);
}

export function blocks(text: string): Block[] {
  const tree = parser.parse(text) as Root;
  liftAtoms(tree as never);
  return tree.children
    .filter((n) => n.position?.start.offset !== undefined && n.position?.end.offset !== undefined)
    .map((n) => ({ key: key(n), start: n.position!.start.offset!, end: n.position!.end.offset! }));
}

/** Longest common subsequence of block keys: pairs of (original index, edited index). */
function match(a: Block[], b: Block[]): Map<number, number> {
  const dp = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      dp[i]![j] = a[i]!.key === b[j]!.key ? dp[i + 1]![j + 1]! + 1 : Math.max(dp[i + 1]![j]!, dp[i]![j + 1]!);
  const pairs = new Map<number, number>(); // edited index -> original index
  for (let i = 0, j = 0; i < a.length && j < b.length; ) {
    if (a[i]!.key === b[j]!.key) pairs.set(j++, i++);
    else if (dp[i + 1]![j]! >= dp[i]![j + 1]!) i++;
    else j++;
  }
  return pairs;
}

/**
 * The text to save: `edited` with every unchanged block taken from `original`.
 * Both are markdown bodies without frontmatter.
 */
export function preserveUntouched(original: string, edited: string): string {
  const a = blocks(original);
  const b = blocks(edited);
  const pairs = match(a, b);
  let out = "";
  let prev: { orig: number | null; editedEnd: number } | null = null;
  b.forEach((block, j) => {
    const i = pairs.get(j);
    if (prev === null) {
      // Leading text before the first block: the original's if it starts the same way.
      out += i === 0 ? original.slice(0, a[0]!.start) : edited.slice(0, block.start);
    } else if (i !== undefined && prev.orig !== null && i === prev.orig + 1) {
      out += original.slice(a[prev.orig]!.end, a[i]!.start); // original spacing
    } else {
      out += edited.slice(prev.editedEnd, block.start);
    }
    out += i !== undefined ? original.slice(a[i]!.start, a[i]!.end) : edited.slice(block.start, block.end);
    prev = { orig: i ?? null, editedEnd: block.end };
  });
  if (!b.length) return edited;
  const last = prev as { orig: number | null; editedEnd: number } | null;
  out +=
    last && last.orig === a.length - 1 ? original.slice(a[a.length - 1]!.end) : edited.slice(last!.editedEnd);
  return out;
}
