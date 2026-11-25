import { describe, expect, it } from "vitest";
import { spaceLabel } from "./spaceLabel";

describe("spaceLabel", () => {
  it("puts abbreviations in capitals and capitalises other names", () => {
    expect(["hr", "it", "core", "marketing", "p-acme", "", null].map(spaceLabel)).toEqual([
      "HR",
      "IT",
      "Core",
      "Marketing",
      "P Acme",
      "",
      "",
    ]);
  });
});
