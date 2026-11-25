/**
 * Word/Docs-style editing on top of Milkdown: list buttons that switch type
 * in place, clear formatting, and the toolbar's "on" states.
 */
import type { Editor } from "@milkdown/kit/core";
import { editorViewCtx } from "@milkdown/kit/core";
import { liftListItem, wrapInList } from "@milkdown/kit/prose/schema-list";
import type { EditorState } from "@milkdown/kit/prose/state";
import type { EditorView } from "@milkdown/kit/prose/view";

export type ListKind = "bullet_list" | "ordered_list";

export type ToolbarState = {
  level: number; // heading level of the block, 0 = normal text
  marks: Set<string>; // strong, emphasis, strike_through, highlight, inlineCode
  list: ListKind | null;
  quote: boolean;
  table: boolean;
};

function withView<T>(editor: Editor, fn: (view: EditorView) => T): T {
  return editor.action((ctx) => fn(ctx.get(editorViewCtx)));
}

/** The innermost list around the cursor, with its position. */
function listAround(state: EditorState): { pos: number; kind: ListKind; depth: number } | null {
  const { $from } = state.selection;
  for (let d = $from.depth; d > 0; d--) {
    const name = $from.node(d).type.name;
    if (name === "bullet_list" || name === "ordered_list") {
      return { pos: $from.before(d), kind: name, depth: d };
    }
  }
  return null;
}

/**
 * Bullets/numbers button, like Word: outside a list, start one; in a list of
 * the other kind, switch the whole list in place; in a list of this kind,
 * turn the item back into normal text.
 */
export function setList(editor: Editor, kind: ListKind): void {
  withView(editor, (view) => {
    const { state } = view;
    const target = state.schema.nodes[kind];
    const item = state.schema.nodes["list_item"];
    if (!target || !item) return;
    const around = listAround(state);
    if (!around) {
      wrapInList(target)(state, view.dispatch);
    } else if (around.kind === kind) {
      liftListItem(item)(state, view.dispatch);
    } else {
      const list = state.doc.nodeAt(around.pos)!;
      const attrs = kind === "ordered_list" ? { order: 1, spread: list.attrs.spread } : { spread: list.attrs.spread };
      const tr = state.tr.setNodeMarkup(around.pos, target, attrs);
      // Items carry their list type too (it decides "-" or "1." when saved).
      const listType = kind === "ordered_list" ? "ordered" : "bullet";
      list.forEach((child, offset, index) => {
        if (child.type !== item) return;
        const label = listType === "ordered" ? `${index + 1}.` : "•";
        tr.setNodeMarkup(around.pos + 1 + offset, undefined, { ...child.attrs, listType, label });
      });
      view.dispatch(tr);
    }
    view.focus();
  });
}

/** Remove bold, italic, highlight and the rest from the selection. */
export function clearFormatting(editor: Editor): void {
  withView(editor, (view) => {
    const { state } = view;
    const { from, to, empty } = state.selection;
    if (empty) {
      view.dispatch(state.tr.setStoredMarks([]));
    } else {
      let tr = state.tr;
      for (const mark of Object.values(state.schema.marks)) {
        if (mark.name === "link") continue; // links aren't "formatting"
        tr = tr.removeMark(from, to, mark);
      }
      view.dispatch(tr);
    }
    view.focus();
  });
}

/** What the toolbar shows as "on" for the current selection. */
export function toolbarState(state: EditorState): ToolbarState {
  const { $from, from, to, empty } = state.selection;
  const marks = new Set<string>();
  const active = empty ? (state.storedMarks ?? $from.marks()) : [];
  for (const m of active) marks.add(m.type.name);
  if (!empty) {
    for (const type of Object.values(state.schema.marks)) {
      if (state.doc.rangeHasMark(from, to, type)) marks.add(type.name);
    }
  }
  let quote = false;
  let table = false;
  for (let d = $from.depth; d > 0; d--) {
    const name = $from.node(d).type.name;
    if (name === "blockquote") quote = true;
    if (name === "table") table = true;
  }
  const block = $from.parent;
  return {
    level: block.type.name === "heading" ? Number(block.attrs.level) : 0,
    marks,
    list: listAround(state)?.kind ?? null,
    quote,
    table,
  };
}
