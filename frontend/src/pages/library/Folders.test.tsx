import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { forgetPlaces } from "@/lib/places";
import { json, makeMe, mockFetch, renderApp, type Handler } from "@/test/utils";

const doc = (id: string, title: string, vault_path: string, space: string) => ({
  id, title, vault_path, space, kind: "note", doc_type: "sop", status: "published", programme: null, stage: null,
  owner: null, access: [{ space, sensitivity: "internal" }], approved: true, pending_change: false, review_due: null,
});
const DOCS = [
  doc("d1", "Discovery Workshop SOP", "Programmes/Discovery/Discovery Workshop SOP.md", "core"),
  doc("d2", "Brand Pillars", "Programmes/Strategy/Brand Pillars.md", "core"),
  doc("d3", "Leave Policy", "HR/Leave Policy.md", "hr"),
];
const FOLDERS = [
  { id: null, space: "core", path: "Programmes", can_edit: true },
  { id: "f1", space: "core", path: "Programmes/Onboarding", can_edit: true },
];

function setup(extra: Record<string, Handler> = {}, me = makeMe({ space_actions: { core: ["ask", "contribute"], hr: ["ask"] } })) {
  session.signIn("t");
  return mockFetch({
    "GET /api/v1/me": () => json(me),
    "GET /api/v1/documents": () => json(DOCS),
    "GET /api/v1/documents/stages": () => json([]),
    "GET /api/v1/library/folders": () => json(FOLDERS),
    ...extra,
  });
}

beforeEach(() => forgetPlaces());

describe("library folders", () => {
  it("keeps departments apart and browses folders like an explorer", async () => {
    setup();
    const { router } = renderApp("/library?view=folders&group=core");
    const u = userEvent.setup();
    await screen.findByRole("button", { name: "hr" });
    const groups = screen.getByRole("navigation", { name: "Programmes, stages or departments" });
    expect(within(groups).getAllByRole("button").map((b) => b.textContent)).toEqual(["core", "hr"]);
    await u.click(await screen.findByRole("button", { name: /Programmes/ }));
    expect(router.state.location.search).toContain("folder=Programmes");
    expect(screen.getByRole("button", { name: /Onboarding/ })).toHaveTextContent("0 documents");
    expect(screen.getByRole("button", { name: /Discovery/ })).toHaveTextContent("1 documents");
    expect(screen.queryByText("Leave Policy")).not.toBeInTheDocument(); // HR never mixes in
    await u.click(screen.getByRole("button", { name: /Discovery/ }));
    expect(await screen.findByRole("link", { name: "Discovery Workshop SOP" })).toBeInTheDocument();
  });

  it("searches only inside the open folder, and offers Ask about it", async () => {
    let searched: URLSearchParams | null = null;
    setup({
      "GET /api/v1/search": (req) => ((searched = new URL(req.url).searchParams), json({ search_id: null, semantic: true, results: [] })),
    });
    renderApp("/library?view=folders&group=core&folder=Programmes%2FDiscovery");
    const u = userEvent.setup();
    expect(await screen.findByRole("link", { name: "Ask about this folder" })).toHaveAttribute(
      "href",
      "/ask?folder=Programmes%2FDiscovery",
    );
    expect(screen.getByLabelText("Only search in Discovery")).toBeChecked();
    await u.type(screen.getByLabelText("Search the library"), "intake{Enter}");
    expect(await screen.findByText("Results for “intake” in Programmes/Discovery")).toBeInTheDocument();
    expect(searched!.get("folder")).toBe("Programmes/Discovery");
  });

  it("makes a folder and moves a document within the department", async () => {
    let made: unknown = null;
    let moved: unknown = null;
    setup({
      "POST /api/v1/library/folders": async (req) => (
        (made = await req.json()), json({ id: "f2", space: "core", path: "Programmes/Discovery/Archive", can_edit: true }, 201)
      ),
      "POST /api/v1/library/documents/d1/move": async (req) => (
        (moved = await req.json()), json({ id: "d1", vault_path: "Programmes/Onboarding/Discovery Workshop SOP.md" })
      ),
    });
    renderApp("/library?view=folders&group=core&folder=Programmes%2FDiscovery");
    const u = userEvent.setup();
    await u.click(await screen.findByRole("button", { name: "New folder" }));
    await u.type(screen.getByLabelText("Folder name"), "Archive");
    await u.click(screen.getByRole("button", { name: "Create" }));
    expect(made).toEqual({ space: "core", parent: "Programmes/Discovery", name: "Archive" });

    renderApp("/library?view=folders&group=core&folder=Programmes%2FDiscovery");
    const row = (await screen.findAllByRole("link", { name: "Discovery Workshop SOP" })).at(-1)!.closest("li")!;
    await u.click(within(row).getByRole("button", { name: "Move" }));
    const form = within(row).getByRole("form", { name: "Move Discovery Workshop SOP" });
    const options = within(form).getAllByRole("option").map((o) => o.textContent);
    expect(options).not.toContain("HR");
    await u.selectOptions(within(form).getByLabelText("Move to folder"), "Programmes/Onboarding");
    await u.click(within(form).getByRole("button", { name: "Move here" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Moved Discovery Workshop SOP to Programmes/Onboarding.");
    expect(moved).toEqual({ folder: "Programmes/Onboarding" });
  });

  it("shows readers the folders but no folder or move buttons", async () => {
    setup({}, makeMe({ space_actions: { core: ["ask"], hr: ["ask"] } }));
    renderApp("/library?view=folders&group=core&folder=Programmes%2FDiscovery");
    expect(await screen.findByRole("link", { name: "Discovery Workshop SOP" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New folder" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Move" })).not.toBeInTheDocument();
  });
});
