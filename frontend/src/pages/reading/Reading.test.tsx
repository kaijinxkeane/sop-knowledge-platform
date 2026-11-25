import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp, type Handler } from "@/test/utils";

const doc = {
  id: "n1",
  title: "Discovery Workshop",
  vault_path: "Programmes/Discovery Workshop.md",
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
};
const status = (over: Record<string, unknown> = {}) => ({
  document_id: "n1",
  required: true,
  due_on: "2026-11-01",
  overdue: true,
  current_version: 3,
  acknowledged_version: null,
  acknowledged_at: null,
  reread: false,
  ...over,
});

function reader(extra: Record<string, Handler>, me = makeMe()) {
  session.signIn("t");
  return mockFetch({
    "GET /api/v1/me": () => json(me),
    "GET /api/v1/documents": () => json([doc]),
    "GET /api/v1/documents/n1": () => json(doc),
    "GET /api/v1/documents/n1/backlinks": () => json([]),
    "GET /api/v1/documents/n1/versions": () => json([]),
    "GET /api/v1/documents/n1/file": () => new Response("# Discovery\n\nOpen with the brand story.\n"),
    "GET /api/v1/me/bookmarks": () => json([]),
    "GET /api/v1/notifications": () => json([]),
    ...extra,
  });
}

beforeEach(() => session.signOut());

describe("required reading in the reader", () => {
  it("asks an assignee to acknowledge the current version", async () => {
    let acked = false;
    reader({
      "GET /api/v1/documents/n1/reading": () =>
        json(acked ? status({ acknowledged_version: 3, acknowledged_at: "2026-11-25T09:00:00Z", overdue: false }) : status()),
      "POST /api/v1/documents/n1/acknowledge": () => ((acked = true), json(status({ acknowledged_version: 3 }))),
    });
    renderApp("/library/n1");
    expect(await screen.findByText(/required reading for you/)).toBeInTheDocument();
    expect(screen.getByText(/Overdue since/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "I have read version 3" }));
    expect(await screen.findByText(/You read version 3 on/)).toBeInTheDocument();
  });

  it("says why after a material change", async () => {
    reader({ "GET /api/v1/documents/n1/reading": () => json(status({ reread: true, due_on: null, overdue: false })) });
    renderApp("/library/n1");
    expect(await screen.findByText(/changed in a way that matters/)).toBeInTheDocument();
  });

  it("shows nothing when the SOP isn't assigned and was never read", async () => {
    const { calls } = reader({
      "GET /api/v1/documents/n1/reading": () => json(status({ required: false, due_on: null, overdue: false })),
    });
    renderApp("/library/n1");
    expect(await screen.findByText("Open with the brand story.")).toBeInTheDocument();
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/reading"))).toBe(true));
    expect(screen.queryByRole("region", { name: "Required reading" })).toBeNull();
    // Staff get no assign button: that's for the space's lead.
    expect(screen.queryByRole("button", { name: "Assign reading" })).toBeNull();
  });

  it("lets a lead assign it to a role with a due date", async () => {
    let body: unknown = null;
    reader(
      {
        "GET /api/v1/documents/n1/reading": () => json(status({ required: false, due_on: null, overdue: false })),
        "GET /api/v1/reading-assignments/roles": () =>
          json([{ name: "core-staff", description: "Trainers" }, { name: "core-lead", description: "" }]),
        "POST /api/v1/reading-assignments": async (req) => ((body = await req.json()), json([], 201)),
      },
      makeMe({ space_actions: { core: ["ask", "contribute", "approve"] } }),
    );
    renderApp("/library/n1");
    await userEvent.click(await screen.findByRole("button", { name: "Assign reading" }));
    await userEvent.click(await screen.findByRole("checkbox", { name: "core-staff" }));
    await userEvent.type(screen.getByLabelText("Due date (optional)"), "2026-12-15");
    await userEvent.click(screen.getByRole("button", { name: "Assign" }));
    expect(await screen.findByText(/Assigned\./)).toBeInTheDocument();
    expect(body).toEqual({ document_id: "n1", user_ids: [], roles: ["core-staff"], due_on: "2026-12-15" });
  });
});

describe("PDF export", () => {
  it("exports the note as this reader sees it, with the token", async () => {
    URL.createObjectURL = vi.fn(() => "blob:http://localhost/pdf");
    URL.revokeObjectURL = vi.fn();
    let body: unknown = null;
    const { calls } = reader({
      "GET /api/v1/documents/n1/reading": () => json(status({ required: false, due_on: null, overdue: false })),
      "POST /api/v1/exports": async (req) => (
        (body = await req.json()), new Response(new Uint8Array([37, 80, 68, 70]), { headers: { "content-type": "application/pdf" } })
      ),
    });
    renderApp("/library/n1");
    await userEvent.click(await screen.findByRole("button", { name: "Export PDF" }));
    await waitFor(() => expect(body).toEqual({ document_id: "n1" }));
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.headers.get("Authorization")).toBe("Bearer t");
  });

  it("says when a space has export turned off", async () => {
    reader({
      "GET /api/v1/documents/n1/reading": () => json(status({ required: false, due_on: null, overdue: false })),
      "POST /api/v1/exports": () => json({ detail: "PDF export is turned off for this space" }, 403),
    });
    renderApp("/library/n1");
    await userEvent.click(await screen.findByRole("button", { name: "Export PDF" }));
    expect(await screen.findByText("PDF export is turned off for this space.")).toBeInTheDocument();
  });
});

describe("Home and Admin", () => {
  const home = {
    "GET /api/v1/notifications": () => json([]),
    "GET /api/v1/me/gaps": () => json([]),
    "GET /api/v1/me/recent": () => json([]),
    "GET /api/v1/me/waiting": () => json({ reviews: 0, drafts: 0, labels: 0 }),
    "GET /api/v1/me/bookmarks": () => json([]),
    "GET /api/v1/documents/stages": () => json([]),
    "GET /api/v1/documents": () => json([]),
    "GET /api/v1/handovers": () => json([]),
  };
  const usage = {
    month: "2026-11",
    days: [{ day: "2026-11-24", calls: 40, cloud_calls: 30, cost_usd: 0.42 }],
    tiers: [
      { tier: "answer", model: "hosted-model", provider: "cloud_api", location: "cloud", calls: 30, fallbacks: 0, input_tokens: 900000, output_tokens: 100000, cache_read_tokens: 0, cost_usd: 0.14 },
      { tier: "router", model: "qwen3:8b", provider: "openai_compat", location: "local", calls: 10, fallbacks: 2, input_tokens: 5000, output_tokens: 500, cache_read_tokens: 0, cost_usd: 0 },
    ],
    total_cost_usd: 0.42,
    cloud_calls: 30,
    local_calls: 10,
    fallbacks: 2,
    priced: true,
  };

  it("lists my unread required reading on Home, and no cost card for staff", async () => {
    session.signIn("t");
    const { calls } = mockFetch({
      ...home,
      "GET /api/v1/me": () => json(makeMe()),
      "GET /api/v1/me/required-reading": () =>
        json([
          { document_id: "n1", title: "Discovery Workshop", due_on: null, overdue: false, acknowledged_at: null, current_version: 2, reread: true },
          { document_id: "n2", title: "Already Read", due_on: null, overdue: false, acknowledged_at: "2026-11-01T00:00:00Z", current_version: 1, reread: false },
        ]),
    });
    renderApp("/");
    expect(await screen.findByRole("link", { name: "Discovery Workshop" })).toHaveAttribute("href", "/library/n1");
    expect(screen.getByText("Read again")).toBeInTheDocument();
    expect(screen.queryByText("Already Read")).toBeNull();
    expect(calls.map((c) => new URL(c.url).pathname)).not.toContain("/api/v1/reports/usage");
  });

  it("shows the admin this month's cost on Home and the breakdown in Admin", async () => {
    session.signIn("t");
    mockFetch({
      ...home,
      "GET /api/v1/me": () => json(makeMe({ global_actions: ["manage_users"] })),
      "GET /api/v1/me/required-reading": () => json([]),
      "GET /api/v1/reports/usage": () => json(usage),
      "GET /api/v1/admin/users": () => json([]),
    });
    renderApp("/");
    expect(await screen.findByRole("link", { name: "$0.42" })).toHaveAttribute("href", "/admin/usage");
    renderApp("/admin/usage");
    expect(await screen.findByRole("cell", { name: "hosted-model" })).toBeInTheDocument();
    expect(screen.getByText(/answered by a fallback model/)).toBeInTheDocument();
  });
});
