import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp, type Handler } from "@/test/utils";

const lead = makeMe({ space_actions: { core: ["ask", "contribute", "review", "approve"], hr: ["ask"], it: ["ask"] } });
const hr = makeMe({ global_actions: ["view_gap_reports"] });

const TOPIC = {
  id: "t1",
  space: "core",
  label: "Rescheduling a discovery session",
  status: "open",
  programme: "Signature Personal Brand Programme",
  stage: "discovery",
  questions: 7,
  people: 4,
  last_30_days: 3,
  reasons: { no_answer: 5, not_helpful: 2 },
  examples: ["how do I move a discovery session", "client wants a new date"],
  access_gap: null,
  addressed_at: null,
};

function retainApi(me = lead, extra: Record<string, Handler> = {}) {
  session.signIn("t");
  return mockFetch({
    "GET /api/v1/me": () => json(me),
    "GET /api/v1/notifications": () => json([]),
    "GET /api/v1/spaces/core/gaps": () => json([TOPIC]),
    "GET /api/v1/reports/gaps": () =>
      json([{ id: "t1", space: "core", label: TOPIC.label, status: "addressed", programme: null, stage: null, questions: 7, people: 4, by_role: { trainer: 3, other: 1 }, before_addressed_30d: 6, after_addressed_30d: 1 }]),
    "GET /api/v1/reports/coverage": () =>
      json([
        { programme: "Signature", stage: "discovery", published: 2, stale: 1, titles: ["Discovery Workshop", "Intake Call"] },
        { programme: "Signature", stage: "delivery", published: 0, stale: 0, titles: [] },
      ]),
    ...extra,
  });
}

beforeEach(() => session.signOut());

describe("Retain → gaps", () => {
  it("shows a lead their space's topics with anonymous examples and changes the follow-up", async () => {
    let body: unknown = null;
    retainApi(lead, { "PATCH /api/v1/gap-topics/t1": async (req) => ((body = await req.json()), new Response(null, { status: 204 })) });
    renderApp("/retain");
    expect(await screen.findByRole("heading", { name: TOPIC.label })).toBeInTheDocument();
    expect(screen.getByText("7 questions from 4 people · 3 in the last 30 days")).toBeInTheDocument();
    expect(screen.getByText("5 no answer · 2 marked not helpful")).toBeInTheDocument();
    expect(screen.getByText("client wants a new date")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Draft an SOP" }).getAttribute("href")).toContain("title=Rescheduling");
    await userEvent.selectOptions(screen.getByLabelText("Follow-up"), "training_planned");
    await waitFor(() => expect(body).toEqual({ status: "training_planned" }));
  });

  it("shows HR counts by role and the trend, never example questions", async () => {
    const { calls } = retainApi(hr);
    renderApp("/retain");
    expect(await screen.findByText("Questions 30 days before / after it was addressed: 6 → 1")).toBeInTheDocument();
    expect(screen.getByText("trainer: 3")).toBeInTheDocument();
    expect(screen.queryByText("client wants a new date")).toBeNull();
    // HR isn't a lead, so the space report isn't even asked for.
    expect(calls.some((c) => new URL(c.url).pathname.includes("/spaces/"))).toBe(false);
    expect(screen.queryByRole("tab", { name: "Bus factor" })).toBeNull();
  });

  it("is a 404 for plain staff", async () => {
    retainApi(makeMe());
    renderApp("/retain");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });
});

describe("Retain → coverage", () => {
  it("draws the programme × stage grid and offers to create a missing SOP", async () => {
    retainApi();
    renderApp("/retain?tab=coverage");
    const grid = await screen.findByRole("table");
    expect(within(grid).getByText("2 published")).toBeInTheDocument();
    expect(within(grid).getByText("1 due")).toBeInTheDocument();
    await userEvent.click(within(grid).getByText("None"));
    expect(screen.getByRole("link", { name: "Create one" }).getAttribute("href")).toBe("/write/new?programme=Signature&stage=delivery");
    await userEvent.click(within(grid).getByText("2 published"));
    expect(screen.getByText("Intake Call")).toBeInTheDocument();
  });
});

describe("Retain → health reports", () => {
  it("lists review-due SOPs, single authors and possible conflicts", async () => {
    let dismissed = false;
    retainApi(lead, {
      "GET /api/v1/spaces/core/stale": () => json([{ document_id: "d1", title: "Intake Call", review_due: "2026-10-01", approved_on: "2025-10-01", overdue: true }]),
      "GET /api/v1/reports/bus-factor": () =>
        json({ single_author: [{ document_id: "d2", title: "Room Setup", only_author: "Avery Tan", space: "core", author_leaving_on: "2026-12-31" }], leaving: [{ name: "Avery Tan", leaving_on: "2026-12-31", owner_of: 4, sole_author_of: 2 }] }),
      "GET /api/v1/reports/conflicts": () =>
        json([{ id: "c1", document_a: "d1", document_b: "d2", title_a: "Intake Call", title_b: "Room Setup", explanation: "One says 2 hours, the other 3.", created_at: "2026-11-20T03:00:00Z" }]),
      "POST /api/v1/conflicts/c1/dismiss": () => ((dismissed = true), new Response(null, { status: 204 })),
    });
    renderApp("/retain?tab=due");
    expect(await screen.findByText("Overdue")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Bus factor" }));
    expect(await screen.findByText(/only Avery Tan/)).toBeInTheDocument();
    expect(screen.getByText(/owns 4, sole author of 2/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Conflicts" }));
    expect(await screen.findByText("One says 2 hours, the other 3.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Not a conflict" }));
    await waitFor(() => expect(dismissed).toBe(true));
  });
});
