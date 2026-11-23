import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp } from "@/test/utils";

const MARKDOWN =
  "**How this assistant uses your information.** Stored for 24 months.\n\n" +
  '<img src=x onerror="alert(1)"> <script>alert(2)</script>';

describe("staff notice", () => {
  it("keeps the app closed until the notice is acknowledged", async () => {
    session.signIn("t");
    let acknowledged = false;
    const { calls } = mockFetch({
      "GET /api/v1/me": () => json(makeMe({ notice: { version: "2026-11-21", acknowledged } })),
      "GET /api/v1/notice": () =>
        json({ version: "2026-11-21", acknowledged, markdown: MARKDOWN }),
      "POST /api/v1/notice/acknowledge": () => {
        acknowledged = true;
        return new Response(null, { status: 204 });
      },
    });
    renderApp("/library");

    expect(await screen.findByText("Please read this notice before you use the assistant.")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
    expect(screen.getByText("How this assistant uses your information.").tagName).toBe("STRONG");
    // Raw HTML in the notice is never rendered.
    expect(document.querySelector("main img, main script")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "I have read this notice" }));
    expect(await screen.findByRole("navigation", { name: "Main" })).toBeInTheDocument();
    const ack = calls.find((c) => c.url.endsWith("/notice/acknowledge"))!;
    expect(await ack.clone().json()).toEqual({ version: "2026-11-21" });
  });

  it("asks again when the notice changed while it was open", async () => {
    session.signIn("t");
    let version = "v1";
    mockFetch({
      "GET /api/v1/me": () => json(makeMe({ notice: { version: "v1", acknowledged: false } })),
      "GET /api/v1/notice": () => json({ version, acknowledged: false, markdown: `Notice ${version}` }),
      "POST /api/v1/notice/acknowledge": () => {
        version = "v2";
        return json({ detail: "the notice has changed; reload it" }, 409);
      },
    });
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "I have read this notice" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("just updated");
    await waitFor(() => expect(screen.getByText("Notice v2")).toBeInTheDocument());
  });
});
