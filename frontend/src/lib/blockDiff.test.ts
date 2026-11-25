import { describe, expect, it } from "vitest";
import { blockDiff, blocks, detailChanges } from "./blockDiff";

describe("formatted compare", () => {
  it("cuts a note into blocks, one per list item", () => {
    expect(blocks("# Title\n\nIntro text\nstill intro.\n\n- one\n- two\n\n1. first\n2. second\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")).toEqual([
      "# Title",
      "Intro text\nstill intro.",
      "- one",
      "- two",
      "1. first",
      "2. second",
      "| a | b |\n|---|---|\n| 1 | 2 |",
    ]);
  });

  it("marks only the list item that changed", () => {
    const rows = blockDiff("- one\n- two\n- three\n", "- one\n- 2\n- three\n- four\n");
    expect(rows.map((r) => r.kind)).toEqual(["same", "changed", "same", "added"]);
  });

  it("ignores frontmatter in the body and reports changed details field by field", () => {
    const a = "---\ntitle: Leave\nsensitivity: internal\nowner: \"[[Pat]]\"\n---\nBody\n";
    const b = "---\ntitle: Leave\nsensitivity: restricted\nreview_cycle_days: 90\n---\nBody\n";
    expect(blockDiff(a, b).map((r) => r.kind)).toEqual(["same"]);
    expect(detailChanges(a, b)).toEqual([
      { key: "sensitivity", before: "internal", after: "restricted" },
      { key: "owner", before: "\"[[Pat]]\"", after: null },
      { key: "review_cycle_days", before: null, after: "90" },
    ]);
  });
});
