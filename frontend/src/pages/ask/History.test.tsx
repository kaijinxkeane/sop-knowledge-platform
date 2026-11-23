import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp } from "@/test/utils";
import { dayGroup } from "./Conversations";

const now = new Date().toISOString();
const CONVS = [
  { id: "c1", title: "Discovery workshop timing", updated_at: now },
  { id: "c2", title: "Rate card questions", updated_at: "2026-01-02T10:00:00Z" },
];
const DOCS = [
  { id: "d1", title: "Running the Discovery Workshop", vault_path: "a.md", kind: "note", doc_type: "sop", status: "published", programme: "Signature Personal Brand Programme", stage: "discovery", owner: null, access: [], approved: true, pending_change: false, review_due: null },
];
const sse = (events: [string, unknown][]) =>
  new Response(events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join(""), {
    headers: { "Content-Type": "text/event-stream" },
  });
const CITE = { n: 1, document_id: "d1", title: "Running the Discovery Workshop", heading: "2. Opening (20 minutes)", part: null, part_number: null };

function setup(extra: Record<string, (req: Request) => Response | Promise<Response>> = {}) {
  session.signIn("t");
  let convs = [...CONVS];
  const asked: Record<string, unknown>[] = [];
  const mock = mockFetch({
    "GET /api/v1/me": () => json(makeMe()),
    "GET /api/v1/spaces": () => json([{ name: "core", title: "Core delivery", access: "internal", actions: ["ask"] }]),
    "GET /api/v1/conversations": (req) => {
      const q = new URL(req.url).searchParams.get("q")?.toLowerCase();
      return json(q ? convs.filter((c) => c.title.toLowerCase().includes(q)) : convs);
    },
    "PATCH /api/v1/conversations/c1": async (req) => {
      const { title } = await req.json();
      convs = convs.map((c) => (c.id === "c1" ? { ...c, title } : c));
      return json(convs[0]);
    },
    "POST /api/v1/conversations/c1/hide": () => {
      convs = convs.filter((c) => c.id !== "c1");
      return new Response(null, { status: 204 });
    },
    "POST /api/v1/conversations": () => json({ id: "c9", title: "", updated_at: now }, 201),
    "GET /api/v1/conversations/c9/messages": () => json([]),
    "GET /api/v1/conversations/c1/messages": () => json([]),
    "POST /api/v1/conversations/c9/messages": async (req) => {
      asked.push(await req.json());
      return sse([
        ["agent_dispatched", { space: "core", title: "Core delivery" }],
        ["token", { space: "core", text: "It lasts 3 hours [1]." }],
        ["citation", { space: "core", ...CITE }],
        ["section_done", { space: "core", no_answer: false, unavailable: false }],
        [
          "done",
          {
            message_id: `m${asked.length}`,
            question_id: `q${asked.length}`,
            answered: true,
            followups: [{ document_id: "d1", title: "Running the Discovery Workshop", heading: "Values card sort (45 minutes)" }],
          },
        ],
      ]);
    },
    "GET /api/v1/documents": () => json(DOCS),
    "GET /api/v1/documents/stages": () => json(["discovery", "delivery"]),
    "GET /api/v1/me/bookmarks": () => json([]),
    ...extra,
  });
  return { ...mock, asked };
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

describe("conversation history", () => {
  it("groups by day", () => {
    const at = new Date("2026-11-24T12:00:00");
    expect(dayGroup("2026-11-24T08:00:00", at)).toBe("today");
    expect(dayGroup("2026-11-23T23:00:00", at)).toBe("yesterday");
    expect(dayGroup("2026-11-19T09:00:00", at)).toBe("week");
    expect(dayGroup("2026-10-01T09:00:00", at)).toBe("earlier");
  });

  it("searches, renames and hides", async () => {
    const { calls } = setup();
    renderApp("/ask?conversation=c1");
    const nav = await screen.findByRole("navigation", { name: "Conversations" });
    expect(await within(nav).findByText("Rate card questions")).toBeInTheDocument();
    const u = userEvent.setup();
    await u.type(within(nav).getByLabelText("Search history"), "discov");
    await waitFor(() => expect(within(nav).queryByText("Rate card questions")).toBeNull());
    expect(calls.some((r) => new URL(r.url).searchParams.get("q") === "discov")).toBe(true);
    await u.clear(within(nav).getByLabelText("Search history"));

    await u.click(await within(nav).findByRole("button", { name: "Rename Discovery workshop timing" }));
    const name = within(nav).getByLabelText("Conversation name");
    await u.clear(name);
    await u.type(name, "Workshop{Enter}");
    expect(await within(nav).findByText("Workshop")).toBeInTheDocument();

    await u.click(within(nav).getByRole("button", { name: "Hide Workshop" }));
    expect(within(nav).getByText(/kept for audit for 24 months/)).toBeInTheDocument();
    await u.click(within(nav).getByRole("button", { name: "Hide" }));
    await waitFor(() => expect(within(nav).queryByText("Workshop")).toBeNull());
    // the hidden conversation was open: the screen goes back to a new one
    expect(await screen.findByRole("heading", { name: "What do you need to know?" })).toBeInTheDocument();
  });
});

describe("filters and follow-ups", () => {
  it("sends the filters, keeps them for the next question, and asks a follow-up", async () => {
    const { asked } = setup();
    renderApp("/ask");
    const u = userEvent.setup();
    await screen.findByRole("option", { name: "Signature Personal Brand Programme" });
    await screen.findByRole("option", { name: "discovery" });
    await u.selectOptions(screen.getByLabelText("Programme"), "Signature Personal Brand Programme");
    await u.selectOptions(screen.getByLabelText("Stage"), "discovery");
    await u.type(screen.getByLabelText("Ask about any programme, stage or SOP…"), "How long is it?{Enter}");
    const chip = await screen.findByRole("button", { name: /Values card sort \(45 minutes\)/ });
    expect(asked[0]).toEqual({ content: "How long is it?", programme: "Signature Personal Brand Programme", stage: "discovery" });
    await u.click(chip);
    await waitFor(() => expect(asked).toHaveLength(2));
    expect(asked[1]).toEqual({
      content: 'What does "Running the Discovery Workshop" say about Values card sort (45 minutes)?',
      programme: "Signature Personal Brand Programme",
      stage: "discovery",
    });
  });

  it("takes the filters from Home", async () => {
    const { asked } = setup();
    renderApp("/");
    const u = userEvent.setup();
    await screen.findByRole("option", { name: "discovery" });
    await u.selectOptions(screen.getByLabelText("Stage"), "discovery");
    await u.type(screen.getByLabelText("Ask about any programme, stage or SOP…"), "What do I prepare?{Enter}");
    await waitFor(() => expect(asked).toEqual([{ content: "What do I prepare?", stage: "discovery" }]));
    expect(screen.getByLabelText("Stage")).toHaveValue("discovery");
  });
});
