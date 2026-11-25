import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp, type Handler } from "@/test/utils";

const path = (over: Record<string, unknown> = {}) => ({
  id: "p1",
  space: "core",
  title: "New trainer",
  description: "Your first two weeks.",
  total: 3,
  done: 1,
  due_on: null,
  next_item: "i2",
  assignments: [],
  can_edit: false,
  steps: [
    {
      title: "Week 1",
      items: [
        { id: "i1", required: true, readable: true, document_id: "d1", title: "Discovery Workshop", kind: "note", doc_type: "sop", done: true },
        { id: "i2", required: false, readable: true, document_id: "d2", title: "Intake Deck", kind: "attachment", doc_type: "deck", done: false },
      ],
    },
    { title: "Week 2", items: [{ id: "i3", required: true, readable: false, document_id: null, title: null, kind: null, doc_type: null, done: false }] },
  ],
  ...over,
});

function setup(extra: Record<string, Handler> = {}, me = makeMe()) {
  session.signIn("t");
  return mockFetch({
    "GET /api/v1/me": () => json(me),
    "GET /api/v1/notifications": () => json([]),
    "GET /api/v1/documents": () =>
      json([
        { id: "d1", title: "Discovery Workshop", kind: "note", approved: true, doc_type: "sop", vault_path: "a.md", access: [] },
        { id: "d2", title: "Intake Deck", kind: "attachment", approved: true, doc_type: "deck", vault_path: "b.pptx", access: [] },
      ]),
    ...extra,
  });
}

beforeEach(() => session.signOut());

describe("onboarding paths", () => {
  it("shows a learner the next item, Done for optional items and sign-off for required ones", async () => {
    let doneCalled = false;
    setup({
      "GET /api/v1/me/paths/p1": () => json(path()),
      "POST /api/v1/path-items/i2/done": () => ((doneCalled = true), new Response(null, { status: 204 })),
    });
    renderApp("/paths/p1");
    expect(await screen.findByRole("heading", { name: "New trainer" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "1 of 3 done" })).toBeInTheDocument();
    const row = screen.getByRole("link", { name: "Intake Deck" }).closest("li")!;
    expect(within(row).getByText("Next up")).toBeInTheDocument();
    // The hidden item: no title, no link.
    expect(screen.getByText("An item you can't open yet")).toBeInTheDocument();
    expect(screen.getAllByRole("link").map((a) => a.getAttribute("href"))).not.toContain("/library/null");
    await userEvent.click(within(row).getByRole("button", { name: "Done" }));
    expect(doneCalled).toBe(true);
    expect(within(row).getByRole("link", { name: "Ask about this" }).getAttribute("href")).toContain("/ask?q=");
  });

  it("puts unfinished paths on Home", async () => {
    setup({
      "GET /api/v1/me/paths": () => json([path()]),
      "GET /api/v1/me/gaps": () => json([]),
      "GET /api/v1/me/recent": () => json([]),
      "GET /api/v1/me/waiting": () => json({ reviews: 0, drafts: 0, labels: 0 }),
      "GET /api/v1/me/bookmarks": () => json([]),
      "GET /api/v1/me/required-reading": () => json([]),
      "GET /api/v1/documents/stages": () => json([]),
      "GET /api/v1/handovers": () => json([]),
    });
    renderApp("/");
    const card = await screen.findByRole("region", { name: "Onboarding" });
    expect(within(card).getByRole("link", { name: "New trainer" })).toHaveAttribute("href", "/paths/p1");
    expect(within(card).getByRole("link", { name: "Intake Deck" })).toHaveAttribute("href", "/library/d2");
  });

  it("lets a lead build a path from library items", async () => {
    let body: unknown = null;
    setup(
      {
        "GET /api/v1/me/paths": () => json([]),
        "GET /api/v1/paths": () => json([]),
        "GET /api/v1/reports/path-completion": () => json([]),
        "POST /api/v1/paths": async (req) => ((body = await req.json()), json(path({ can_edit: true }), 201)),
        "GET /api/v1/paths/p1": () => json(path({ can_edit: true })),
        "GET /api/v1/reading-assignments/roles": () => json([]),
      },
      makeMe({ space_actions: { core: ["ask", "approve"] } }),
    );
    renderApp("/paths/new");
    await userEvent.type(await screen.findByLabelText("Path name"), "New trainer");
    await userEvent.type(screen.getByLabelText("Add an SOP, deck or worksheet…"), "disc");
    await userEvent.click(await screen.findByRole("button", { name: /Discovery Workshop/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Required" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("form", { name: "Assign this path" })).toBeInTheDocument();
    expect(body).toEqual({
      space: "core",
      title: "New trainer",
      description: "",
      steps: [{ title: "Week 1", items: [{ document_id: "d1", required: true }] }],
    });
  });

  it("is a 404 for a path that isn't mine", async () => {
    setup();
    renderApp("/paths/nope");
    expect(await screen.findByText(/couldn't find|not found/i)).toBeInTheDocument();
  });
});
