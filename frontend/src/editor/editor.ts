/**
 * The visual editor (plan §8.1): Milkdown, saving Obsidian-compatible markdown.
 *
 * Fidelity rules, checked on every demo-vault note by the round-trip test:
 * - Obsidian syntax is kept as verbatim atoms (./obsidian.ts).
 * - Leading and trailing whitespace of the body is kept as it was.
 * - Stringify settings follow the vault's own style ("-" bullets, "*" emphasis).
 * - If the document is unchanged, the original text is saved byte for byte.
 */
import {
  Editor,
  defaultValueCtx,
  editorViewCtx,
  editorViewOptionsCtx,
  remarkStringifyOptionsCtx,
  rootCtx,
} from "@milkdown/kit/core";
import { history } from "@milkdown/kit/plugin/history";
import { listener, listenerCtx } from "@milkdown/kit/plugin/listener";
import { commonmark } from "@milkdown/kit/preset/commonmark";
import { gfm } from "@milkdown/kit/preset/gfm";
import { getMarkdown, replaceAll } from "@milkdown/kit/utils";
import {
  highlightKeymap,
  highlightSchema,
  obsidianAtomSchema,
  obsidianHandlers,
  remarkObsidian,
  toggleHighlightCommand,
} from "./obsidian";
import { toolbarState, type ToolbarState } from "./commands";
import { STRINGIFY, preserveUntouched } from "./preserve";

/** Whitespace around the body that markdown serialisers drop. */
export function envelope(body: string): { lead: string; core: string; trail: string } {
  const lead = /^\s*/.exec(body)![0];
  const trail = /\s*$/.exec(body.slice(lead.length))![0];
  return { lead, core: body.slice(lead.length, body.length - trail.length), trail };
}

type Options = {
  root: HTMLElement;
  markdown: string;
  editable?: boolean;
  onChange?: (markdown: string) => void;
  /** What the toolbar should show as "on", after every selection or content change. */
  onToolbarState?: (state: ToolbarState) => void;
};

export async function createEditor({ root, markdown, editable = true, onChange, onToolbarState }: Options) {
  const { core } = envelope(markdown);
  const editor = await Editor.make()
    .config((ctx) => {
      ctx.set(rootCtx, root);
      ctx.set(defaultValueCtx, core);
      ctx.update(editorViewOptionsCtx, (prev) => ({ ...prev, editable: () => editable }));
      ctx.update(remarkStringifyOptionsCtx, (prev) => ({
        ...prev,
        ...STRINGIFY,
        handlers: { ...prev.handlers, ...(obsidianHandlers as unknown as Record<string, never>) },
      }));
      if (onChange) {
        ctx.get(listenerCtx).markdownUpdated((_ctx, md) => onChange(md));
      }
      if (onToolbarState) {
        const report = (c: typeof ctx) => {
          // The listener can fire while the editor is still being set up.
          let state;
          try {
            state = c.get(editorViewCtx)?.state;
          } catch {
            return;
          }
          if (state?.selection) onToolbarState(toolbarState(state));
        };
        ctx.get(listenerCtx).selectionUpdated(report).updated(report);
      }
    })
    .use(commonmark)
    .use(gfm)
    .use(history)
    .use(listener)
    .use(remarkObsidian)
    .use(obsidianAtomSchema)
    .use(highlightSchema)
    .use(toggleHighlightCommand)
    .use(highlightKeymap)
    .create();
  return editor;
}

/** The markdown the editor holds now, with the original whitespace envelope. */
export function currentMarkdown(editor: Editor, original: string): string {
  const { lead, trail } = envelope(original);
  return lead + editor.action(getMarkdown()).replace(/\s+$/, "") + trail;
}

/**
 * What to save: the original text if nothing changed, else the edit with
 * every untouched block restored to its original source (./preserve.ts).
 */
export function bodyToSave(original: string, baseline: string, now: string): string {
  return now === baseline ? original : preserveUntouched(original, now);
}

export function replaceContent(editor: Editor, markdown: string) {
  editor.action(replaceAll(envelope(markdown).core));
}

/** Parse and serialise once, headless: the round-trip test and the baseline. */
export async function roundTrip(markdown: string): Promise<string> {
  const root = document.createElement("div");
  const editor = await createEditor({ root, markdown, editable: false });
  const out = currentMarkdown(editor, markdown);
  await editor.destroy();
  return out;
}
