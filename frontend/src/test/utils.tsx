import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";
import type { Me } from "@/auth/permissions";
import { makeQueryClient } from "@/app/App";
import { routes } from "@/app/routes";

export type Handler = (req: Request) => Response | Promise<Response>;

export const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

/** Route fetch calls by "METHOD /path"; anything unrouted is a 404. */
export function mockFetch(routesByKey: Record<string, Handler>) {
  const calls: Request[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = input instanceof Request ? input : new Request(new URL(String(input), "http://localhost"), init);
    calls.push(req);
    const key = `${req.method} ${new URL(req.url).pathname}`;
    const handler = routesByKey[key];
    return handler ? handler(req) : json({ detail: "not found" }, 404);
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls };
}

export function renderApp(path = "/") {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = makeQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, queryClient };
}

export function makeMe(overrides: Partial<Me> = {}): Me {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    email: "pat@example.test",
    display_name: "Pat Example",
    home_space: "core",
    roles: ["employee"],
    scopes: { core: "public", hr: "public", it: "public" },
    space_actions: { core: ["ask"], hr: ["ask"], it: ["ask"] },
    global_actions: [],
    notice: { version: "1", acknowledged: true },
    ...overrides,
  };
}
