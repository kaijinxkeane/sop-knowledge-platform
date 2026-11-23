import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp, type Handler } from "@/test/utils";

const V1 = "a".repeat(64);
const V2 = "b".repeat(64);
const V3 = "c".repeat(64);

// Written in a style the editor would change (`*` bullets, `__bold__`, a loose
// table) so the tests prove untouched parts are saved exactly as they were.
const NOTE = `---
doc_type: sop
title: Discovery Workshop
status: draft
owner: "[[Avery Tan]]"
stage: discovery
# kept as is
custom: yes
---

# Discovery Workshop

Lasts 3 hours, see [[Leave Policy|the leave rules]].

* Bring __cards__
* Book the room

| Step | Time |
|---|---|
| Story | 3 min |
`;

const doc = {
  id: "n1",
  title: "Discovery Workshop",
  vault_path: "Drafts/core/Discovery Workshop.md",
  kind: "note",
  doc_type: "sop",
  status: "draft",
  programme: null,
  stage: "discovery",
  owner: "[[Avery Tan]]",
  access: [{ space: "core", sensitivity: "internal" }],
  approved: false,
  pending_change: false,
  review_due: null,
};
const leave = { ...doc, id: "n2", title: "Leave Policy", vault_path: "HR/Leave Policy.md", status: "published" };
const contributor = makeMe({ space_actions: { core: ["ask", "contribute"], hr: ["ask"], it: ["ask"] } });

function writeApi(extra: Record<string, Handler> = {}, me = contributor) {
  session.signIn("t");
  const puts: { base_version: string; content: string }[] = [];
  const mock = mockFetch({
    "GET /api/v1/me": () => json(me),
    "GET /api/v1/documents": () => json([doc, leave]),
    "GET /api/v1/documents/stages": () => json(["discovery", "strategy"]),
    "GET /api/v1/documents/n1": () => json(doc),
    "GET /api/v1/documents/n1/backlinks": () => json([]),
    "GET /api/v1/documents/n1/versions": () => json([]),
    "GET /api/v1/documents/n1/file": () => new Response(NOTE),
    "GET /api/v1/notes/n1/source": () => json({ id: "n1", vault_path: doc.vault_path, version: V1, content: NOTE }),
    "PUT /api/v1/notes/n1": async (req) => {
      puts.push(await req.json());
      return json({ id: "n1", vault_path: doc.vault_path, version: V2, commit: "c1" });
    },
    ...extra,
  });
  return { ...mock, puts };
}

async function openEditor() {
  renderApp("/write/n1");
  // The editor is a lazy chunk; under a parallel test run it can take over the default 1 s.
  const body = await screen.findByLabelText("Note text", undefined, { timeout: 5000 });
  await within(body).findByText("Discovery Workshop", undefined, { timeout: 5000 });
  return body;
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:x");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => vi.useRealTimers());

describe("editor", () => {
  it("shows Obsidian syntax as chips and starts with nothing to save", async () => {
    writeApi();
    const body = await openEditor();
    expect(within(body).getByText("[[Leave Policy|the leave rules]]")).toHaveAttribute("data-kind", "wikilink");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("No changes");
  });

  it("saves a metadata change without touching anything else", async () => {
    const { puts } = writeApi();
    await openEditor();
    const u = userEvent.setup();
    await u.selectOptions(screen.getByLabelText("Stage"), "strategy");
    await u.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]!.base_version).toBe(V1);
    expect(puts[0]!.content).toBe(NOTE.replace("stage: discovery", "stage: strategy"));
    expect(await screen.findByText(/Autosaved/)).toBeInTheDocument();
  });

  it("inserts a link inline, changing only the block it went into", async () => {
    // Where the cursor is needs real layout (a browser); jsdom puts it at the start.
    const { puts } = writeApi();
    await openEditor();
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: "Link a note or file" }));
    await u.click(await screen.findByRole("button", { name: /Leave Policy/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save" })).toBeEnabled());
    await u.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(puts).toHaveLength(1));
    const blocks = (s: string) => s.split("\n\n");
    const before = blocks(NOTE), after = blocks(puts[0]!.content);
    // Same number of blocks (inline: nothing split), exactly one of them changed,
    // and it gained "[[Leave Policy]]".
    expect(after).toHaveLength(before.length);
    const changed = after.filter((blk, i) => blk !== before[i]);
    expect(changed).toHaveLength(1);
    expect(changed[0]!.replace("[[Leave Policy]]", "")).toBe(before[after.indexOf(changed[0]!)]);
  });

  it("autosaves a draft a few seconds after a change", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { puts } = writeApi();
    await openEditor();
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Discovery Workshop v2" } });
    expect(puts).toHaveLength(0);
    await act(() => vi.advanceTimersByTimeAsync(9_000));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]!.content).toContain("title: Discovery Workshop v2");
  });

  it("merges someone else's change to another block without asking", async () => {
    const theirs = NOTE.replace("* Book the room", "* Book the room a week ahead");
    const puts: { base_version: string; content: string }[] = [];
    let calls = 0;
    writeApi({
      "PUT /api/v1/notes/n1": async (req) => {
        puts.push(await req.json());
        return ++calls === 1
          ? json({ detail: { message: "changed", current_version: V3 } }, 409)
          : json({ id: "n1", vault_path: doc.vault_path, version: V2, commit: "c2" });
      },
      "GET /api/v1/notes/n1/source": () =>
        json({ id: "n1", vault_path: doc.vault_path, version: calls ? V3 : V1, content: calls ? theirs : NOTE }),
    });
    await openEditor();
    const u = userEvent.setup();
    await u.selectOptions(screen.getByLabelText("Stage"), "strategy");
    await u.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/different places/)).toBeInTheDocument();
    await u.click(within(dialog).getByRole("button", { name: "Save merged note" }));
    await waitFor(() => expect(puts).toHaveLength(2));
    expect(puts[1]!.base_version).toBe(V3);
    expect(puts[1]!.content).toBe(theirs.replace("stage: discovery", "stage: strategy"));
  });

  it("asks per block when both changed the same one", async () => {
    const theirs = NOTE.replace("stage: discovery", "stage: delivery");
    const puts: { base_version: string; content: string }[] = [];
    let calls = 0;
    writeApi({
      "PUT /api/v1/notes/n1": async (req) => {
        puts.push(await req.json());
        return ++calls === 1
          ? json({ detail: { message: "changed", current_version: V3 } }, 409)
          : json({ id: "n1", vault_path: doc.vault_path, version: V2, commit: "c2" });
      },
      "GET /api/v1/notes/n1/source": () =>
        json({ id: "n1", vault_path: doc.vault_path, version: calls ? V3 : V1, content: calls ? theirs : NOTE }),
    });
    await openEditor();
    const u = userEvent.setup();
    await u.selectOptions(screen.getByLabelText("Stage"), "strategy");
    await u.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/changed 1 of the same blocks/)).toBeInTheDocument();
    await u.click(within(dialog).getByRole("radio", { name: /Theirs/ }));
    await u.click(within(dialog).getByRole("button", { name: "Save merged note" }));
    await waitFor(() => expect(puts).toHaveLength(2));
    expect(puts[1]!.content).toBe(theirs);
  });

  it("uploads an attachment with its original design link, then reloads the note", async () => {
    // jsdom's FormData can't be encoded by Node's Request, so capture the fields as the app adds them.
    const fields = new Map<string, unknown>();
    const append = vi.spyOn(FormData.prototype, "append").mockImplementation((k: string, v: unknown) => void fields.set(k, v));
    let uploaded = false;
    const withEmbed = NOTE + "\n![[Deck.pptx]]\n*Original: Canva — https://canva.example/d/1*\n";
    writeApi({
      "POST /api/v1/notes/n1/attachments": async () => {
        uploaded = true;
        return json({ id: "a1", vault_path: "Drafts/core/attachments/Deck.pptx", version: V2, commit: "c3" }, 201);
      },
      "GET /api/v1/notes/n1/source": () =>
        json({ id: "n1", vault_path: doc.vault_path, version: uploaded ? V2 : V1, content: uploaded ? withEmbed : NOTE }),
    });
    const body = await openEditor();
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: "Upload attachment" }));
    const dialog = await screen.findByRole("dialog");
    await u.upload(within(dialog).getByLabelText("File"), new File(["x"], "Deck.pptx"));
    await u.type(within(dialog).getByLabelText("Made in (optional)"), "Canva");
    await u.type(within(dialog).getByLabelText("Link to the original design (optional)"), "https://canva.example/d/1");
    await u.click(within(dialog).getByRole("button", { name: "Upload" }));
    expect(await within(body).findByText("![[Deck.pptx]]")).toBeInTheDocument();
    expect((fields.get("file") as File).name).toBe("Deck.pptx");
    expect(fields.get("source_tool")).toBe("Canva");
    expect(fields.get("original_link")).toBe("https://canva.example/d/1");
    append.mockRestore();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("shows the server's refusal when a save widens access", async () => {
    writeApi({
      "PUT /api/v1/notes/n1": () => json({ detail: "making a note more open needs approval from the space lead" }, 403),
    });
    await openEditor();
    const u = userEvent.setup();
    await u.selectOptions(screen.getByLabelText("Who can read it"), "public");
    expect(screen.getByText(/the space lead must approve this/)).toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Making a note more open needs approval from the space lead.")).toBeInTheDocument();
  });

  it("answers a note the person can't see like a missing page", async () => {
    writeApi({ "GET /api/v1/notes/n1/source": () => json({ detail: "not found" }, 404) });
    renderApp("/write/n1");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});

describe("new note", () => {
  it("creates a draft from the SOP template, pre-filled from a gap", async () => {
    let created: Record<string, unknown> | null = null;
    writeApi({
      "POST /api/v1/notes": async (req) => {
        created = await req.json();
        return json({ id: "n1", vault_path: doc.vault_path, version: V1, commit: "c0" }, 201);
      },
    });
    renderApp("/write/new?programme=Signature&stage=strategy&related=Brand%20Pillars%20Workshop%20SOP");
    const u = userEvent.setup();
    await u.type(await screen.findByLabelText("Title"), "Pillars follow-up");
    await u.click(screen.getByRole("button", { name: "Create draft" }));
    await screen.findByLabelText("Note text", undefined, { timeout: 5000 });
    expect(created).toMatchObject({
      title: "Pillars follow-up",
      space: "core",
      sensitivity: "internal",
      doc_type: "sop",
      programme: "[[Signature]]",
      stage: "strategy",
    });
    expect(created!.body).toBe(
      "# Pillars follow-up\n\n## Purpose\n\n\n## When to use it\n\n\n## Steps\n\n\n## Done when\n\n\n## Related\n\n- [[Brand Pillars Workshop SOP]]\n",
    );
  });

  it("is hidden from people who can't write", async () => {
    writeApi({}, makeMe());
    renderApp("/write/new");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});

describe("reader", () => {
  it("offers Edit only to people who can contribute in the note's space", async () => {
    writeApi();
    renderApp("/library/n1");
    expect(await screen.findByRole("link", { name: "Edit" })).toHaveAttribute("href", "/write/n1");
  });

  it("has no Edit for readers", async () => {
    writeApi({}, makeMe());
    renderApp("/library/n1");
    await screen.findByRole("heading", { level: 1, name: "Discovery Workshop" });
    expect(screen.queryByRole("link", { name: "Edit" })).toBeNull();
  });
});
