import { describe, expect, it } from "vitest";
import { session } from "@/auth/session";
import { json, makeMe, mockFetch } from "@/test/utils";
import { api } from "./client";

describe("authFetch", () => {
  it("sends the access token as a bearer header", async () => {
    session.signIn("tok-1");
    const { calls } = mockFetch({ "GET /api/v1/me": () => json(makeMe()) });
    await api.GET("/api/v1/me");
    expect(calls[0]!.headers.get("Authorization")).toBe("Bearer tok-1");
  });

  it("refreshes once on a 401 and retries with the new token", async () => {
    session.signIn("old");
    const { calls } = mockFetch({
      "GET /api/v1/me": (req) =>
        req.headers.get("Authorization") === "Bearer new" ? json(makeMe()) : json({}, 401),
      "POST /api/v1/auth/refresh": () => json({ access_token: "new", token_type: "bearer", expires_in: 900 }),
    });
    const { data } = await api.GET("/api/v1/me");
    expect(data?.display_name).toBe("Pat Example");
    expect(calls.map((c) => new URL(c.url).pathname)).toEqual([
      "/api/v1/me",
      "/api/v1/auth/refresh",
      "/api/v1/me",
    ]);
    expect(session.get()).toEqual({ status: "signed-in", accessToken: "new" });
  });

  it("shares one refresh between parallel 401s (the backend treats a reused cookie as theft)", async () => {
    session.signIn("old");
    const { calls } = mockFetch({
      "GET /api/v1/me": (req) =>
        req.headers.get("Authorization") === "Bearer new" ? json(makeMe()) : json({}, 401),
      "POST /api/v1/auth/refresh": async () => {
        await new Promise((r) => setTimeout(r, 10));
        return json({ access_token: "new", token_type: "bearer", expires_in: 900 });
      },
    });
    await Promise.all([api.GET("/api/v1/me"), api.GET("/api/v1/me"), api.GET("/api/v1/me")]);
    expect(calls.filter((c) => c.url.endsWith("/auth/refresh"))).toHaveLength(1);
  });

  it("signs out when the refresh fails", async () => {
    session.signIn("old");
    mockFetch({
      "GET /api/v1/me": () => json({}, 401),
      "POST /api/v1/auth/refresh": () => json({}, 401),
    });
    const { response } = await api.GET("/api/v1/me");
    expect(response.status).toBe(401);
    expect(session.get().status).toBe("signed-out");
  });

  it("never retries sign-in steps (a 401 there means a wrong code)", async () => {
    const { calls } = mockFetch({ "POST /api/v1/auth/totp/verify": () => json({}, 401) });
    await api.POST("/api/v1/auth/totp/verify", { body: { token: "x", code: "000000" } });
    expect(calls).toHaveLength(1);
  });
});
