import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useSyncExternalStore } from "react";
import { api, unwrap } from "@/api/client";
import { session } from "./session";

export function useSession() {
  return useSyncExternalStore(session.subscribe, session.get);
}

export function useMe() {
  const { status } = useSession();
  return useQuery({
    queryKey: ["me"],
    queryFn: () => unwrap(api.GET("/api/v1/me")),
    enabled: status === "signed-in",
    staleTime: 60_000,
  });
}

export function useSignOut() {
  const queryClient = useQueryClient();
  return useCallback(async () => {
    try {
      await api.POST("/api/v1/auth/logout");
    } finally {
      session.signOut();
      // Drop everything cached for this user before anyone else signs in.
      queryClient.clear();
    }
  }, [queryClient]);
}
