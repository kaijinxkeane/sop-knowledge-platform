import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, mockFetch, renderApp } from "@/test/utils";

function openInvite(hash: string) {
  window.history.replaceState(null, "", `/invite${hash}`);
  session.signOut();
  return renderApp("/invite");
}

async function setPassword(a: string, b = a) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("New password"), a);
  await user.type(screen.getByLabelText("Type it again"), b);
  await user.click(screen.getByRole("button", { name: "Set password" }));
}

describe("accept invite", () => {
  it("reads the token from the fragment, then removes it from the address bar", async () => {
    const { calls } = mockFetch({
      "POST /api/v1/auth/invite/accept": () => new Response(null, { status: 204 }),
    });
    openInvite("#tok-123");
    expect(window.location.hash).toBe("");
    await setPassword("a long enough password");
    expect(await screen.findByRole("status")).toHaveTextContent("Your password is set");
    expect(await calls[0]!.clone().json()).toEqual({
      token: "tok-123",
      password: "a long enough password",
    });
  });

  it("checks length and the second entry before sending anything", async () => {
    const { calls } = mockFetch({});
    openInvite("#tok-123");
    await setPassword("short");
    expect(await screen.findByRole("alert")).toHaveTextContent("at least 12 characters");
    await userEvent.clear(screen.getByLabelText("New password"));
    await userEvent.clear(screen.getByLabelText("Type it again"));
    await setPassword("a long enough password", "a different password!");
    expect(await screen.findByRole("alert")).toHaveTextContent("don't match");
    expect(calls).toHaveLength(0);
  });

  it("explains an expired link", async () => {
    mockFetch({
      "POST /api/v1/auth/invite/accept": () => json({ detail: "this link is invalid or has expired" }, 400),
    });
    openInvite("#old");
    await setPassword("a long enough password");
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid or has expired");
  });

  it("says so when the link has no token", async () => {
    mockFetch({});
    openInvite("");
    expect(await screen.findByRole("alert")).toHaveTextContent("incomplete");
  });
});
