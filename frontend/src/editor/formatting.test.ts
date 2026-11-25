import { editorViewCtx, type Editor } from "@milkdown/kit/core";
import { turnIntoTextCommand, wrapInHeadingCommand } from "@milkdown/kit/preset/commonmark";
import { TextSelection } from "@milkdown/kit/prose/state";
import { callCommand, getMarkdown } from "@milkdown/kit/utils";
import { afterEach, describe, expect, it } from "vitest";
import { clearFormatting, setList, toolbarState, type ToolbarState } from "./commands";
import { createEditor } from "./editor";
import { toggleHighlightCommand } from "./obsidian";

let editor: Editor | null = null;
afterEach(async () => {
  await editor?.destroy();
  editor = null;
});

async function open(markdown: string, seen: ToolbarState[] = []) {
  editor = await createEditor({ root: document.createElement("div"), markdown, onToolbarState: (s) => seen.push(s) });
  return editor;
}

/** Select `text` (first occurrence); an empty string puts the cursor at the start of the first text. */
function select(e: Editor, text: string, collapse = false) {
  e.action((ctx) => {
    const view = ctx.get(editorViewCtx);
    let from = -1;
    view.state.doc.descendants((node, pos) => {
      if (from < 0 && node.isText && node.text!.includes(text)) from = pos + node.text!.indexOf(text);
    });
    const to = collapse ? from : from + text.length;
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, from, to)));
  });
}

const md = (e: Editor) => e.action(getMarkdown()).trim();
const ui = (e: Editor) => e.action((ctx) => toolbarState(ctx.get(editorViewCtx).state));

describe("text style", () => {
  it("turns a heading back into normal text", async () => {
    const e = await open("Arrive early");
    select(e, "Arrive");
    e.action(callCommand(wrapInHeadingCommand.key, 2));
    expect(md(e)).toBe("## Arrive early");
    expect(ui(e).level).toBe(2);
    e.action(callCommand(turnIntoTextCommand.key));
    expect(md(e)).toBe("Arrive early");
    expect(ui(e).level).toBe(0);
  });
});

describe("highlight", () => {
  it("shows highlighted text as formatting, not ==text==, and saves it as ==text==", async () => {
    const e = await open("Bring ==spare markers== today.");
    const root = e.action((ctx) => ctx.get(editorViewCtx).dom);
    const mark = root.querySelector("mark")!;
    expect(mark.textContent).toBe("spare markers");
    expect(root.textContent).not.toContain("==");
    expect(md(e)).toBe("Bring ==spare markers== today.");
  });

  it("toggles on and off like bold", async () => {
    const e = await open("Bring spare markers to the room.");
    select(e, "spare markers");
    e.action(callCommand(toggleHighlightCommand.key));
    expect(md(e)).toBe("Bring ==spare markers== to the room.");
    expect(ui(e).marks.has("highlight")).toBe(true);
    e.action(callCommand(toggleHighlightCommand.key));
    expect(md(e)).toBe("Bring spare markers to the room.");
  });

  it("keeps highlighted text editable", async () => {
    const e = await open("==spare markers==");
    select(e, "markers", true);
    e.action((ctx) => {
      const view = ctx.get(editorViewCtx);
      view.dispatch(view.state.tr.insertText("blue "));
    });
    expect(md(e)).toBe("==spare blue markers==");
  });
});

describe("lists", () => {
  it("switches bullets to numbers and back in place, like Word", async () => {
    const e = await open("- one\n- two\n- three");
    select(e, "two", true);
    setList(e, "ordered_list");
    expect(md(e)).toBe("1. one\n2. two\n3. three");
    expect(ui(e).list).toBe("ordered_list");
    setList(e, "bullet_list");
    expect(md(e)).toBe("- one\n- two\n- three");
  });

  it("starts a list from text, and pressing the same button again ends it", async () => {
    const e = await open("Plain line");
    select(e, "Plain", true);
    setList(e, "bullet_list");
    expect(md(e)).toBe("- Plain line");
    setList(e, "bullet_list");
    expect(md(e)).toBe("Plain line");
  });
});

describe("clear formatting", () => {
  it("removes bold, italic and highlight from the selection, but keeps links", async () => {
    const e = await open("**bold** *it* ==hi== [site](https://example.com)");
    e.action((ctx) => {
      const view = ctx.get(editorViewCtx);
      view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 1, view.state.doc.content.size - 1)));
    });
    clearFormatting(e);
    expect(md(e)).toBe("bold it hi [site](https://example.com)");
  });
});
