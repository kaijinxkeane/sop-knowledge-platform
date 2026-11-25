import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp, type Handler } from "@/test/utils";

const author = makeMe({ id: "u-author", space_actions: { core: ["ask", "contribute"], hr: ["ask"], it: ["ask"] }, home_space: "core" });
const receiver = makeMe({ id: "u-recv", display_name: "Jordan Lee" });

const base = {
  id: "h1",
  document_id: "doc-h1",
  title: "Acme handover",
  space: "core",
  status: "sent",
  author: "Pat Example",
  mine: false,
  receivers: [{ user_id: "u-recv", name: "Jordan Lee", acknowledged_at: null }],
  created_at: "2026-11-24T09:00:00Z",
  sent_at: "2026-11-24T10:00:00Z",
  issues: [],
};
const fields = { client: "Acme", programme: "Signature", stage: "delivery", done: "Two sessions run.", actions: [], sessions: [], no_upcoming_sessions: true, preferences: "", files: "", contacts: "", risks: "" };
const detail = { ...base, fields, markdown: "---\ndoc_type: handover\n---\n# Acme handover\n\nTwo sessions run.\n" };

function hoApi(me = author, extra: Record<string, Handler> = {}) {
  session.signIn("t");
  return mockFetch({
    "GET /api/v1/me": () => json(me),
    "GET /api/v1/notifications": () => json([]),
    "GET /api/v1/documents": () => json([]),
    "GET /api/v1/documents/stages": () => json(["discovery", "delivery"]),
    "GET /api/v1/handovers": () => json([base]),
    "GET /api/v1/handovers/h1": () => json(detail),
    "GET /api/v1/handovers/h1/comments": () => json([]),
    ...extra,
  });
}

beforeEach(() => session.signOut());

describe("handovers", () => {
  it("writes a handover: picks receivers by name and saves the template fields", async () => {
    let sent: Record<string, unknown> | null = null;
    hoApi(author, {
      "GET /api/v1/people": (req) =>
        json(new URL(req.url).searchParams.get("q") === "jor" ? [{ id: "u-recv", name: "Jordan Lee" }] : []),
      "POST /api/v1/handovers": async (req) => ((sent = (await req.json()) as Record<string, unknown>), json({ ...base, id: "h2", status: "draft", mine: true }, 201)),
      "GET /api/v1/handovers/h2": () => json({ ...detail, id: "h2", status: "draft", mine: true }),
      "GET /api/v1/handovers/h2/comments": () => json([]),
    });
    const { router } = renderApp("/handovers/new");
    await userEvent.type(await screen.findByLabelText("Title"), "Acme handover");
    await userEvent.type(screen.getByLabelText("Client"), "Acme");
    await userEvent.click(screen.getByRole("button", { name: "Add an action" }));
    await userEvent.type(screen.getByLabelText("Action"), "Send the deck");
    await userEvent.type(screen.getByLabelText("Owner"), "Jordan");
    // No receiver yet: refused before anything is sent.
    await userEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Pick at least one receiver.");
    await userEvent.type(screen.getByLabelText("Receivers"), "jor");
    await userEvent.click(await screen.findByRole("button", { name: "Jordan Lee" }));
    await userEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/handovers/h2"));
    expect(sent).toMatchObject({
      title: "Acme handover",
      space: "core",
      receivers: ["u-recv"],
      fields: { client: "Acme", actions: [{ text: "Send the deck", owner: "Jordan", due: null }] },
    });
  });

  it("lets a receiver acknowledge and ask a question", async () => {
    let acked = false;
    let comment: unknown = null;
    hoApi(receiver, {
      "POST /api/v1/handovers/h1/acknowledge": () => ((acked = true), json(base)),
      "POST /api/v1/handovers/h1/comments": async (req) => ((comment = await req.json()), json({ id: "c1", author: "Jordan Lee", body: "x", created_at: "2026-11-25T00:00:00Z" }, 201)),
    });
    renderApp("/handovers");
    expect(await screen.findByText("Awaiting my acknowledgement")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Acme handover" }));
    expect(await screen.findByText("Two sessions run.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send to receivers" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "I have read and understood this handover" }));
    await waitFor(() => expect(acked).toBe(true));
    await userEvent.type(screen.getByLabelText("Ask the author a question…"), "Who is the client contact?");
    await userEvent.click(screen.getByRole("button", { name: "Post" }));
    await waitFor(() => expect(comment).toEqual({ body: "Who is the client contact?" }));
  });

  it("runs the completeness check and sends a draft", async () => {
    let sent = false;
    hoApi(author, {
      "GET /api/v1/handovers/h1": () => json({ ...detail, status: "draft", mine: true }),
      "POST /api/v1/handovers/h1/check": () => json([{ section: "Open actions", message: "An action has no due date.", source: "rules" }]),
      "POST /api/v1/handovers/h1/send": () => ((sent = true), json({ ...base, mine: true })),
    });
    renderApp("/handovers/h1");
    await userEvent.click(await screen.findByRole("button", { name: "Check completeness" }));
    expect(await screen.findByText("An action has no due date.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Send to receivers" }));
    await waitFor(() => expect(sent).toBe(true));
  });

  it("looks like a missing page when the backend says 404", async () => {
    hoApi(makeMe(), { "GET /api/v1/handovers/h1": () => json({ detail: "not found" }, 404) });
    renderApp("/handovers/h1");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });
});
