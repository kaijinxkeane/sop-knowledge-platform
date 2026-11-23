import { describe, expect, it } from "vitest";
import { fold, lineDiff, stats } from "./diff";

describe("line diff", () => {
  it("pairs a replaced line as changed", () => {
    const rows = lineDiff("a\nb\nc", "a\nB\nc");
    expect(rows.map((r) => r.kind)).toEqual(["same", "changed", "same"]);
    expect(stats(rows)).toEqual({ added: 0, removed: 0, changed: 1 });
  });

  it("shows added and removed lines with their own numbers", () => {
    const rows = lineDiff("a\nb\nc", "a\nc\nd");
    expect(rows).toEqual([
      { kind: "same", left: "a", right: "a", leftNo: 1, rightNo: 1 },
      { kind: "removed", left: "b", leftNo: 2 },
      { kind: "same", left: "c", right: "c", leftNo: 3, rightNo: 2 },
      { kind: "added", right: "d", rightNo: 3 },
    ]);
  });

  it("is all same for identical text", () => {
    expect(stats(lineDiff("x\ny", "x\ny"))).toEqual({ added: 0, removed: 0, changed: 0 });
  });

  it("folds long unchanged runs around changes", () => {
    const before = Array.from({ length: 30 }, (_, i) => `line ${i}`).join("\n");
    const after = before.replace("line 15", "line fifteen");
    const shown = fold(lineDiff(before, after));
    expect(shown).toHaveLength(3);
    expect(shown[0]).toEqual({ hidden: 12, from: 0 });
    expect("rows" in shown[1]! && shown[1].rows).toHaveLength(7);
    expect(shown[2]).toEqual({ hidden: 11, from: 19 });
  });
});
