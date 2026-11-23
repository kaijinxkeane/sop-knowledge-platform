import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp, type Handler } from "@/test/utils";

const C1 = "1".repeat(40), C2 = "2".repeat(40), C3 = "3".repeat(40);
const doc = {
  id: "n1",
  title: "Leave Policy",
  vault_path: "HR/Leave Policy.md",
  kind: "note",
  doc_type: "policy",
  status: "published",
  programme: "[[Signature Personal Brand Programme]]",
  stage: null,
  owner: null,
  access: [{ space: "hr", sensitivity: "public" }],
  approved: true,
  pending_change: true,
  review_due: null,
};
const v = (commit: string, over: Record<string, unknown>) => ({
  commit,
  approved: false,
  live: false,
  latest: false,
  author_name: "Avery Tan",
  author_source: "app",
  authored_by: null,
  committed_at: "2026-11-20T10:00:00Z",
  ...over,
});
const VERSIONS = [v(C3, { latest: true }), v(C2, { approved: true, live: true }), v(C1, { approved: true })];
const LINES = Array.from({ length: 20 }, (_, i) => `Line ${i + 1}.`);
const TEXT: Record<string, string> = {
  [C1]: "# Leave\n\n" + LINES.join("\n") + "\n\nCarry over 5 days.\n",
  [C2]: "# Leave\n\n" + LINES.join("\n") + "\n\nCarry over 10 days.\n",
};

function api(extra: Record<string, Handler> = {}, me = makeMe()) {
  session.signIn("t");
  const marks: { id: string; target_type: string; target_id: string; part: number | null; title: string }[] = [];
  const mock = mockFetch({
    "GET /api/v1/me": () => json(me),
    "GET /api/v1/documents": () => json([doc]),
    "GET /api/v1/documents/n1": () => json(doc),
    "GET /api/v1/documents/n1/backlinks": () => json([]),
    "GET /api/v1/documents/n1/versions": () => json(VERSIONS),
    "GET /api/v1/documents/n1/file": () => new Response(TEXT[C2]),
    ...Object.fromEntries(
      Object.entries(TEXT).map(([c, content]) => [
        `GET /api/v1/documents/n1/versions/${c}`,
        () => json({ commit: c, author_name: "Avery Tan", committed_at: "2026-11-01T09:00:00Z", approved: true, content }),
      ]),
    ),
    "GET /api/v1/me/bookmarks": () => json(marks),
    "POST /api/v1/me/bookmarks": async (req) => {
      const b = await req.json();
      const out = { id: `b${marks.length + 1}`, ...b, part: b.part ?? null, title: doc.title, kind: "note", doc_type: "policy", created_at: "2026-11-23T00:00:00Z" };
      marks.push(out);
      return json(out, 201);
    },
    "DELETE /api/v1/me/bookmarks/b1": () => {
      marks.splice(0, 1);
      return new Response(null, { status: 204 });
    },
    ...extra,
  });
  return { ...mock, marks };
}

describe("version history", () => {
  it("marks the live and unapproved versions and opens an older one read-only", async () => {
    api();
    renderApp("/library/n1");
    const history = await screen.findByRole("heading", { name: "Version history" });
    const list = history.parentElement!;
    await within(list).findByText("approved, live");
    expect(within(list).getByText("not approved yet")).toBeInTheDocument();
    const reads = within(list).getAllByRole("link", { name: "Read" });
    await userEvent.click(reads[2]!);
    expect(await screen.findByText(/You're reading the version from/)).toBeInTheDocument();
    expect(await screen.findByText("Carry over 5 days.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to current" })).toHaveAttribute("href", "/library/n1");
  });

  it("says only 'not available' for a version the reader can't open", async () => {
    api();
    renderApp(`/library/n1?version=${C3}`);
    expect(await screen.findByText("This version isn't available.")).toBeInTheDocument();
  });

  it("compares two versions side by side, folding unchanged lines", async () => {
    api();
    renderApp(`/library/n1/compare?from=${C1}&to=${C2}`);
    expect(await screen.findByRole("status")).toHaveTextContent("1 changed, 0 added, 0 removed lines");
    const changed = document.querySelector('tr[data-kind="changed"]')!;
    expect(changed).toHaveTextContent("Carry over 5 days.");
    expect(changed).toHaveTextContent("Carry over 10 days.");
    const fold = screen.getByRole("button", { name: /Show \d+ unchanged lines/ });
    await userEvent.click(fold);
    expect(screen.getAllByText("Line 1.")).toHaveLength(2); // unchanged: both sides
  });

  it("defaults to comparing the latest version with the live one", async () => {
    api({
      [`GET /api/v1/documents/n1/versions/${C3}`]: () =>
        json({ commit: C3, author_name: "Avery Tan", committed_at: "2026-11-22T09:00:00Z", approved: false, content: TEXT[C2]!.replace("10 days", "15 days") }),
    });
    renderApp("/library/n1/compare");
    expect(await screen.findByLabelText("Older")).toHaveValue(C2);
    expect(screen.getByLabelText("Newer")).toHaveValue(C3);
    expect(await screen.findByText("Carry over 15 days.")).toBeInTheDocument();
  });
});

describe("bookmarks", () => {
  it("stars and unstars a document, and lists it on Home", async () => {
    const { marks } = api();
    renderApp("/library/n1");
    const u = userEvent.setup();
    const star = await screen.findByRole("button", { name: "Bookmark" });
    expect(star).toHaveAttribute("aria-pressed", "false");
    await u.click(star);
    await waitFor(() => expect(screen.getByRole("button", { name: "Remove bookmark" })).toHaveAttribute("aria-pressed", "true"));
    expect(marks).toEqual([expect.objectContaining({ target_type: "document", target_id: "n1", part: null })]);
    await u.click(screen.getByRole("button", { name: "Remove bookmark" }));
    await waitFor(() => expect(marks).toHaveLength(0));
  });

  it("shows bookmarks on Home", async () => {
    const { marks } = api();
    marks.push({ id: "b1", target_type: "document", target_id: "n1", part: 3, title: "Brand Foundations" });
    renderApp("/");
    const link = await screen.findByRole("link", { name: /Brand Foundations/ });
    expect(link).toHaveAttribute("href", "/library/n1?slide=3&page=3");
  });
});

describe("Ctrl+K", () => {
  const quick = {
    documents: [{ id: "n1", title: "Leave Policy", kind: "note", doc_type: "policy", programme: null, stage: null }],
    programmes: ["Signature Personal Brand Programme"],
    stages: [],
    bookmarks: [],
    conversations: [{ id: "c1", title: "How much leave carries over?" }],
  };

  it("opens from anywhere, searches titles and jumps with the keyboard", async () => {
    const { calls } = api({ "GET /api/v1/quick-search": () => json(quick) });
    renderApp("/");
    await screen.findByRole("heading", { level: 1 });
    const u = userEvent.setup();
    await u.keyboard("{Control>}k{/Control}");
    const box = await screen.findByRole("combobox", { name: "Quick search" });
    await u.type(box, "leave");
    await screen.findByRole("option", { name: /^Leave Policy/ }); // after the debounce
    const options = screen.getAllByRole("option");
    // Documents, then programmes, then conversations; no actions match "leave".
    expect(options.map((o) => o.querySelector(".truncate")!.textContent)).toEqual([
      "Leave Policy",
      "Signature Personal Brand Programme",
      "How much leave carries over?",
    ]);
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    await u.keyboard("{ArrowDown}{Enter}");
    expect(await screen.findByRole("heading", { name: "Signature Personal Brand Programme" })).toBeInTheDocument();
    const searched = calls.filter((c) => c.url.includes("/quick-search"));
    expect(new URL(searched[searched.length - 1]!.url).searchParams.get("q")).toBe("leave");
  });

  it("offers only the actions this person's menus have", async () => {
    api({}, makeMe());
    renderApp("/");
    await screen.findByRole("heading", { level: 1 });
    await userEvent.click(screen.getByRole("button", { name: /Search/ }));
    const labels = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(labels).toContain("Library");
    expect(labels).not.toContain("New SOP");
    expect(labels).not.toContain("Review queue");
  });

  it("lists New SOP for writers", async () => {
    api({}, makeMe({ space_actions: { core: ["ask", "contribute"], hr: ["ask"], it: ["ask"] } }));
    renderApp("/");
    await screen.findByRole("heading", { level: 1 });
    await userEvent.click(screen.getByRole("button", { name: /Search/ }));
    expect(await screen.findByRole("option", { name: /New SOP/ })).toBeInTheDocument();
  });
});
