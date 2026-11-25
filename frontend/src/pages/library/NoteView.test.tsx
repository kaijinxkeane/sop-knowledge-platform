import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeQueryClient } from "@/app/App";
import { session } from "@/auth/session";
import { mockFetch } from "@/test/utils";
import type { Doc } from "./api";
import { NoteView } from "./NoteView";

const base = {
  kind: "attachment",
  status: "published",
  programme: null,
  stage: null,
  owner: null,
  access: [{ space: "core", sensitivity: "internal" }],
  approved: true,
  pending_change: false,
  review_due: null,
};
const diagram = { ...base, id: "i1", title: "Journey Map", vault_path: "Training Content/Attachments/Journey Map.png", doc_type: "image" } as unknown as Doc;
const photo = { ...base, id: "i2", title: "Room Setup", vault_path: "Attachments/Room Setup.jpg", doc_type: "image" } as unknown as Doc;

function show(text: string, docs: Doc[]) {
  const qc = makeQueryClient();
  qc.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><NoteView text={text} docs={docs} /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  session.signIn("t");
  URL.createObjectURL = vi.fn(() => "blob:http://localhost/img");
  URL.revokeObjectURL = vi.fn();
});

describe("images in notes", () => {
  it("shows a readable vault image from ![[embed]] and ![](path), fetched with the token", async () => {
    const { calls } = mockFetch({
      "GET /api/v1/documents/i1/file": () => new Response(new Uint8Array([137, 80, 78, 71])),
      "GET /api/v1/documents/i2/file": () => new Response(new Uint8Array([255, 216])),
    });
    show("![[Journey Map.png|400]]\n\n![The room](../Attachments/Room%20Setup.jpg)\n", [diagram, photo]);
    await waitFor(() => expect(screen.getAllByRole("img")).toHaveLength(2));
    const imgs = screen.getAllByRole("img");
    expect(imgs.map((i) => i.getAttribute("alt"))).toEqual(["Journey Map", "The room"]);
    expect(imgs.every((i) => i.getAttribute("src")?.startsWith("blob:"))).toBe(true);
    expect(calls.every((c) => c.headers.get("Authorization") === "Bearer t")).toBe(true);
  });

  it("never fetches outside images or images the reader can't open", async () => {
    const { fn } = mockFetch({});
    show("![tracker](https://evil.example/pixel.png)\n\n![[Secret Diagram.png]]\n", [diagram]);
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText("[tracker]")).toBeInTheDocument();
    await waitFor(() => expect(fn).not.toHaveBeenCalled());
  });
});

describe("formatting in notes", () => {
  it("shows callouts as coloured boxes and highlights as highlights", () => {
    mockFetch({});
    show("> [!warning] Check the date\n> Rooms fill fast.\n\nPlain quote:\n\n> just a quote\n\nBring ==spare markers==.", []);
    const warning = screen.getByText("Warning: Check the date").closest("blockquote")!;
    expect(warning).toHaveClass("sop-callout", "sop-callout-amber");
    expect(warning).toHaveTextContent("Rooms fill fast.");
    expect(screen.getByText("just a quote").closest("blockquote")).not.toHaveClass("sop-callout");
    const mark = screen.getByText("spare markers");
    expect(mark.tagName).toBe("MARK");
    expect(document.body.textContent).not.toContain("==");
  });
});
