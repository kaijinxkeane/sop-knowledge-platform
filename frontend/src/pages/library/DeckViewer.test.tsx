import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp, type Handler } from "@/test/utils";

const deck = {
  id: "k1",
  title: "Intake Deck",
  vault_path: "Training/Intake Deck.pptx",
  kind: "attachment",
  doc_type: "deck",
  status: "published",
  programme: null,
  stage: null,
  owner: null,
  access: [{ space: "core", sensitivity: "internal" }],
  approved: true,
  pending_change: false,
  review_due: null,
};
const parts = [
  { part: "slide", number: 1, title: "Welcome", speaker_notes: "Say hello." },
  { part: "slide", number: 2, title: "Agenda", speaker_notes: null },
];

function setup(slide: Handler) {
  session.signIn("t");
  return mockFetch({
    "GET /api/v1/me": () => json(makeMe()),
    "GET /api/v1/notifications": () => json([]),
    "GET /api/v1/documents": () => json([deck]),
    "GET /api/v1/documents/k1": () => json(deck),
    "GET /api/v1/documents/k1/parts": () => json(parts),
    "GET /api/v1/documents/k1/backlinks": () => json([]),
    "GET /api/v1/documents/k1/versions": () => json([]),
    "GET /api/v1/me/bookmarks": () => json([]),
    "GET /api/v1/documents/k1/slides/2": slide,
  });
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:http://localhost/slide");
  URL.revokeObjectURL = vi.fn();
});

describe("slide pictures", () => {
  it("shows the slide's picture, fetched with the token", async () => {
    const { calls } = setup(() => new Response(new Uint8Array([137, 80, 78, 71]), { headers: { "content-type": "image/png" } }));
    renderApp("/library/k1?slide=2");
    const img = await screen.findByRole("img", { name: "Slide 2: Agenda" });
    expect(img).toHaveAttribute("src", "blob:http://localhost/slide");
    expect(calls.find((c) => c.url.includes("/slides/2"))!.headers.get("Authorization")).toBe("Bearer t");
  });

  it("falls back to the slide's title when pictures aren't available", async () => {
    setup(() => json({ detail: "slide pictures aren't available" }, 503));
    renderApp("/library/k1?slide=2");
    expect(await screen.findByRole("heading", { name: "Agenda" })).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull();
  });
});
