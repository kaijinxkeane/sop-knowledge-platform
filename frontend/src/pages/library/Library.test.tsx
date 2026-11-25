import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { session } from "@/auth/session";
import { forgetPlaces, placeFor, recordPlace } from "@/lib/places";
import { json, makeMe, mockFetch, renderApp, type Handler } from "@/test/utils";

const doc = (over: Record<string, unknown>) => ({
  id: "d0",
  title: "Untitled",
  vault_path: "x.md",
  kind: "note",
  doc_type: "sop",
  status: "published",
  programme: null,
  stage: null,
  owner: null,
  access: [{ space: "core", sensitivity: "internal" }],
  approved: true,
  pending_change: false,
  review_due: null,
  ...over,
});

const SIG = "[[Signature Personal Brand Programme]]";
const DOCS = [
  doc({ id: "d1", title: "Discovery Workshop SOP", vault_path: "Programmes/Discovery Workshop SOP.md", programme: SIG, stage: "discovery", owner: "[[Avery Tan]]" }),
  doc({ id: "d2", title: "Brand Foundations", vault_path: "Training Content/Attachments/Brand Foundations.pptx", kind: "attachment", doc_type: "deck", programme: SIG, stage: "discovery" }),
  doc({ id: "d3", title: "Values Card Sort Worksheet", vault_path: "Training Content/Attachments/Values Card Sort Worksheet.pdf", kind: "attachment", doc_type: "pdf", programme: SIG, stage: "strategy" }),
  doc({ id: "d4", title: "Leave Policy", vault_path: "HR/Leave Policy.md", doc_type: "policy", access: [{ space: "hr", sensitivity: "public" }], pending_change: true, approved: true }),
];

const NOTE = `---
title: Discovery Workshop SOP
---
# Discovery Workshop

Read [[Leave Policy|the leave rules]] and the [[Rate Card 2026]] first.
Part of [[Signature Personal Brand Programme]].

![[Brand Foundations.pptx]]

[click me](javascript:alert(1)) <b>raw html</b>

| Step | Time |
| --- | --- |
| Story | 3 min |
`;

const SLIDES = [
  { part: "slide", number: 1, title: "Welcome", speaker_notes: "Introduce yourself." },
  { part: "slide", number: 2, title: "What a brand is", speaker_notes: "Use one personal story." },
  { part: "slide", number: 3, title: "Brand gaps", speaker_notes: "" },
];

function libraryApi(extra: Record<string, Handler> = {}) {
  session.signIn("t");
  return mockFetch({
    "GET /api/v1/me": () => json(makeMe()),
    "GET /api/v1/documents": () => json(DOCS),
    "GET /api/v1/documents/stages": () => json(["discovery", "strategy", "content", "delivery", "follow-up"]),
    ...Object.fromEntries(
      DOCS.flatMap((d) => [
        [`GET /api/v1/documents/${d.id}`, () => json(d)],
        [`GET /api/v1/documents/${d.id}/backlinks`, () => json([])],
        [`GET /api/v1/documents/${d.id}/versions`, () =>
          json([{ commit: "abc", author_name: "Avery Tan", author_source: "app", authored_by: null, committed_at: "2026-11-20T10:00:00Z" }])],
      ]),
    ),
    "GET /api/v1/documents/d1/file": () => new Response(NOTE),
    "GET /api/v1/documents/d2/parts": () => json(SLIDES),
    "GET /api/v1/documents/d3/file": () => new Response(new Uint8Array([37, 80, 68, 70])),
    ...extra,
  });
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:http://localhost/fake");
  URL.revokeObjectURL = vi.fn();
});

describe("library: browse", () => {
  it("shows a programme's stages, flags stages with no SOPs, and lists documents by stage", async () => {
    libraryApi();
    renderApp("/library");
    expect(await screen.findByRole("heading", { name: "Signature Personal Brand Programme" })).toBeInTheDocument();
    expect(screen.getByText("1 SOPs")).toBeInTheDocument(); // discovery
    expect(screen.getAllByText(/No SOPs yet/)).toHaveLength(4); // strategy .. follow-up
    expect(screen.getByRole("link", { name: "Discovery Workshop SOP" })).toHaveAttribute("href", "/library/d1");
    expect(screen.getByRole("link", { name: "Values Card Sort Worksheet" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Leave Policy" })).not.toBeInTheDocument();
  });

  it("switches to the department view", async () => {
    libraryApi();
    renderApp("/library");
    const u = userEvent.setup();
    await u.selectOptions(await screen.findByLabelText("View"), "department");
    await u.click(screen.getByRole("button", { name: "HR" }));
    expect(await screen.findByRole("link", { name: "Leave Policy" })).toBeInTheDocument();
    // An editor sees that changes are waiting.
    expect(screen.getByText("Changes waiting for review")).toBeInTheDocument();
  });
});

describe("library: arranging a programme", () => {
  it("lets contributors put a stage in their own order, saved for everyone", async () => {
    let saved: unknown = null;
    let order: { document_id: string; position: number }[] = [];
    libraryApi({
      "GET /api/v1/me": () => json(makeMe({ space_actions: { core: ["ask", "contribute"], hr: ["ask"] } })),
      "GET /api/v1/documents": () => json(DOCS.map((d) => ({ ...d, space: d.access[0]!.space }))),
      "GET /api/v1/library/order": () => json(order),
      "PUT /api/v1/library/order": async (req) => {
        saved = await req.json();
        order = [{ document_id: "d2", position: 10 }, { document_id: "d1", position: 20 }];
        return new Response(null, { status: 204 });
      },
    });
    renderApp(`/library?group=${encodeURIComponent("Signature Personal Brand Programme")}`);
    const u = userEvent.setup();
    await u.click(await screen.findByRole("button", { name: "Arrange" }));
    await u.click(screen.getByRole("button", { name: "Move Brand Foundations up" }));
    await u.click(screen.getByRole("button", { name: "Save order" }));
    await waitFor(() => expect(saved).toEqual({ programme: SIG, stage: "discovery", document_ids: ["d2", "d1"] }));
    const links = await screen.findAllByRole("link", { name: /Brand Foundations|Discovery Workshop SOP/ });
    expect(links.map((l) => l.textContent)).toEqual(["Brand Foundations", "Discovery Workshop SOP"]);
  });

  it("offers no Arrange to readers", async () => {
    libraryApi({ "GET /api/v1/library/order": () => json([]) });
    renderApp(`/library?group=${encodeURIComponent("Signature Personal Brand Programme")}`);
    await screen.findByRole("link", { name: "Discovery Workshop SOP" });
    expect(screen.queryByRole("button", { name: "Arrange" })).toBeNull();
  });
});

describe("library: help", () => {
  it("puts the user guide in its own Help group, reached from the header", async () => {
    const guide = doc({ id: "g1", title: "Asking Questions", vault_path: "Help/Asking Questions.md", doc_type: "guide", access: [{ space: "core", sensitivity: "public" }] });
    libraryApi({ "GET /api/v1/documents": () => json([...DOCS, guide]) });
    renderApp("/library");
    const u = userEvent.setup();
    await screen.findByRole("button", { name: "Help: using the SOP Assistant" });
    const groups = screen.getByRole("navigation", { name: "Programmes, stages or departments" });
    expect(within(groups).getAllByRole("button").at(-1)).toHaveTextContent("Help: using the SOP Assistant");
    await u.click(within(groups).getByRole("button", { name: "Other documents" }));
    expect(await screen.findByRole("link", { name: "Leave Policy" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Asking Questions" })).not.toBeInTheDocument();
    await u.click(screen.getByRole("link", { name: "Help" }));
    expect(await screen.findByRole("heading", { name: "Help: using the SOP Assistant" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Asking Questions" })).toHaveAttribute("href", "/library/g1");
  });
});

describe("library: remembers where you were", () => {
  beforeEach(() => forgetPlaces());

  it("brings you back to the search results after opening a document", async () => {
    libraryApi({
      "GET /api/v1/search": () =>
        json({ search_id: "s1", semantic: true, results: [{ document_id: "d1", title: "Discovery Workshop SOP", vault_path: "a.md", doc_type: "sop", kind: "note", programme: null, stage: null, heading: null, part: null, part_number: null, snippet: "the workshop", score: 1, matched: [] }] }),
      "POST /api/v1/search/s1/outcome": () => new Response(null, { status: 204 }),
    });
    const { router } = renderApp("/library");
    const u = userEvent.setup();
    await u.type(await screen.findByLabelText("Search the library"), "workshop");
    await u.click(screen.getByRole("button", { name: "Search" }));
    await u.click(await screen.findByRole("link", { name: "Discovery Workshop SOP" }));
    await u.click(await screen.findByRole("link", { name: "Library" , current: false }));
    await waitFor(() => expect(router.state.location.search).toBe("?q=workshop"));
    expect(await screen.findByRole("link", { name: "Discovery Workshop SOP" })).toBeInTheDocument();
  });

  it("keeps the view and folder for the back link and the menu", async () => {
    libraryApi();
    const { router } = renderApp("/library?view=department&group=hr");
    const u = userEvent.setup();
    await u.click(await screen.findByRole("link", { name: "Leave Policy" }));
    await screen.findByRole("heading", { name: "Leave Policy" });
    const back = screen.getAllByRole("link", { name: "Library" }).find((l) => l.closest("main"))!;
    expect(back).toHaveAttribute("href", "/library?view=department&group=hr");
    const menu = within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", { name: "Library" });
    expect(menu).toHaveAttribute("href", "/library?view=department&group=hr");
    await u.click(back);
    expect(router.state.location.search).toBe("?view=department&group=hr");
    expect(await screen.findByRole("link", { name: "Leave Policy" })).toBeInTheDocument();
  });

  it("returns a document opened from Ask to the conversation", async () => {
    recordPlace("/ask", "?conversation=c1");
    libraryApi();
    renderApp("/library/d1");
    const back = await screen.findByRole("link", { name: "Ask" , current: false });
    expect(back.getAttribute("href")).toBe("/ask?conversation=c1");
  });

  it("forgets everything on sign-out", () => {
    recordPlace("/library", "?q=secret");
    session.signOut();
    expect(placeFor("library", "/library")).toBe("/library");
  });
});

describe("library: search", () => {
  const results = {
    search_id: "s1",
    semantic: true,
    results: [
      { document_id: "d2", title: "Brand Foundations", vault_path: "x.pptx", doc_type: "deck", kind: "attachment", programme: null, stage: null, heading: null, part: "slide", part_number: 2, snippet: "what a personal brand is", score: 1, matched: [] },
    ],
  };

  it("links a slide hit straight to the slide and reports only counts", async () => {
    const { calls } = libraryApi({
      "GET /api/v1/search": () => json(results),
      "POST /api/v1/search/s1/outcome": () => new Response(null, { status: 204 }),
    });
    renderApp("/library");
    const u = userEvent.setup();
    await u.type(await screen.findByLabelText("Search the library"), "personal brand");
    await u.click(screen.getByRole("button", { name: "Search" }));
    const hit = await screen.findByRole("link", { name: "Brand Foundations" });
    expect(hit).toHaveAttribute("href", "/library/d2?slide=2");
    expect(screen.getByText("slide 2")).toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: "Yes" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/outcome"))).toBe(true));
    const outcome = calls.find((c) => c.url.endsWith("/outcome"))!;
    expect(await outcome.clone().json()).toEqual({ opened: 0, used: true });
    const search = calls.find((c) => c.url.includes("/search?"))!;
    expect(new URL(search.url).searchParams.get("q")).toBe("personal brand");
  });

  it("says when nothing matches", async () => {
    libraryApi({ "GET /api/v1/search": () => json({ search_id: "s2", semantic: false, results: [] }) });
    renderApp("/library?q=zzz");
    expect(await screen.findByText("Nothing you can access matches this.")).toBeInTheDocument();
    expect(screen.getByText(/keyword matches only/)).toBeInTheDocument();
  });
});

describe("reader", () => {
  it("renders a note with Obsidian links resolved against what the reader can see", async () => {
    libraryApi();
    renderApp("/library/d1");
    expect(await screen.findByRole("heading", { level: 1, name: "Discovery Workshop SOP" })).toBeInTheDocument();
    const article = await screen.findByRole("article");
    await within(article).findByText("Discovery Workshop");
    expect(within(article).getByRole("link", { name: "the leave rules" })).toHaveAttribute("href", "/library/d4");
    // A link to a note the reader can't see shows no title and no hint it exists.
    expect(within(article).queryByText(/Rate Card/)).not.toBeInTheDocument();
    expect(within(article).getByText("(note not available)")).toBeInTheDocument();
    // A programme name opens that programme in the Library.
    expect(within(article).getByRole("link", { name: "Signature Personal Brand Programme" })).toHaveAttribute(
      "href",
      "/library?view=programme&group=Signature%20Personal%20Brand%20Programme",
    );
    // The embedded deck becomes a card that opens it.
    expect(within(article).getByRole("link", { name: /Brand Foundations/ })).toHaveAttribute("href", "/library/d2");
    // No script links, no raw HTML; tables render.
    expect(within(article).queryByRole("link", { name: "click me" })).toBeNull();
    expect(article.querySelector("b")).toBeNull();
    expect(within(article).getByRole("table")).toBeInTheDocument();
    // Metadata: plain names, not [[links]].
    expect(screen.getByText("Signature Personal Brand Programme", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("Avery Tan", { selector: "dd" })).toBeInTheDocument();
  });

  it("opens a deck at the cited slide and steps through it", async () => {
    libraryApi();
    renderApp("/library/d2?slide=2");
    expect(await screen.findByRole("heading", { name: "What a brand is" })).toBeInTheDocument();
    expect(screen.getByText("Use one personal story.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next slide" }));
    expect(await screen.findByRole("heading", { name: "Brand gaps" })).toBeInTheDocument();
    expect(screen.getByText("No speaker notes on this slide.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next slide" })).toBeDisabled();
  });

  it("shows a PDF in the browser viewer from a blob, at the cited page", async () => {
    libraryApi();
    renderApp("/library/d3?page=2");
    const frame = await screen.findByTitle("PDF: Values Card Sort Worksheet");
    expect(frame).toHaveAttribute("src", "blob:http://localhost/fake#page=2");
    const blob = (URL.createObjectURL as ReturnType<typeof vi.fn>).mock.calls[0]![0] as Blob;
    expect(blob.type).toBe("application/pdf");
  });

  it("answers a hidden document exactly like a missing one", async () => {
    libraryApi({ "GET /api/v1/documents/hidden": () => json({ detail: "not found" }, 404) });
    renderApp("/library/hidden");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
