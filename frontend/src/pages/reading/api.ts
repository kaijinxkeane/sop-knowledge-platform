import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Schemas } from "@/api/client";
import { call } from "@/api/errors";

export type ReadingStatus = Schemas["StatusOut"];
export type Required = Schemas["RequiredOut"];
export type DocStatus = Schemas["DocStatus"];

const doc = (id: string) => ({ params: { path: { document_id: id } } });

export const useReadingStatus = (id: string, enabled = true) =>
  useQuery({
    queryKey: ["reading", "status", id],
    queryFn: () => call(api.GET("/api/v1/documents/{document_id}/reading", doc(id))),
    enabled,
  });

export const useMyReading = () =>
  useQuery({ queryKey: ["reading", "mine"], queryFn: () => call(api.GET("/api/v1/me/required-reading")) });

export const useReadStatus = (enabled: boolean) =>
  useQuery({ queryKey: ["reading", "report"], queryFn: () => call(api.GET("/api/v1/reports/read-status")), enabled });

export const useAssignableRoles = (enabled: boolean) =>
  useQuery({
    queryKey: ["reading", "roles"],
    queryFn: () => call(api.GET("/api/v1/reading-assignments/roles")),
    enabled,
    staleTime: 5 * 60_000,
  });

export function useReadingActions() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["reading"] });
  return {
    acknowledge: useMutation({
      mutationFn: (id: string) => call(api.POST("/api/v1/documents/{document_id}/acknowledge", doc(id))),
      onSettled: refresh,
    }),
    assign: useMutation({
      mutationFn: (body: Schemas["ReadingAssignIn"]) => call(api.POST("/api/v1/reading-assignments", { body })),
      onSettled: refresh,
    }),
    unassign: useMutation({
      mutationFn: (id: string) =>
        call(api.DELETE("/api/v1/reading-assignments/{assignment_id}", { params: { path: { assignment_id: id } } })),
      onSettled: refresh,
    }),
  };
}

export const shortDate = (d: string) => new Date(d).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
