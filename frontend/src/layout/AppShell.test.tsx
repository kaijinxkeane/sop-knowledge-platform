import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp } from "@/test/utils";

function navLinks() {
  const nav = screen.getByRole("navigation", { name: "Main" });
  return within(nav).getAllByRole("link").map((l) => l.textContent);
}

describe("app shell", () => {
  it("shows an employee only Ask and Library", async () => {
    session.signIn("t");
    mockFetch({ "GET /api/v1/me": () => json(makeMe()) });
    renderApp("/");
    await screen.findByRole("navigation", { name: "Main" });
    expect(navLinks()).toEqual(["Ask", "Library"]);
  });

  it("shows a platform admin the Admin menu", async () => {
    session.signIn("t");
    mockFetch({ "GET /api/v1/me": () => json(makeMe({ global_actions: ["manage_users", "view_audit"] })) });
    renderApp("/");
    await screen.findByRole("navigation", { name: "Main" });
    expect(navLinks()).toContain("Admin");
  });

  it("answers a hidden section with the same page as a missing one", async () => {
    session.signIn("t");
    mockFetch({ "GET /api/v1/me": () => json(makeMe()) });
    renderApp("/admin");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });

  it("signs out: revokes the session, forgets the token and returns to sign-in", async () => {
    session.signIn("t");
    const { calls } = mockFetch({
      "GET /api/v1/me": () => json(makeMe()),
      "POST /api/v1/auth/logout": () => new Response(null, { status: 204 }),
    });
    const { router } = renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/sign-in"));
    expect(calls.some((c) => c.url.endsWith("/auth/logout"))).toBe(true);
    expect(session.get()).toEqual({ status: "signed-out", accessToken: null });
  });

  it("restores nothing and shows sign-in when the refresh cookie is gone", async () => {
    // status "unknown" until the boot refresh answers
    mockFetch({ "POST /api/v1/auth/refresh": () => json({}, 401) });
    const { router } = renderApp("/");
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    const { refreshSession } = await import("@/auth/session");
    await refreshSession();
    await waitFor(() => expect(router.state.location.pathname).toBe("/sign-in"));
  });
});
