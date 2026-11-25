import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp } from "@/test/utils";
import { toCsv } from "./Audit";

const auditor = makeMe({ global_actions: ["view_audit"] });
const EVENTS = [
  { id: 42, ts: "2026-11-24T09:00:00Z", actor_id: "aaaaaaaa-0000-0000-0000-000000000000", action: "sop_approved", target_type: "document", target_id: "d1", details: { method: "review" } },
];

beforeEach(() => session.signOut());

describe("audit log viewer", () => {
  it("opens for an auditor, filters by action and verifies the chain", async () => {
    session.signIn("t");
    const { calls } = mockFetch({
      "GET /api/v1/me": () => json(auditor),
      "GET /api/v1/notifications": () => json([]),
      "GET /api/v1/admin/audit": () => json(EVENTS),
      "GET /api/v1/admin/audit/verify": () => json({ ok: false, events: 120, first_bad_id: 77 }),
    });
    const { router } = renderApp("/admin");
    await waitFor(() => expect(router.state.location.pathname).toBe("/admin/audit"));
    expect(await screen.findByText("sop_approved")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Users" })).toBeNull();
    // Without manage_users the user list isn't requested; actors show as short ids.
    expect(calls.some((c) => new URL(c.url).pathname === "/api/v1/admin/users")).toBe(false);
    expect(screen.getByText("aaaaaaaa")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Action"), "login_failed");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(calls.some((c) => new URL(c.url).searchParams.get("action") === "login_failed")).toBe(true),
    );
    await userEvent.click(screen.getByRole("button", { name: "Verify the chain" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("first broken event is #77");
  });

  it("exports CSV that a spreadsheet can't run as formulas", () => {
    const csv = toCsv([{ ...EVENTS[0]!, target_id: "=HYPERLINK(1)" }], () => "Pat");
    expect(csv.split("\r\n")[1]).toContain(`"'=HYPERLINK(1)"`);
    expect(csv).toContain(`"{""method"":""review""}"`);
  });
});
