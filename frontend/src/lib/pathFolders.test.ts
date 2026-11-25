import { describe, expect, it } from "vitest";
import { departmentFolders, docsIn, stepsFromFolder } from "./pathFolders";

const P = "Programmes/Signature";
const doc = (id: string, vault_path: string, space = "core") => ({ id, title: id, vault_path, space });
const DOCS = [
  doc("Overview", `${P}/Overview.md`),
  doc("Workshop", `${P}/01 Discovery/Workshop.md`),
  doc("Intake", `${P}/01 Discovery/Intake.md`),
  doc("Strategy", `${P}/02 Strategy/Strategy.md`),
  doc("Wrap", `${P}/10 Wrap-up/Wrap.md`),
  doc("Leave", "HR/Leave.md", "hr"),
  doc("Guide", "Help/Guide.md"),
];

describe("paths from folders", () => {
  it("lists only the department's folders, never Help or another department", () => {
    expect(departmentFolders(DOCS, "core")).toEqual([
      "Programmes",
      P,
      `${P}/01 Discovery`,
      `${P}/02 Strategy`,
      `${P}/10 Wrap-up`,
    ]);
    expect(docsIn(DOCS, "core", "HR")).toEqual([]);
  });

  it("makes one step per subfolder in number order, folder's own documents first", () => {
    const steps = stepsFromFolder(DOCS, "core", P);
    expect(steps.map((s) => s.title)).toEqual(["Signature", "01 Discovery", "02 Strategy", "10 Wrap-up"]);
    expect(steps[1]!.docs.map((d) => d.id)).toEqual(["Intake", "Workshop"]);
  });
});
