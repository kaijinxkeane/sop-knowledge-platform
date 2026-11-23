import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp } from "@/test/utils";

const GAP = {
  key: "s1,s2",
  label: "camera-shy clients",
  count: 4,
  last_at: "2026-11-23T00:00:00Z",
  message: "",
  related: [],
  experts: ["Avery Tan"],
  space: "core",
  programme: null,
  stage: null,
};

function setup(routes: Record<string, () => Response>, me = makeMe()) {
  session.signIn("t");
  return mockFetch({
    "GET /api/v1/me": () => json(me),
    "GET /api/v1/documents": () => json([]),
    "GET /api/v1/documents/stages": () => json([]),
    "GET /api/v1/me/bookmarks": () => json([]),
    "GET /api/v1/me/gaps": () => json([]),
    "GET /api/v1/me/waiting": () => json({ reviews: 0, drafts: 0, labels: 0 }),
    "GET /api/v1/me/recent": () => json([]),
    ...routes,
  });
}

describe("Home cards", () => {
  it("shows no empty cards", async () => {
    setup({});
    renderApp("/");
    await screen.findByRole("heading", { name: "What do you need to know?" });
    await waitFor(() => expect(screen.queryByRole("region")).toBeNull());
  });

  it("shows gaps, what's waiting and what was approved recently", async () => {
    let requested: unknown = null;
    setup(
      {
        "GET /api/v1/me/gaps": () => json([GAP]),
        "GET /api/v1/me/waiting": () => json({ reviews: 2, drafts: 1, labels: 0 }),
        "GET /api/v1/me/recent": () =>
          json([{ id: "d1", title: "Running the Discovery Workshop", kind: "note", doc_type: "sop", programme: "Signature Personal Brand Programme", stage: "discovery", approved_at: "2026-11-20T10:00:00Z" }]),
        "POST /api/v1/me/gaps/request": () => {
          requested = true;
          return json({ requested: true }, 202);
        },
      },
      makeMe({ space_actions: { core: ["ask", "contribute"], hr: ["ask"], it: ["ask"] } }),
    );
    renderApp("/");
    const gaps = await screen.findByRole("region", { name: "Gaps from your searches" });
    expect(within(gaps).getByText("camera-shy clients")).toBeInTheDocument();
    expect(within(gaps).getByRole("link", { name: "Start a draft" })).toHaveAttribute("href", "/write/new?title=camera-shy%20clients");
    await userEvent.click(within(gaps).getByRole("button", { name: "Request an SOP" }));
    await waitFor(() => expect(requested).toBe(true));
    const waiting = screen.getByRole("region", { name: "Waiting for you" });
    expect(within(waiting).getByRole("link", { name: "2 to review" })).toHaveAttribute("href", "/review");
    expect(within(waiting).getByRole("link", { name: "1 unsubmitted drafts" })).toBeInTheDocument();
    expect(within(waiting).queryByText(/AI label/)).toBeNull();
    const recent = screen.getByRole("region", { name: "Recently approved" });
    expect(within(recent).getByRole("link", { name: "Running the Discovery Workshop" })).toHaveAttribute("href", "/library/d1");
  });
});
