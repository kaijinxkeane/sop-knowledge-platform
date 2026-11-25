import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp, type Handler } from "@/test/utils";

const coreLead = makeMe({ id: "u-lead", space_actions: { core: ["ask", "contribute", "review", "approve"], hr: ["ask"], it: ["ask"] } });
const hrLead = makeMe({ id: "u-hr", space_actions: { core: ["ask"], hr: ["ask", "contribute", "approve"], it: ["ask"] } });
const member = makeMe({ id: "u-m" });

const PROJECT = {
  id: "p1",
  name: "Acme rollout",
  space: "project-acme-rollout",
  folder: "Projects/acme-rollout",
  lead: { id: "u-lead", name: "Pat Example" },
  starts_on: "2026-11-01",
  ends_on: "2027-02-01",
  active: true,
  days_left: 68,
  members: [{ id: "u-lead", name: "Pat Example" }, { id: "u-m", name: "Sam Lee" }],
  shares: [{ id: "s1", space: "hr", status: "requested", scope: null, max_sensitivity: "internal", folders: [], documents: 0, note: "", approved_until: null, in_force: false, renewal_requested: false }],
  my_role: "lead",
};

function prApi(me = coreLead, extra: Record<string, Handler> = {}) {
  session.signIn("t");
  return mockFetch({
    "GET /api/v1/me": () => json(me),
    "GET /api/v1/notifications": () => json([]),
    "GET /api/v1/projects": () => json([PROJECT]),
    "GET /api/v1/projects/p1": () => json(PROJECT),
    "GET /api/v1/project-shares": () => json([]),
    "GET /api/v1/spaces": () => json([{ name: "core", title: "Core", access: "internal", actions: [] }, { name: "hr", title: "HR", access: "public", actions: [] }]),
    "GET /api/v1/documents": () =>
      json([
        { id: "d1", title: "Leave Policy", vault_path: "HR/Policies/Leave Policy.md", kind: "note", doc_type: "policy", status: "published", programme: null, stage: null, owner: null, access: [{ space: "hr", sensitivity: "internal" }], approved: true, pending_change: false, review_due: null },
      ]),
    ...extra,
  });
}

beforeEach(() => session.signOut());

describe("projects", () => {
  it("lets a space lead create a project, naming members and departments to ask", async () => {
    let body: Record<string, unknown> | null = null;
    prApi(coreLead, {
      "GET /api/v1/people": () => json([{ id: "u-m", name: "Sam Lee" }]),
      "POST /api/v1/projects": async (req) => ((body = (await req.json()) as Record<string, unknown>), json({ ...PROJECT, id: "p2" }, 201)),
      "GET /api/v1/projects/p2": () => json({ ...PROJECT, id: "p2" }),
    });
    const { router } = renderApp("/projects");
    await userEvent.click(await screen.findByRole("button", { name: "New project" }));
    await userEvent.type(screen.getByLabelText("Project name"), "Acme rollout");
    await userEvent.type(screen.getByLabelText("Ends on"), "2027-02-01");
    await userEvent.type(screen.getByLabelText("Members"), "sam");
    await userEvent.click(await screen.findByRole("button", { name: "Sam Lee" }));
    await userEvent.click(screen.getByLabelText("HR"));
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/projects/p2"));
    expect(body).toEqual({ name: "Acme rollout", ends_on: "2027-02-01", lead_id: null, members: ["u-m"], shares: [{ space: "hr", note: "" }] });
  });

  it("shows the project lead its shares and lead tools", async () => {
    prApi();
    renderApp("/projects/p1");
    expect(await screen.findByText("Waiting for the lead")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "End the project now" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open its notes in the Library" }).getAttribute("href")).toBe(
      "/library?view=department&group=project-acme-rollout",
    );
  });

  it("gives a member no lead tools and no 'New project' button", async () => {
    prApi(member, { "GET /api/v1/projects/p1": () => json({ ...PROJECT, my_role: "member" }) });
    renderApp("/projects/p1");
    expect(await screen.findByRole("heading", { name: "Acme rollout" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "End the project now" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove Sam Lee" })).toBeNull();
  });

  it("lets the department lead share only selected folders, at internal by default", async () => {
    let body: unknown = null;
    prApi(hrLead, {
      "GET /api/v1/projects": () => json([]),
      "GET /api/v1/project-shares": () =>
        json([{ id: "s1", project_id: "p1", project: "Acme rollout", project_lead: "Pat Example", members: 2, ends_on: "2027-02-01", space: "hr", status: "requested", note: "Needs the leave rules", renewal_requested: false }]),
      "POST /api/v1/project-shares/s1/approve": async (req) => ((body = await req.json()), json({})),
    });
    renderApp("/projects");
    expect(await screen.findByText("Needs the leave rules")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("What to share"), "selected");
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose at least one folder or SOP.");
    await userEvent.click(screen.getByLabelText("HR/Policies"));
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(body).toEqual({ scope: "selected", max_sensitivity: "internal", folders: ["HR/Policies"], document_ids: [] }));
  });

  it("looks like a missing page for a project you're not in", async () => {
    prApi(makeMe(), { "GET /api/v1/projects/p1": () => json({ detail: "not found" }, 404) });
    renderApp("/projects/p1");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });
});
