import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp, type Handler } from "@/test/utils";
import { markCitations } from "./AnswerText";
import { parseSse } from "./api";

type Ev = [string, Record<string, unknown>];
const sse = (events: Ev[]) =>
  new Response(events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join(""), {
    headers: { "Content-Type": "text/event-stream" },
  });

const CITE = {
  n: 1,
  document_id: "d1",
  title: "Running the Discovery Workshop",
  vault_path: "Programmes/Discovery Workshop SOP.md",
  heading: "Running the Discovery Workshop › Before the session",
  part: null,
  part_number: null,
  version: "abcdef1234",
  written_by: "Avery Tan",
  approved_by: "Jordan Lee",
  approval: "approved",
  approved_on: "2026-11-02",
};
const SLIDE = { ...CITE, n: 2, document_id: "d2", title: "Brand Foundations", heading: "Slide 2: What a brand is", part: "slide", part_number: 2 };
const NOTE = "# Running the Discovery Workshop\n\n## Before the session\n\nConfirm the intake questionnaire.\n";

const answer = (space: string, text: string, cites: Record<string, unknown>[] = [CITE]): Ev[] => [
  ["agent_dispatched", { space, title: space === "core" ? "Core delivery" : "HR" }],
  ...text.split(" ").map((w, i): Ev => ["token", { space, text: (i ? " " : "") + w }]),
  ...cites.map((c): Ev => ["citation", { space, ...c }]),
  ["section_done", { space, no_answer: false, unavailable: false, confidence: "high", contact: null }],
];

function askApi(stream: Handler, stored: unknown[] = [], extra: Record<string, Handler> = {}, me = makeMe()) {
  session.signIn("t");
  let asked = false;
  const posts: Record<string, unknown>[] = [];
  const mock = mockFetch({
    "GET /api/v1/me": () => json(me),
    "GET /api/v1/spaces": () =>
      json([
        { name: "core", title: "Core delivery", access: "internal", actions: ["ask"] },
        { name: "hr", title: "HR", access: "public", actions: ["ask"] },
      ]),
    "GET /api/v1/conversations": () => json(asked ? [{ id: "c1", title: "How do we open?", updated_at: new Date().toISOString() }] : []),
    "POST /api/v1/conversations": () => json({ id: "c1", title: "", updated_at: new Date().toISOString() }, 201),
    "GET /api/v1/conversations/c1/messages": () => json(asked ? stored : []),
    "POST /api/v1/conversations/c1/messages": async (req) => {
      posts.push(await req.json());
      asked = true;
      return stream(req);
    },
    "GET /api/v1/me/bookmarks": () => json([]),
    "GET /api/v1/documents": () => json([]),
    "GET /api/v1/documents/d1": () => json({ id: "d1", title: CITE.title, vault_path: CITE.vault_path, kind: "note", doc_type: "sop", status: "published", programme: null, stage: null, owner: null, access: [], approved: true, pending_change: false, review_due: null }),
    "GET /api/v1/documents/d1/file": () => new Response(NOTE),
    "GET /api/v1/documents/d2": () => json({ id: "d2", title: "Brand Foundations", vault_path: "x.pptx", kind: "attachment", doc_type: "deck", status: "published", programme: null, stage: null, owner: null, access: [], approved: true, pending_change: false, review_due: null }),
    "GET /api/v1/documents/d2/parts": () =>
      json([
        { part: "slide", number: 1, title: "Welcome", speaker_notes: "Hello." },
        { part: "slide", number: 2, title: "What a brand is", speaker_notes: "Use one personal story." },
        { part: "slide", number: 3, title: "Brand gaps", speaker_notes: "" },
      ]),
    ...extra,
  });
  return { ...mock, posts };
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:x");
  URL.revokeObjectURL = vi.fn();
  Element.prototype.scrollIntoView = vi.fn();
});

describe("SSE parsing", () => {
  it("splits events, keeps a partial one for later and skips broken data", () => {
    const { events, rest } = parseSse('event: token\ndata: {"space":"core","text":"Hi"}\n\nevent: bad\ndata: {oops\n\nevent: done\ndata: {"mess');
    expect(events).toEqual([{ event: "token", data: { space: "core", text: "Hi" } }]);
    expect(rest).toBe('event: done\ndata: {"mess');
  });

  it("marks citations but not inside code", () => {
    expect(markCitations("Do this [1] and `a[2]`.")).toBe("Do this [1](sop-cite:1) and `a[2]`.");
  });
});

describe("Ask", () => {
  const stored = [
    { id: "q1", role: "user", content: "How do we open a discovery workshop?", sections: [], created_at: "2026-11-23T10:00:00Z" },
    {
      id: "m1",
      role: "assistant",
      content: "Start with the brand story [1].",
      sections: [{ space: "core", text: "Start with the brand story [1].", citations: [CITE], no_answer: false }],
      created_at: "2026-11-23T10:00:05Z",
    },
  ];

  it("asks from Home, streams the answer and opens the cited section", async () => {
    const { posts } = askApi(
      () => sse([["routing", { spaces: ["core"], reason: "search" }], ...answer("core", "Start with the brand story [1]."), ["done", { message_id: "m1", question_id: "q1", answered: true }]]),
      stored,
    );
    renderApp("/");
    const u = userEvent.setup();
    await u.type(await screen.findByLabelText("Ask about any programme, stage or SOP…"), "How do we open a discovery workshop?{Enter}");
    const cite = await screen.findByRole("button", { name: /Source 1: Running the Discovery Workshop/ });
    expect(posts).toEqual([{ content: "How do we open a discovery workshop?" }]);
    expect(screen.getAllByText("How do we open a discovery workshop?")).toHaveLength(1);
    await u.click(cite);
    const panel = await screen.findByRole("complementary", { name: "Source" });
    expect(within(panel).getByText("by Avery Tan")).toBeInTheDocument();
    expect(within(panel).getByText("approved by Jordan Lee 2026-11-02")).toBeInTheDocument();
    const heading = await within(panel).findByRole("heading", { name: "Before the session" });
    await waitFor(() => expect(heading).toHaveClass("sop-cited"));
    expect(within(panel).getByRole("link", { name: "Open in Library" })).toHaveAttribute("href", "/library/d1");
  });

  it("shows each department's answer in its own section", async () => {
    askApi(() =>
      sse([
        ...answer("core", "Core says [1]."),
        ...answer("hr", "HR says [1]."),
        ["done", { message_id: "m9", question_id: "q9", answered: true }],
      ]),
    );
    renderApp("/ask?q=leave%20for%20trainers");
    expect(await screen.findByRole("region", { name: "Core delivery" })).toHaveTextContent("Core says");
    expect(screen.getByRole("region", { name: "HR" })).toHaveTextContent("HR says");
  });

  it("never renders links that come back in an answer", async () => {
    askApi(() => sse([...answer("core", "See [click here](https://evil.example) [1]."), ["done", { message_id: "m2", question_id: "q2", answered: true }]]));
    renderApp("/ask?q=anything%20here");
    await screen.findByRole("button", { name: /Source 1/ });
    expect(screen.queryByRole("link", { name: "click here" })).toBeNull();
    expect(screen.getByText("click here")).toBeInTheDocument();
  });

  it("opens a cited slide with its speaker notes and neighbours", async () => {
    askApi(() => sse([...answer("core", "Tell a story [2].", [SLIDE]), ["done", { message_id: "m3", question_id: "q3", answered: true }]]));
    renderApp("/ask?q=brand%20story");
    await userEvent.click(await screen.findByRole("button", { name: /Source 2/ }));
    const panel = await screen.findByRole("complementary", { name: "Source" });
    expect(await within(panel).findByText("Use one personal story.")).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Next slide" }));
    expect(within(panel).getByRole("heading", { name: "Brand gaps" })).toBeInTheDocument();
  });

  it("says plainly when no SOP covers it, and offers three ways on", async () => {
    let requested: unknown = null;
    askApi(
      () =>
        sse([
          ["agent_dispatched", { space: "core", title: "Core delivery" }],
          ["section_done", { space: "core", no_answer: true, unavailable: false, contact: "Ask the delivery team." }],
          ["done", { message_id: "m4", question_id: "q4", answered: false }],
        ]),
      [],
      {
        "POST /api/v1/me/gaps/request": async (req) => {
          requested = await req.json();
          return json({ requested: true }, 202);
        },
        "GET /api/v1/me/gaps": () => json([{ key: "s1,q4", label: "x", count: 1, last_at: "2026-11-23T00:00:00Z", message: "", related: [], experts: ["Avery Tan"], space: "core", programme: null, stage: null }]),
      },
      makeMe({ space_actions: { core: ["ask", "contribute"], hr: ["ask"], it: ["ask"] } }),
    );
    renderApp("/ask?q=camera%20shy%20clients");
    expect(await screen.findByText("No SOP you can access covers this.")).toBeInTheDocument();
    expect(screen.getByText("Ask the delivery team.")).toBeInTheDocument();
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: "Request an SOP" }));
    await waitFor(() => expect(requested).toEqual({ key: "q4", space: "core" }));
    expect(screen.getByRole("link", { name: "Start a draft" })).toHaveAttribute("href", "/write/new?title=camera%20shy%20clients");
    await u.click(screen.getByRole("button", { name: "Suggest an expert" }));
    expect(await screen.findByText(/Avery Tan/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Helpful" })).toBeNull();
  });

  it("has no Start a draft for people who can't write", async () => {
    askApi(() =>
      sse([
        ["section_done", { space: "core", no_answer: true, unavailable: false, contact: null }],
        ["done", { message_id: "m5", question_id: "q5", answered: false }],
      ]),
    );
    renderApp("/ask?q=camera%20shy");
    await screen.findByText("No SOP you can access covers this.");
    expect(screen.queryByRole("link", { name: "Start a draft" })).toBeNull();
  });

  it("points to the Library when the assistant is down", async () => {
    askApi(() => new Response("upstream down", { status: 502 }));
    renderApp("/ask?q=leave%20policy");
    expect(await screen.findByRole("alert")).toHaveTextContent("The assistant is temporarily unavailable; the Library still works.");
    expect(screen.getByRole("link", { name: "Search the Library for this" })).toHaveAttribute("href", "/library?q=leave%20policy");
  });

  it("sends a not-helpful reason", async () => {
    let feedback: unknown = null;
    askApi(
      () => sse([...answer("core", "Answer [1]."), ["done", { message_id: "m1", question_id: "q1", answered: true }]]),
      stored,
      {
        "POST /api/v1/messages/m1/feedback": async (req) => {
          feedback = await req.json();
          return new Response(null, { status: 204 });
        },
      },
    );
    renderApp("/ask?q=open%20workshop");
    const u = userEvent.setup();
    await u.click(await screen.findByRole("button", { name: "Not helpful" }));
    await u.click(screen.getByRole("radio", { name: "Outdated" }));
    await u.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(feedback).toEqual({ helpful: false, reason: "outdated", comment: "" }));
  });

  it("stops a running answer", async () => {
    let aborted = false;
    askApi((req) => {
      req.signal.addEventListener("abort", () => (aborted = true));
      const body = new ReadableStream({
        start(c) {
          c.enqueue(new TextEncoder().encode('event: agent_dispatched\ndata: {"space":"core","title":"Core delivery"}\n\n'));
          req.signal.addEventListener("abort", () => c.error(new DOMException("aborted", "AbortError")));
        },
      });
      return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
    });
    renderApp("/ask?q=slow%20question");
    expect(await screen.findByText("Checking Core delivery…")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(await screen.findByText(/Stopped/)).toBeInTheDocument();
    expect(aborted).toBe(true);
    expect(screen.getByRole("button", { name: "Ask" })).toBeInTheDocument();
  });
});
