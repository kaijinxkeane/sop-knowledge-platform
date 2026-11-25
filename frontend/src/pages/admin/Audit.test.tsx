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
    expect(await screen.findByText("Approved an SOP version")).toBeInTheDocument();
    expect(screen.getByText("Approved after review")).toBeInTheDocument();
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

  it("shows details in plain words, with people's names when the admin can list users", async () => {
    session.signIn("t");
    const pat = "bbbbbbbb-0000-0000-0000-000000000000";
    mockFetch({
      "GET /api/v1/me": () => json(makeMe({ global_actions: ["view_audit", "manage_users"] })),
      "GET /api/v1/notifications": () => json([]),
      "GET /api/v1/admin/users": () => json([{ id: pat, display_name: "Pat Lim" }]),
      "GET /api/v1/admin/audit": () =>
        json([
          {
            id: 7, ts: "2026-11-25T09:00:00Z", actor_id: pat, action: "pdf_exported", target_type: "document", target_id: "c0ffee00-0000-0000-0000-000000000000",
            details: { documents: ["c0ffee00-0000-0000-0000-000000000000"], restricted: true },
          },
          {
            id: 8, ts: "2026-11-25T10:00:00Z", actor_id: pat, action: "note_saved", target_type: "document", target_id: null,
            details: { commit: "0123456789abcdef0123456789abcdef01234567", bytes: 20480, review: null },
          },
        ]),
    });
    renderApp("/admin/audit");
    expect(await screen.findByText("Exported a PDF")).toBeInTheDocument();
    expect(screen.getAllByText("Pat Lim").length).toBeGreaterThan(0);
    expect(screen.getByText("Restricted content")).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();
    expect(screen.getByText("1 (c0ffee00)")).toBeInTheDocument();
    expect(screen.getByText("version 0123456")).toBeInTheDocument();
    expect(screen.getByText("20 KB")).toBeInTheDocument();
    // Empty values are left out; the raw record is still one click away.
    expect(screen.queryByText("Review")).toBeNull();
    expect(screen.getAllByText("Raw").length).toBe(2);
  });

  it("exports CSV that a spreadsheet can't run as formulas", () => {
    const csv = toCsv([{ ...EVENTS[0]!, target_id: "=HYPERLINK(1)" }], () => "Pat");
    expect(csv.split("\r\n")[1]).toContain(`"'=HYPERLINK(1)"`);
    expect(csv).toContain(`"{""method"":""review""}"`);
  });

  it("puts plain words first in the CSV and keeps the raw record after", () => {
    const pat = "bbbbbbbb-0000-0000-0000-000000000000";
    const csv = toCsv(
      [{ ...EVENTS[0]!, actor_id: pat, target_id: pat, target_type: "user", details: { restricted: true, bytes: 2048 } }],
      () => "Pat Lim",
      (id) => (id === pat ? "Pat Lim" : undefined),
    );
    const [head, row] = csv.split("\r\n");
    expect(head).toBe(
      `"Event #","When","Who","What","About","Details","ts","actor_id","action","target_type","target_id","details_raw"`,
    );
    expect(row).toContain(`"Approved an SOP version","Person · Pat Lim","Restricted content: Yes; File size: 2 KB"`);
    expect(row).toContain(`"sop_approved","user","${pat}","{""restricted"":true,""bytes"":2048}"`);
  });
});
