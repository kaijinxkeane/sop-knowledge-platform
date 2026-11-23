import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";
import { ApiError } from "@/api/client";
import { refreshSession, session } from "@/auth/session";
import { routes } from "./routes";

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // 403/404 won't change on retry; a hidden item must stay hidden.
        retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
        refetchOnWindowFocus: false,
      },
    },
  });
}

export function App() {
  const [queryClient] = useState(makeQueryClient);
  const [router] = useState(() => createBrowserRouter(routes));

  useEffect(() => {
    // Restore the session from the refresh cookie after a reload.
    if (session.get().status === "unknown") void refreshSession();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
