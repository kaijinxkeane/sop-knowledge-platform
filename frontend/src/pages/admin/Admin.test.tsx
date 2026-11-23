import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp, type Handler } from "@/test/utils";

const ADMIN_ID = "00000000-0000-0000-0000-0000000000aa";
const me = makeMe({
  id: ADMIN_ID,
  display_name: "Ada Admin",
  roles: ["employee", "platform-admin"],
  global_actions: ["manage_users", "view_audit"],
});

const user = (over: Record<string, unknown>) => ({
  id: "00000000-0000-0000-0000-0000000000b1",
  email: "sam@staff.example.com",
  display_name: "Sam Lee",
  home_space: "core",
  roles: ["employee", "core-staff"],
  is_active: true,
  totp_enabled: true,
  invite_pending: false,
  locked: false,
  created_at: "2026-11-01T00:00:00Z",
  last_login_at: null,
  leaving_on: null,
  ...over,
});

const roles = [
  { id: "r1", name: "employee", description: "Every member of staff.", user_count: 2, grants: [] },
  { id: "r2", name: "core-staff", description: "Trainers.", user_count: 1, grants: [] },
  {
    id: "r3",
    name: "platform-admin",
    description: "Manages users.",
    user_count: 1,
    grants: [
      { id: "g1", space: null, max_sensitivity: "public", actions: ["manage_users", "view_audit"] },
    ],
  },
];

const options = {
  spaces: [
    { name: "core", title: "Core" },
    { name: "hr", title: "HR" },
  ],
  space_actions: ["admin", "approve", "ask", "contribute", "review"],
  global_actions: ["manage_users", "view_audit", "view_gap_reports"],
  sensitivities: ["public", "internal", "restricted"],
};

function adminApi(extra: Record<string, Handler> = {}) {
  session.signIn("t");
  return mockFetch({
    "GET /api/v1/me": () => json(me),
    "GET /api/v1/admin/users": () =>
      json([user({ id: ADMIN_ID, display_name: "Ada Admin", roles: ["employee", "platform-admin"] }), user({})]),
    "GET /api/v1/admin/roles": () => json(roles),
    "GET /api/v1/admin/options": () => json(options),
    ...extra,
  });
}

describe("admin: users", () => {
  it("lists people with their status", async () => {
    adminApi();
    renderApp("/admin/users");
    const row = (await screen.findByText("Sam Lee")).closest("tr")!;
    expect(within(row).getByText("core-staff")).toBeInTheDocument();
    expect(within(row).getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("(you)")).toBeInTheDocument();
  });

  it("invites a person and shows the link once, with the token in the fragment", async () => {
    const { calls } = adminApi({
      "POST /api/v1/admin/users": () =>
        json(
          {
            user: user({ id: "new", display_name: "Riley Ong", invite_pending: true }),
            invite_token: "secret-invite-token",
            expires_in_hours: 72,
          },
          201,
        ),
    });
    renderApp("/admin/users");
    const u = userEvent.setup();
    await u.click(await screen.findByRole("button", { name: "Invite a person" }));
    await u.type(screen.getByLabelText("Name"), "Riley Ong");
    await u.type(screen.getByLabelText("Email"), "riley@staff.example.com");
    await u.selectOptions(screen.getByLabelText("Home space"), "core");
    await u.click(screen.getByLabelText(/core-staff/));
    await u.click(screen.getByRole("button", { name: "Create invite link" }));

    expect(await screen.findByText("Sign-in link for Riley Ong")).toBeInTheDocument();
    expect(screen.getByText(`${window.location.origin}/invite#secret-invite-token`)).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/admin/users"))!;
    expect(await post.clone().json()).toEqual({
      email: "riley@staff.example.com",
      display_name: "Riley Ong",
      roles: ["employee", "core-staff"],
      home_space: "core",
    });
    await u.click(screen.getAllByRole("button", { name: "Close" })[0]!);
    await waitFor(() => expect(screen.queryByText(/secret-invite-token/)).not.toBeInTheDocument());
  });

  it("won't offer new roles to yourself (two-person rule) or let you deactivate yourself", async () => {
    adminApi();
    renderApp("/admin/users");
    await userEvent.click(await screen.findByRole("button", { name: "Edit Ada Admin" }));
    expect(screen.getByText("Another administrator must add roles to your account.")).toBeInTheDocument();
    expect(screen.getByLabelText(/core-staff/)).toBeDisabled();
    expect(screen.getByLabelText(/platform-admin/)).toBeEnabled(); // you can still drop one
    expect(screen.getByLabelText(/Account active/)).toBeDisabled();
  });

  it("sends only the fields that changed, and shows the server's refusal", async () => {
    const { calls } = adminApi({
      "PATCH /api/v1/admin/users/00000000-0000-0000-0000-0000000000b1": () =>
        json({ detail: "this would leave no active user who can manage users" }, 409),
    });
    renderApp("/admin/users");
    const u = userEvent.setup();
    await u.click(await screen.findByRole("button", { name: "Edit Sam Lee" }));
    await u.click(screen.getByLabelText(/Account active/));
    await u.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This would leave no active user who can manage users.",
    );
    const patch = calls.find((c) => c.method === "PATCH")!;
    expect(await patch.clone().json()).toEqual({ is_active: false });
  });
});

describe("admin: roles and grants", () => {
  it("offers only company actions for a company-wide grant", async () => {
    const { calls } = adminApi({
      "POST /api/v1/admin/roles/r2/grants": () => json(roles[1], 201),
    });
    renderApp("/admin/roles");
    const form = await screen.findByRole("form", { name: "Add grant: core-staff" });
    const u = userEvent.setup();
    await u.selectOptions(within(form).getByLabelText("Applies to"), "Company-wide");
    expect(within(form).queryByLabelText("Can read up to")).not.toBeInTheDocument();
    expect(within(form).queryByLabelText("Contribute (write)")).not.toBeInTheDocument();
    await u.click(within(form).getByLabelText("View gap reports"));
    await u.click(within(form).getByRole("button", { name: "Add grant" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/roles/r2/grants"))).toBe(true));
    const post = calls.find((c) => c.url.endsWith("/roles/r2/grants"))!;
    expect(await post.clone().json()).toEqual({
      space: null,
      max_sensitivity: "public",
      actions: ["view_gap_reports"],
    });
  });

  it("adds a space grant with its sensitivity", async () => {
    const { calls } = adminApi({
      "POST /api/v1/admin/roles/r2/grants": () => json(roles[1], 201),
    });
    renderApp("/admin/roles");
    const form = await screen.findByRole("form", { name: "Add grant: core-staff" });
    const u = userEvent.setup();
    await u.selectOptions(within(form).getByLabelText("Can read up to"), "internal");
    await u.click(within(form).getByLabelText("Ask and read"));
    await u.click(within(form).getByLabelText("Contribute (write)"));
    await u.click(within(form).getByRole("button", { name: "Add grant" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/roles/r2/grants"))).toBe(true));
    const post = calls.find((c) => c.url.endsWith("/roles/r2/grants"))!;
    expect(await post.clone().json()).toEqual({
      space: "core",
      max_sensitivity: "internal",
      actions: ["ask", "contribute"],
    });
  });

  it("asks before removing a grant and shows a refusal", async () => {
    adminApi({
      "DELETE /api/v1/admin/grants/g1": () =>
        json({ detail: "this would leave no active user who can manage users" }, 409),
    });
    renderApp("/admin/roles");
    const u = userEvent.setup();
    await u.click(await screen.findByRole("button", { name: "Remove grant" }));
    const dialog = await screen.findByRole("dialog");
    await u.click(within(dialog).getByRole("button", { name: "Remove grant" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("no active user");
  });

  it("is hidden from people without manage_users", async () => {
    session.signIn("t");
    mockFetch({ "GET /api/v1/me": () => json(makeMe()) });
    renderApp("/admin/roles");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
