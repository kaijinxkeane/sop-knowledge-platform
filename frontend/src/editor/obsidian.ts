/**
 * Obsidian syntax in the editor (plan §8.1). Wikilinks, embeds, tags,
 * callout markers, %%comments%%, ==highlights== and ^block-ids are lifted out
 * of the markdown text as inline atoms that hold their exact source and are
 * written back verbatim, so escaping can never change them.
 */
import { $nodeSchema, $remark } from "@milkdown/kit/utils";
import type { Node as MdNode, Parent, Root, Text } from "mdast";

export const ATOM = "obsidianAtom";

export type AtomKind = "wikilink" | "embed" | "tag" | "callout" | "comment" | "highlight" | "blockid";

// Order matters: embeds before wikilinks; anchored patterns are tried at their own spots.
const PATTERN =
  /(!\[\[[^\]\n]+?\]\])|(\[\[[^\]\n]+?\]\])|(\[![A-Za-z-]+\][+-]?)|(%%[^%\n]*%%)|(==[^=\n]+==)|((?<=^|\s)#[A-Za-z][\w/-]*)|((?<=\s)\^[A-Za-z0-9-]+$)/g;

const KINDS: AtomKind[] = ["embed", "wikilink", "callout", "comment", "highlight", "tag", "blockid"];

export function kindOf(source: string): AtomKind {
  PATTERN.lastIndex = 0;
  const m = PATTERN.exec(source);
  const i = m ? m.slice(1).findIndex((g) => g !== undefined) : -1;
  return KINDS[i] ?? "wikilink";
}

type AtomNode = MdNode & { type: typeof ATOM; value: string };

/** Split one text value into text and atom nodes. */
export function splitText(value: string): (Text | AtomNode)[] {
  const out: (Text | AtomNode)[] = [];
  let last = 0;
  PATTERN.lastIndex = 0;
  for (let m = PATTERN.exec(value); m; m = PATTERN.exec(value)) {
    if (m.index > last) out.push({ type: "text", value: value.slice(last, m.index) });
    out.push({ type: ATOM, value: m[0] });
    last = m.index + m[0].length;
  }
  if (last < value.length) out.push({ type: "text", value: value.slice(last) });
  return out;
}

function liftAtoms(node: MdNode) {
  const parent = node as Parent;
  if (!Array.isArray(parent.children)) return;
  const next: MdNode[] = [];
  for (const child of parent.children) {
    if (child.type === "text") next.push(...splitText((child as Text).value));
    else if (child.type === "code" || child.type === "inlineCode" || child.type === "html") next.push(child);
    else {
      liftAtoms(child);
      next.push(child);
    }
  }
  parent.children = next as Parent["children"];
}

export const remarkObsidian = $remark("remarkObsidian", () => () => (tree: Root) => {
  liftAtoms(tree);
});

export const obsidianAtomSchema = $nodeSchema(ATOM, () => ({
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,
  attrs: { value: { default: "" } },
  parseDOM: [
    {
      tag: "span[data-obsidian]",
      getAttrs: (dom) => ({ value: (dom as HTMLElement).dataset.obsidian ?? "" }),
    },
  ],
  toDOM: (node) => {
    const value = node.attrs.value as string;
    return [
      "span",
      {
        "data-obsidian": value,
        "data-kind": kindOf(value),
        class: `obsidian-atom obsidian-${kindOf(value)}`,
        contenteditable: "false",
      },
      value,
    ];
  },
  parseMarkdown: {
    match: (node) => node.type === ATOM,
    runner: (state, node, type) => {
      state.addNode(type, { value: (node as unknown as AtomNode).value });
    },
  },
  toMarkdown: {
    match: (node) => node.type.name === ATOM,
    runner: (state, node) => {
      state.addNode(ATOM, undefined, node.attrs.value as string);
    },
  },
}));

/** remark-stringify handler: the atom's source, untouched. */
export const atomHandler = (node: { value: string }) => node.value;
