import type { Editor } from "@milkdown/kit/core";
import { redoCommand, undoCommand } from "@milkdown/kit/plugin/history";
import {
  toggleEmphasisCommand,
  toggleStrongCommand,
  wrapInBlockquoteCommand,
  wrapInBulletListCommand,
  wrapInHeadingCommand,
  wrapInOrderedListCommand,
} from "@milkdown/kit/preset/commonmark";
import { insertTableCommand } from "@milkdown/kit/preset/gfm";
import { callCommand, getMarkdown, insert } from "@milkdown/kit/utils";
import {
  Bold,
  Heading1,
  Heading2,
  Italic,
  Link2,
  List,
  ListOrdered,
  MessageSquareWarning,
  Quote,
  Redo2,
  Table,
  Undo2,
} from "lucide-react";
import { useEffect, useRef, type ReactNode, type RefObject } from "react";
import { t, type MessageKey } from "@/i18n";
import { createEditor, envelope, replaceContent } from "./editor";

export type EditorHandle = {
  /** Insert markdown at the cursor (parsed, so [[links]] become atoms); `inline` keeps it in the paragraph. */
  insert: (markdown: string, inline?: boolean) => void;
  /** Replace the whole body (after a merge or an upload); returns the new baseline. */
  replace: (markdown: string) => string;
};

type Props = {
  /** The body (no frontmatter) to open with. */
  initial: string;
  label: string;
  /** Called with the editor's markdown, wrapped in the original's whitespace. */
  onChange: (markdown: string) => void;
  /** Called once with the editor's first serialisation: the "unchanged" baseline. */
  onReady: (baseline: string) => void;
  handle: RefObject<EditorHandle | null>;
  onInsertLink: () => void;
};

function Tool({ label, onClick, children }: { label: MessageKey; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onMouseDown={(e) => e.preventDefault()} // keep the editor's selection
      onClick={onClick}
      aria-label={t(label)}
      title={t(label)}
      className="rounded p-1.5 hover:bg-accent [&_svg]:size-4"
    >
      {children}
    </button>
  );
}

export default function MilkdownEditor({ initial, label, onChange, onReady, handle, onInsertLink }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const editor = useRef<Editor | null>(null);
  const callbacks = useRef({ onChange, onReady });
  useEffect(() => {
    callbacks.current = { onChange, onReady };
  });

  useEffect(() => {
    let cancelled = false;
    const el = root.current!;
    let env = envelope(initial);
    const wrap = (md: string) => env.lead + md.replace(/\s+$/, "") + env.trail;
    let made: Editor | null = null;
    void createEditor({
      root: el,
      markdown: initial,
      onChange: (md) => callbacks.current.onChange(wrap(md)),
    }).then((e) => {
      made = e;
      if (cancelled) return void e.destroy();
      editor.current = e;
      el.querySelector(".ProseMirror")?.setAttribute("aria-label", label);
      // Its first serialisation is what "unchanged" looks like.
      callbacks.current.onReady(wrap(e.action(getMarkdown())));
      handle.current = {
        insert: (md, inline) => e.action(insert(md, inline)),
        replace: (md) => {
          env = envelope(md);
          replaceContent(e, md);
          return wrap(e.action(getMarkdown()));
        },
      };
    });
    return () => {
      cancelled = true;
      handle.current = null;
      editor.current = null;
      void made?.destroy();
    };
    // Opened once per note; later content arrives through `handle.replace`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = (cmd: { key: unknown }, payload?: unknown) =>
    editor.current?.action(callCommand(cmd.key as never, payload as never));

  return (
    <div className="rounded-md border">
      <div role="toolbar" aria-label={t("write.toolbar")} className="flex flex-wrap gap-0.5 border-b p-1">
        <Tool label="write.h1" onClick={() => run(wrapInHeadingCommand, 1)}><Heading1 /></Tool>
        <Tool label="write.h2" onClick={() => run(wrapInHeadingCommand, 2)}><Heading2 /></Tool>
        <Tool label="write.bold" onClick={() => run(toggleStrongCommand)}><Bold /></Tool>
        <Tool label="write.italic" onClick={() => run(toggleEmphasisCommand)}><Italic /></Tool>
        <Tool label="write.bullets" onClick={() => run(wrapInBulletListCommand)}><List /></Tool>
        <Tool label="write.numbers" onClick={() => run(wrapInOrderedListCommand)}><ListOrdered /></Tool>
        <Tool label="write.table" onClick={() => run(insertTableCommand, { row: 3, col: 3 })}><Table /></Tool>
        <Tool label="write.quote" onClick={() => run(wrapInBlockquoteCommand)}><Quote /></Tool>
        <Tool label="write.callout" onClick={() => handle.current?.insert("> [!note] \n")}>
          <MessageSquareWarning />
        </Tool>
        <Tool label="write.link" onClick={onInsertLink}><Link2 /></Tool>
        <Tool label="write.undo" onClick={() => run(undoCommand)}><Undo2 /></Tool>
        <Tool label="write.redo" onClick={() => run(redoCommand)}><Redo2 /></Tool>
      </div>
      <div ref={root} className="prose-sop sop-editor min-h-[50vh] px-4 py-3" />
    </div>
  );
}
