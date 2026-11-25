import type { Editor } from "@milkdown/kit/core";
import { editorViewCtx } from "@milkdown/kit/core";
import { redoCommand, undoCommand } from "@milkdown/kit/plugin/history";
import {
  insertHrCommand,
  liftListItemCommand,
  sinkListItemCommand,
  toggleEmphasisCommand,
  toggleInlineCodeCommand,
  toggleStrongCommand,
  turnIntoTextCommand,
  wrapInBlockquoteCommand,
  wrapInHeadingCommand,
} from "@milkdown/kit/preset/commonmark";
import {
  addColAfterCommand,
  addRowAfterCommand,
  deleteSelectedCellsCommand,
  insertTableCommand,
  selectColCommand,
  selectRowCommand,
  selectTableCommand,
  toggleStrikethroughCommand,
} from "@milkdown/kit/preset/gfm";
import { callCommand, getMarkdown, insert } from "@milkdown/kit/utils";
import {
  Bold,
  Code,
  Highlighter,
  IndentDecrease,
  IndentIncrease,
  Italic,
  Link2,
  List,
  ListOrdered,
  Minus,
  Quote,
  Redo2,
  RemoveFormatting,
  Strikethrough,
  Table,
  Undo2,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { t, type MessageKey } from "@/i18n";
import { clearFormatting, setList, toolbarState, type ListKind, type ToolbarState } from "./commands";
import { createEditor, envelope, replaceContent } from "./editor";
import { toggleHighlightCommand } from "./obsidian";

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

function Tool({
  label,
  onClick,
  children,
  on,
}: {
  label: MessageKey;
  onClick: () => void;
  children: ReactNode;
  on?: boolean;
}) {
  return (
    <button
      type="button"
      onMouseDown={(e) => e.preventDefault()} // keep the editor's selection
      onClick={onClick}
      aria-label={t(label)}
      aria-pressed={on === undefined ? undefined : on}
      title={t(label)}
      className={`rounded p-1.5 hover:bg-accent [&_svg]:size-4 ${on ? "bg-accent text-primary ring-1 ring-border" : ""}`}
    >
      {children}
    </button>
  );
}

const Divider = () => <span aria-hidden="true" className="mx-1 my-1 w-px self-stretch bg-border" />;

function TextTool({ label, onClick }: { label: MessageKey; onClick: () => void }) {
  return (
    <button
      type="button"
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className="rounded px-2 py-1 text-xs hover:bg-accent"
    >
      {t(label)}
    </button>
  );
}

const EMPTY: ToolbarState = { level: 0, marks: new Set(), list: null, quote: false, table: false };

export default function MilkdownEditor({ initial, label, onChange, onReady, handle, onInsertLink }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const editor = useRef<Editor | null>(null);
  const callbacks = useRef({ onChange, onReady });
  const [ui, setUi] = useState<ToolbarState>(EMPTY);
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
      onToolbarState: setUi,
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

  /** Re-read the toolbar state (stored marks change without an editor event). */
  const refresh = () => {
    const e = editor.current;
    if (e) setUi(e.action((ctx) => toolbarState(ctx.get(editorViewCtx).state)));
  };
  const run = (cmd: { key: unknown }, payload?: unknown) => {
    editor.current?.action(callCommand(cmd.key as never, payload as never));
    refresh();
  };
  const list = (kind: ListKind) => {
    if (editor.current) setList(editor.current, kind);
    refresh();
  };
  const focus = () => (root.current?.querySelector(".ProseMirror") as HTMLElement | null)?.focus();
  const on = (mark: string) => ui.marks.has(mark);

  return (
    <div className="rounded-md border">
      <div
        role="toolbar"
        aria-label={t("write.toolbar")}
        className="sticky top-0 z-10 flex flex-wrap items-center gap-0.5 rounded-t-md border-b bg-background p-1"
      >
        <Tool label="write.undo" onClick={() => run(undoCommand)}><Undo2 /></Tool>
        <Tool label="write.redo" onClick={() => run(redoCommand)}><Redo2 /></Tool>
        <Divider />
        <select
          aria-label={t("write.textStyle")}
          title={t("write.textStyle")}
          value={ui.level}
          onChange={(e) => {
            const next = Number(e.target.value);
            if (next === 0) run(turnIntoTextCommand);
            else run(wrapInHeadingCommand, next);
            focus();
          }}
          className="h-8 rounded border bg-background px-1.5 text-sm"
        >
          <option value={0}>{t("write.normalText")}</option>
          <option value={1}>{t("write.heading", { n: 1 })}</option>
          <option value={2}>{t("write.heading", { n: 2 })}</option>
          <option value={3}>{t("write.heading", { n: 3 })}</option>
        </select>
        <Divider />
        <Tool label="write.bold" on={on("strong")} onClick={() => run(toggleStrongCommand)}><Bold /></Tool>
        <Tool label="write.italic" on={on("emphasis")} onClick={() => run(toggleEmphasisCommand)}><Italic /></Tool>
        <Tool label="write.strike" on={on("strike_through")} onClick={() => run(toggleStrikethroughCommand)}><Strikethrough /></Tool>
        <Tool label="write.highlight" on={on("highlight")} onClick={() => run(toggleHighlightCommand)}><Highlighter /></Tool>
        <Tool label="write.code" on={on("inlineCode")} onClick={() => run(toggleInlineCodeCommand)}><Code /></Tool>
        <Tool
          label="write.clear"
          onClick={() => {
            if (editor.current) clearFormatting(editor.current);
            refresh();
          }}
        >
          <RemoveFormatting />
        </Tool>
        <Divider />
        <Tool label="write.bullets" on={ui.list === "bullet_list"} onClick={() => list("bullet_list")}><List /></Tool>
        <Tool label="write.numbers" on={ui.list === "ordered_list"} onClick={() => list("ordered_list")}><ListOrdered /></Tool>
        {ui.list && (
          <>
            <Tool label="write.outdent" onClick={() => run(liftListItemCommand)}><IndentDecrease /></Tool>
            <Tool label="write.indent" onClick={() => run(sinkListItemCommand)}><IndentIncrease /></Tool>
          </>
        )}
        <Divider />
        <Tool label="write.quote" on={ui.quote} onClick={() => run(wrapInBlockquoteCommand)}><Quote /></Tool>
        <select
          aria-label={t("write.callout")}
          title={t("write.callout")}
          value=""
          onChange={(e) => {
            const kind = e.target.value;
            if (!kind) return;
            handle.current?.insert(`> [!${kind}] \n`);
            focus();
          }}
          className="h-8 rounded border bg-background px-1.5 text-sm"
        >
          <option value="">{t("write.calloutPick")}</option>
          {(["note", "tip", "warning", "danger"] as const).map((k) => (
            <option key={k} value={k}>{t(`write.callout.${k}`)}</option>
          ))}
        </select>
        <Tool label="write.divider" onClick={() => run(insertHrCommand)}><Minus /></Tool>
        <Tool label="write.link" onClick={onInsertLink}><Link2 /></Tool>
        <Tool label="write.table" on={ui.table} onClick={() => run(insertTableCommand, { row: 3, col: 3 })}><Table /></Tool>
        {ui.table && (
          <span role="group" aria-label={t("write.tableTools")} className="ml-1 flex items-center gap-0.5 rounded border px-0.5">
            <TextTool label="write.addRow" onClick={() => run(addRowAfterCommand)} />
            <TextTool label="write.addCol" onClick={() => run(addColAfterCommand)} />
            <TextTool
              label="write.deleteRow"
              onClick={() => {
                run(selectRowCommand, { index: rowIndex(editor.current) });
                run(deleteSelectedCellsCommand);
              }}
            />
            <TextTool
              label="write.deleteCol"
              onClick={() => {
                run(selectColCommand, { index: colIndex(editor.current) });
                run(deleteSelectedCellsCommand);
              }}
            />
            <TextTool
              label="write.deleteTable"
              onClick={() => {
                run(selectTableCommand);
                run(deleteSelectedCellsCommand);
              }}
            />
          </span>
        )}
      </div>
      <div ref={root} className="prose-sop sop-editor min-h-[50vh] px-4 py-3" />
    </div>
  );
}

/** Row / column of the cell holding the cursor (for the table tools). */
function cellIndex(editor: Editor | null, of: "row" | "col"): number {
  if (!editor) return 0;
  return editor.action((ctx) => {
    const { $from } = ctx.get(editorViewCtx).state.selection;
    for (let d = $from.depth; d > 0; d--) {
      const name = $from.node(d).type.name;
      if (name === "table_row" || name === "table_header_row") {
        return of === "col" ? $from.index(d) : $from.index(d - 1);
      }
    }
    return 0;
  });
}
const rowIndex = (e: Editor | null) => cellIndex(e, "row");
const colIndex = (e: Editor | null) => cellIndex(e, "col");
