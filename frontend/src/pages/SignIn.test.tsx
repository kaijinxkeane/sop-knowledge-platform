import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch, renderApp } from "@/test/utils";

const signedIn = { access_token: "tok-abc", token_type: "bearer", expires_in: 900 };

async function enterPassword() {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Email"), "pat@example.test");
  await user.type(screen.getByLabelText("Password"), "correct horse");
  await user.click(screen.getByRole("button", { name: "Continue" }));
  return user;
}

describe("sign-in", () => {
  it("sends a signed-out visitor to sign-in, then back where they were after password + code", async () => {
    session.signOut();
    const { calls } = mockFetch({
      "POST /api/v1/auth/login": () => json({ status: "totp_required", token: "mfa-1", expires_in: 600 }),
      "POST /api/v1/auth/totp/verify": () => json(signedIn),
      "GET /api/v1/me": () => json(makeMe({ space_actions: { core: ["ask", "contribute"] } })),
    });
    const { router } = renderApp("/library");
    await waitFor(() => expect(router.state.location.pathname).toBe("/sign-in"));

    const user = await enterPassword();
    await user.type(await screen.findByLabelText("Code"), "123 456");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/library"));
    const verify = calls.find((c) => c.url.endsWith("/totp/verify"))!;
    expect(await verify.clone().json()).toEqual({ token: "mfa-1", code: "123456" });
    expect(await screen.findByRole("link", { name: "Write" })).toBeInTheDocument();
  });

  it("keeps the access token out of browser storage", async () => {
    session.signOut();
    mockFetch({
      "POST /api/v1/auth/login": () => json({ status: "totp_required", token: "mfa-1", expires_in: 600 }),
      "POST /api/v1/auth/totp/verify": () => json(signedIn),
      "GET /api/v1/me": () => json(makeMe()),
    });
    renderApp("/sign-in");
    const user = await enterPassword();
    await user.type(await screen.findByLabelText("Code"), "123456");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await screen.findByRole("navigation", { name: "Main" });

    const stored = [localStorage, sessionStorage].flatMap((s) =>
      Object.keys(s).map((k) => s.getItem(k) ?? ""),
    );
    expect(stored.join()).not.toContain("tok-abc");
    expect(document.cookie).not.toContain("tok-abc");
  });

  it("shows the same message for a wrong password as for an unknown email", async () => {
    session.signOut();
    mockFetch({ "POST /api/v1/auth/login": () => json({ detail: "invalid email, password or code" }, 401) });
    renderApp("/sign-in");
    await enterPassword();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That email, password or code is not right.",
    );
  });

  it("explains a lockout", async () => {
    session.signOut();
    mockFetch({ "POST /api/v1/auth/login": () => json({}, 429) });
    renderApp("/sign-in");
    await enterPassword();
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
  });

  it("sets up two-factor on first sign-in, with the QR code drawn locally", async () => {
    session.signOut();
    const { calls } = mockFetch({
      "POST /api/v1/auth/login": () =>
        json({ status: "totp_enrollment_required", token: "enr-1", expires_in: 600 }),
      "POST /api/v1/auth/totp/enroll": () =>
        json({
          secret: "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
          otpauth_uri: "otpauth://totp/SOP:pat%40example.test?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
        }),
      "POST /api/v1/auth/totp/enroll/confirm": () => json(signedIn),
      "GET /api/v1/me": () => json(makeMe()),
    });
    const { router } = renderApp("/sign-in");
    const user = await enterPassword();
    await user.click(await screen.findByRole("button", { name: "Set up now" }));

    const qr = await screen.findByRole("img", { name: "QR code for your authenticator app" });
    expect(qr.getAttribute("src")).toMatch(/^data:image\/svg\+xml/);
    expect(screen.getByText("JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Code"), "654321");
    await user.click(screen.getByRole("button", { name: "Finish setup" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));

    const confirm = calls.find((c) => c.url.endsWith("/enroll/confirm"))!;
    expect(await confirm.clone().json()).toEqual({ token: "enr-1", code: "654321" });
    // The secret never leaves for a QR service: every request stayed on our API.
    for (const c of calls) expect(new URL(c.url).pathname).toMatch(/^\/api\/v1\//);
  });

  it("sends users back to sign-in if two-factor was set up meanwhile", async () => {
    session.signOut();
    mockFetch({
      "POST /api/v1/auth/login": () =>
        json({ status: "totp_enrollment_required", token: "enr-1", expires_in: 600 }),
      "POST /api/v1/auth/totp/enroll": () => json({ detail: "two-factor is already set up" }, 409),
    });
    renderApp("/sign-in");
    const user = await enterPassword();
    await user.click(await screen.findByRole("button", { name: "Set up now" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already set up");
  });

  it("ignores a return path that leaves the app", async () => {
    session.signOut();
    mockFetch({
      "POST /api/v1/auth/login": () => json({ status: "totp_required", token: "m", expires_in: 600 }),
      "POST /api/v1/auth/totp/verify": () => json(signedIn),
      "GET /api/v1/me": () => json(makeMe()),
    });
    const { router } = renderApp("/sign-in");
    await router.navigate("/sign-in", { state: { from: "//evil.example/x" } });
    const user = await enterPassword();
    await user.type(await screen.findByLabelText("Code"), "123456");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });
});
