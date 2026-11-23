import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { splitFrontmatter } from "@/lib/obsidian";
import { bodyToSave, roundTrip } from "./editor";
import { clashCount, merge3, resolve } from "./merge";
import { readMeta, writeMeta } from "./meta";
import { preserveUntouched } from "./preserve";

const VAULT = path.resolve(import.meta.dirname, "../../../demo-vault");
const walk = (d: string): string[] =>
  readdirSync(d).flatMap((n) => {
    const p = path.join(d, n);
    return statSync(p).isDirectory() ? walk(p) : p.endsWith(".md") ? [p] : [];
  });
const NOTES = walk(VAULT);

describe("round trip on the demo vault (plan §8.1)", () => {
  it("finds the notes", () => expect(NOTES.length).toBeGreaterThan(20));

  it.each(NOTES.map((f) => [path.relative(VAULT, f), f]))(
    "opening and saving %s changes nothing",
    async (_name, file) => {
      const { body } = splitFrontmatter(readFileSync(file, "utf8"));
      const rt = await roundTrip(body);
      // Unchanged: the original is saved as is.
      expect(bodyToSave(body, rt, rt)).toBe(body);
      // Even when the editor re-wrote everything, untouched blocks come back exactly.
      expect(preserveUntouched(body, rt)).toBe(body);
    },
  );
});

describe("editing keeps the rest of the note exact", () => {
  const note = readFileSync(
    path.join(VAULT, "Programmes/Signature Personal Brand Programme/01 Discovery/Discovery Workshop SOP.md"),
    "utf8",
  );
  const { body } = splitFrontmatter(note);

  it("a one-word change touches one line", async () => {
    const rt = await roundTrip(body);
    const edited = rt.replace("3 hours", "4 hours");
    const saved = bodyToSave(body, rt, edited);
    const a = body.split("\n"), b = saved.split("\n");
    expect(b.length).toBe(a.length);
    expect(a.filter((l, i) => l !== b[i])).toEqual([expect.stringContaining("3 hours")]);
  });

  it("keeps Obsidian syntax verbatim through the editor", async () => {
    const text = "See [[Leave Policy|the *leave* rules]] and ![[Deck.pptx]] #tag ==hi== %%note%%\n\n> [!warning] Careful\n> Body ^block-1\n";
    expect(await roundTrip(text)).toBe(text);
  });
});

describe("merge", () => {
  const base = "---\ntitle: A\n---\n# A\n\nOne.\n\nTwo.\n\nThree.\n";

  it("takes changes to different blocks from both sides", () => {
    const mine = base.replace("One.", "One, mine.");
    const theirs = base.replace("Three.", "Three, theirs.");
    const parts = merge3(base, mine, theirs);
    expect(clashCount(parts)).toBe(0);
    expect(resolve(parts, [])).toBe(base.replace("One.", "One, mine.").replace("Three.", "Three, theirs."));
  });

  it("asks when both changed the same block", () => {
    const parts = merge3(base, base.replace("Two.", "Two, mine."), base.replace("Two.", "Two, theirs."));
    expect(clashCount(parts)).toBe(1);
    expect(resolve(parts, ["theirs"])).toBe(base.replace("Two.", "Two, theirs."));
    expect(resolve(parts, ["mine"])).toBe(base.replace("Two.", "Two, mine."));
  });

  it("merges frontmatter as its own block", () => {
    const mine = base.replace("title: A", "title: B");
    const theirs = base.replace("Two.", "Two, theirs.");
    expect(resolve(merge3(base, mine, theirs), [])).toBe(mine.replace("Two.", "Two, theirs."));
  });

  it("handles added and removed blocks", () => {
    const mine = base.replace("Three.\n", "Three.\n\nFour.\n");
    const theirs = base.replace("One.\n\n", "");
    expect(resolve(merge3(base, mine, theirs), [])).toBe("---\ntitle: A\n---\n# A\n\nTwo.\n\nThree.\n\nFour.\n");
  });
});

describe("metadata form", () => {
  const note = '---\ndoc_type: sop\n# who to ask\nowner: "[[Avery Tan]]"\nprogramme: "[[Signature]]"\nstage: discovery\ncustom: keep me\n---\n\n# Body\n';

  it("reads links as plain names", () => {
    expect(readMeta(note)).toMatchObject({ owner: "Avery Tan", programme: "Signature", stage: "discovery" });
  });

  it("writes only what changed and keeps comments and unknown fields", () => {
    const out = writeMeta(note, { ...readMeta(note)!, stage: "strategy" });
    expect(out).toBe(note.replace("stage: discovery", "stage: strategy"));
    const owner = writeMeta(note, { owner: "Jordan Lee" });
    expect(owner).toContain('owner: "[[Jordan Lee]]"');
    expect(owner).toContain("# who to ask");
    expect(owner).toContain("custom: keep me");
  });

  it("refuses broken YAML instead of overwriting it", () => {
    expect(readMeta("---\ntitle: [oops\n---\nx")).toBeNull();
    expect(() => writeMeta("---\ntitle: [oops\n---\nx", { title: "y" })).toThrow();
  });
});
