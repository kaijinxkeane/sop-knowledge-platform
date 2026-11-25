import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Schemas } from "@/api/client";
import { call } from "@/api/errors";

export type Topic = Schemas["TopicOut"];
export type HrTopic = Schemas["HrTopicOut"];
export type Cell = Schemas["CellOut"];
export type Stale = Schemas["StaleOut"];
export type BusFactor = Schemas["BusFactorOut"];
export type Conflict = Schemas["ConflictOut"];

export const TOPIC_STATUSES = ["open", "training_planned", "addressed"] as const;

export const useSpaceGaps = (space: string | null) =>
  useQuery({
    queryKey: ["retain", "gaps", space],
    queryFn: () => call(api.GET("/api/v1/spaces/{space}/gaps", { params: { path: { space: space! } } })),
    enabled: !!space,
  });

export const useHrGaps = (enabled: boolean) =>
  useQuery({ queryKey: ["retain", "hr-gaps"], queryFn: () => call(api.GET("/api/v1/reports/gaps")), enabled });

export const useCoverage = (enabled = true) =>
  useQuery({ queryKey: ["retain", "coverage"], queryFn: () => call(api.GET("/api/v1/reports/coverage")), enabled });

/** Review-due SOPs across several spaces (Home's lead card). */
export const useStaleAll = (spaces: string[]) =>
  useQuery({
    queryKey: ["retain", "stale-all", spaces],
    queryFn: async () =>
      (
        await Promise.all(
          spaces.map((space) =>
            call(api.GET("/api/v1/spaces/{space}/stale", { params: { path: { space }, query: { within_days: 14 } } })),
          ),
        )
      ).flat(),
    enabled: spaces.length > 0,
  });

export const useStale = (space: string | null, days: number) =>
  useQuery({
    queryKey: ["retain", "stale", space, days],
    queryFn: () =>
      call(api.GET("/api/v1/spaces/{space}/stale", { params: { path: { space: space! }, query: { within_days: days } } })),
    enabled: !!space,
  });

export const useBusFactor = (enabled: boolean) =>
  useQuery({ queryKey: ["retain", "bus-factor"], queryFn: () => call(api.GET("/api/v1/reports/bus-factor")), enabled });

export const useConflicts = () =>
  useQuery({ queryKey: ["retain", "conflicts"], queryFn: () => call(api.GET("/api/v1/reports/conflicts")) });

export function useRetainActions() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["retain"] });
  return {
    setStatus: useMutation({
      mutationFn: ({ id, status }: { id: string; status: string }) =>
        call(api.PATCH("/api/v1/gap-topics/{topic_id}", { params: { path: { topic_id: id } }, body: { status } })),
      onSettled: refresh,
    }),
    dismiss: useMutation({
      mutationFn: (id: string) =>
        call(api.POST("/api/v1/conflicts/{conflict_id}/dismiss", { params: { path: { conflict_id: id } } })),
      onSettled: refresh,
    }),
  };
}

/** Spaces where this person is a lead (approve) or reviewer, from /me. */
export function leadSpaces(spaceActions: Record<string, string[]> | undefined, action: "approve" | "review" = "review") {
  return Object.entries(spaceActions ?? {})
    .filter(([, acts]) => acts.includes("approve") || (action === "review" && acts.includes("review")))
    .map(([s]) => s)
    .sort();
}
