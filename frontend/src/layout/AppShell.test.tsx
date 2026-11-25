import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { _offerForTest } from "@/app/pwa";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp } from "@/test/utils";

function navLinks() {
  const nav = screen.getByRole("navigation", { name: "Main" });
  return within(nav).getAllByRole("link").map((l) => l.textContent);
}

describe("notification bell", () => {
  it("counts unread, hides titles it wasn't given, and opens the review", async () => {
    session.signIn("t");
    let read = "";
    const { router } = (mockFetch({
      "GET /api/v1/me": () => json(makeMe()),
      "GET /api/v1/notifications": () =>
        json([
          { id: "a", kind: "review_requested", document_id: "n1", title: "Discovery Workshop", ref_id: "r1", created_at: "2026-11-24T09:00:00Z", read: false },
          { id: "b", kind: "sop_approved", document_id: null, title: null, ref_id: null, created_at: "2026-11-23T09:00:00Z", read: true },
        ]),
      "POST /api/v1/notifications/a/read": (req) => ((read = new URL(req.url).pathname), new Response(null, { status: 204 })),
    }), renderApp("/"));
    const bell = await screen.findByRole("button", { name: "Notifications (1 unread)" });
    await userEvent.click(bell);
    expect(screen.getByText("Approved: a document you can no longer open")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Review requested: Discovery Workshop"));
    await waitFor(() => expect(router.state.location.pathname).toBe("/review"));
    expect(router.state.location.search).toBe("?tab=changes&id=r1");
    await waitFor(() => expect(read).toBe("/api/v1/notifications/a/read"));
  });
});

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

describe("install app", () => {
  it("shows Install app only when the browser offers it, and hides it after", async () => {
    session.signIn("t");
    mockFetch({ "GET /api/v1/me": () => json(makeMe()), "GET /api/v1/notifications": () => json([]) });
    renderApp("/");
    await screen.findByRole("navigation", { name: "Main" });
    expect(screen.queryByRole("button", { name: "Install app" })).toBeNull();
    const prompt = vi.fn(async () => undefined);
    _offerForTest(Object.assign(new Event("beforeinstallprompt"), { prompt, userChoice: Promise.resolve({ outcome: "accepted" }) }));
    await userEvent.click(await screen.findByRole("button", { name: "Install app" }));
    expect(prompt).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Install app" })).toBeNull());
  });
});
