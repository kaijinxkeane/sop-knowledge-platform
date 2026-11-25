import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp } from "@/test/utils";

beforeEach(() => session.signOut());

const common = {
  "GET /api/v1/notifications": () => json([]),
  "GET /api/v1/me/gaps": () => json([]),
  "GET /api/v1/me/recent": () => json([]),
  "GET /api/v1/me/waiting": () => json({ reviews: 0, drafts: 0, labels: 0 }),
  "GET /api/v1/me/bookmarks": () => json([]),
  "GET /api/v1/documents/stages": () => json([]),
  "GET /api/v1/documents": () => json([]),
};

describe("Home role cards", () => {
  it("shows a lead unplaced notes, review due and coverage", async () => {
    session.signIn("t");
    mockFetch({
      ...common,
      "GET /api/v1/me": () => json(makeMe({ space_actions: { core: ["ask", "approve"] } })),
      "GET /api/v1/handovers": () => json([]),
      "GET /api/v1/classifications/queue": () =>
        json([{ group_key: "Inbox|core|restricted", folder: "Inbox", proposed_space: "core", proposed_sensitivity: "restricted", items: [{ id: "p1", current: null }, { id: "p2", current: null }] }]),
      "GET /api/v1/spaces/core/stale": () => json([{ document_id: "d1", title: "Intake Call", review_due: "2026-11-01", approved_on: null, overdue: true }]),
      "GET /api/v1/reports/coverage": () =>
        json([
          { programme: "A", stage: "discovery", published: 1, stale: 1, titles: [] },
          { programme: "A", stage: "delivery", published: 0, stale: 0, titles: [] },
        ]),
    });
    renderApp("/");
    expect(await screen.findByRole("link", { name: "2 notes nobody can read yet" })).toHaveAttribute("href", "/review?tab=unplaced");
    expect(await screen.findByRole("link", { name: "Intake Call" })).toBeInTheDocument();
    expect(screen.getByText("1 overdue →")).toBeInTheDocument();
    expect(await screen.findByText("1 of 2 programme stages have an SOP")).toBeInTheDocument();
  });

  it("shows anyone the handovers waiting for their acknowledgement, and no lead cards", async () => {
    session.signIn("t");
    const { calls } = mockFetch({
      ...common,
      "GET /api/v1/me": () => json(makeMe({ id: "u1" })),
      "GET /api/v1/handovers": () =>
        json([{ id: "h1", title: "Acme handover", status: "sent", author: "Avery Tan", receivers: [{ user_id: "u1", name: "Pat", acknowledged_at: null }] }]),
    });
    renderApp("/");
    expect(await screen.findByRole("link", { name: "Acme handover" })).toHaveAttribute("href", "/handovers/h1");
    const asked = calls.map((c) => new URL(c.url).pathname);
    expect(asked).not.toContain("/api/v1/reports/coverage");
    expect(asked).not.toContain("/api/v1/classifications/queue");
  });
});
