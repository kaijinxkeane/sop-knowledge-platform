import { describe, expect, it } from "vitest";
import { makeMe } from "@/test/utils";
import { visibleSections } from "./permissions";

describe("visibleSections", () => {
  it("shows an employee only Ask and Library", () => {
    expect(visibleSections(makeMe())).toEqual(["ask", "library"]);
  });

  it("adds Write and Review for contributors", () => {
    const me = makeMe({ space_actions: { core: ["ask", "contribute"] } });
    expect(visibleSections(me)).toEqual(["ask", "library", "write", "review", "handovers", "projects"]);
  });

  it("adds Review and Retain for leads who approve", () => {
    const me = makeMe({ space_actions: { core: ["approve", "ask", "contribute", "review"] } });
    expect(visibleSections(me)).toEqual(["ask", "library", "write", "review", "retain", "handovers", "projects"]);
  });

  it("gives HR Retain through gap reports", () => {
    const me = makeMe({ space_actions: { hr: ["ask"] }, global_actions: ["view_gap_reports"] });
    expect(visibleSections(me)).toContain("retain");
  });

  it("gives Admin only to user managers and auditors", () => {
    expect(visibleSections(makeMe({ global_actions: ["manage_users"] }))).toContain("admin");
    expect(visibleSections(makeMe({ global_actions: ["view_audit"] }))).toContain("admin");
    expect(visibleSections(makeMe({ global_actions: ["view_gap_reports"] }))).not.toContain("admin");
  });

  it("shows nothing extra when a user has no actions at all", () => {
    const me = makeMe({ space_actions: {}, global_actions: [] });
    expect(visibleSections(me)).toEqual(["ask", "library"]);
  });
});
