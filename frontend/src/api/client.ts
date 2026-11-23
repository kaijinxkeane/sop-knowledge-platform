import createClient from "openapi-fetch";
import { refreshSession, session } from "@/auth/session";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

// Sign-in steps carry their own short-lived tokens; a 401 there means "wrong
// code", not "session expired", so they are never retried.
const AUTH_PREFIX = "/api/v1/auth/";

function withToken(request: Request): Request {
  const token = session.get().accessToken;
  if (!token) return request;
  const next = new Request(request);
  next.headers.set("Authorization", `Bearer ${token}`);
  return next;
}

/** Adds the access token; on a 401, refreshes once and retries the request. */
export async function authFetch(request: Request): Promise<Response> {
  const retry = request.clone();
  const res = await globalThis.fetch(withToken(request));
  if (res.status !== 401 || new URL(request.url).pathname.startsWith(AUTH_PREFIX)) return res;
  if (!(await refreshSession())) return res;
  return globalThis.fetch(withToken(retry));
}

export const api = createClient<paths>({
  baseUrl: typeof window === "undefined" ? "http://localhost" : window.location.origin,
  fetch: authFetch,
  credentials: "same-origin",
});

/** A failed API call, keeping only the status (never the body: it may quote content). */
export class ApiError extends Error {
  constructor(public readonly status: number) {
    super(`API request failed with status ${status}`);
  }
}

/** Unwrap an openapi-fetch result, throwing ApiError on failure. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, response } = await call;
  if (!response.ok || data === undefined) throw new ApiError(response.status);
  return data;
}
