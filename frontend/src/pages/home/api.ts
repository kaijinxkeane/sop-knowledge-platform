import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";

export const useRecent = () =>
  useQuery({ queryKey: ["me", "recent"], queryFn: () => unwrap(api.GET("/api/v1/me/recent", { params: { query: { limit: 6 } } })) });

export const useWaiting = () =>
  useQuery({ queryKey: ["me", "waiting"], queryFn: () => unwrap(api.GET("/api/v1/me/waiting")) });

export const useMyGaps = () => useQuery({ queryKey: ["me", "gaps"], queryFn: () => unwrap(api.GET("/api/v1/me/gaps")) });
