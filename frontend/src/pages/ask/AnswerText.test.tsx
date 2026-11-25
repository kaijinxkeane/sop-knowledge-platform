import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { AnswerText, plainWikiLinks } from "./AnswerText";

const readable = (target: string) =>
  ({ "discovery workshop sop": { id: "d1" }, "leave policy": { id: "d4" } })[target.toLowerCase()] ?? null;

describe("answer text", () => {
  it("shows Obsidian links as plain words", () => {
    expect(plainWikiLinks("See [[Leave Policy]] first.")).toBe("See Leave Policy first.");
    expect(plainWikiLinks("Read [[Leave Policy|the leave rules]].")).toBe("Read the leave rules.");
    expect(plainWikiLinks("[[HR/Leave Policy.md#Annual leave]]")).toBe("Leave Policy");
    expect(plainWikiLinks("Open ![[Brand Foundations.pptx]]")).toBe("Open Brand Foundations.pptx");
    expect(plainWikiLinks("Code `[[kept]]` stays")).toBe("Code `[[kept]]` stays");
    expect(plainWikiLinks("Half-streamed [[Leave")).toBe("Half-streamed [[Leave");
  });

  it("links documents the asker can open, and only those", () => {
    expect(plainWikiLinks("See [[Leave Policy|the rules]] and [[Rate Card 2026]].", readable)).toBe(
      "See [the rules](sop-doc:d4) and Rate Card 2026.",
    );
    expect(plainWikiLinks("[[HR/Leave Policy#Annual]]", readable)).toBe("Leave Policy");
    expect(plainWikiLinks("[[Leave Policy#Annual]]", readable)).toBe("[Leave Policy](sop-doc:d4)");
  });

  it("keeps citations clickable next to a cleaned-up link", () => {
    const qc = new QueryClient();
    qc.setQueryData(["documents"], [{ id: "d1", title: "Discovery Workshop SOP", vault_path: "Programmes/Discovery Workshop SOP.md", kind: "note" }]);
    render(
      <QueryClientProvider client={qc}><MemoryRouter><AnswerText
        text="Follow [[Discovery Workshop SOP]] [1]."
        citations={[{ n: 1, document_id: "d1", title: "Discovery Workshop SOP", heading: null, part: null, part_number: null } as never]}
        onCite={() => undefined}
      /></MemoryRouter></QueryClientProvider>,
    );
    expect(screen.getByRole("link", { name: "Discovery Workshop SOP" })).toHaveAttribute("href", "/library/d1");
    expect(screen.queryByText(/\[\[/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Source 1/ })).toBeInTheDocument();
  });
});
