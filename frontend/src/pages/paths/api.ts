import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Schemas } from "@/api/client";
import { call } from "@/api/errors";

export type Path = Schemas["PathOut"];
export type PathItem = Schemas["PathItemOut"];
export type PathBody = Schemas["PathIn"];
export type Completion = Schemas["CompletionOut"];

const path = (id: string) => ({ params: { path: { path_id: id } } });

export const useMyPaths = () =>
  useQuery({ queryKey: ["paths", "mine"], queryFn: () => call(api.GET("/api/v1/me/paths")) });

export const useMyPath = (id: string) =>
  useQuery({ queryKey: ["paths", "mine", id], queryFn: () => call(api.GET("/api/v1/me/paths/{path_id}", path(id))) });

export const useManagedPaths = (enabled: boolean) =>
  useQuery({ queryKey: ["paths", "managed"], queryFn: () => call(api.GET("/api/v1/paths")), enabled });

export const useManagedPath = (id: string | undefined) =>
  useQuery({
    queryKey: ["paths", "managed", id],
    queryFn: () => call(api.GET("/api/v1/paths/{path_id}", path(id!))),
    enabled: !!id,
  });

export const useCompletion = (enabled: boolean) =>
  useQuery({ queryKey: ["paths", "completion"], queryFn: () => call(api.GET("/api/v1/reports/path-completion")), enabled });

export function usePathActions() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["paths"] });
  return {
    create: useMutation({ mutationFn: (body: PathBody) => call(api.POST("/api/v1/paths", { body })), onSettled: refresh }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: string; body: PathBody }) => call(api.PUT("/api/v1/paths/{path_id}", { ...path(id), body })),
      onSettled: refresh,
    }),
    remove: useMutation({ mutationFn: (id: string) => call(api.DELETE("/api/v1/paths/{path_id}", path(id))), onSettled: refresh }),
    assign: useMutation({
      mutationFn: ({ id, body }: { id: string; body: Schemas["PathAssignIn"] }) =>
        call(api.POST("/api/v1/paths/{path_id}/assign", { ...path(id), body })),
      onSettled: refresh,
    }),
    done: useMutation({
      mutationFn: (itemId: string) => call(api.POST("/api/v1/path-items/{item_id}/done", { params: { path: { item_id: itemId } } })),
      onSettled: refresh,
    }),
  };
}

/** Leads (approve on a space) and HR manage paths; the backend checks both. */
export function canManagePaths(me: Schemas["MeOut"] | undefined): boolean {
  if (!me) return false;
  return me.global_actions.includes("view_gap_reports") || Object.values(me.space_actions).some((a) => a.includes("approve"));
}

export const leadOf = (me: Schemas["MeOut"] | undefined) =>
  Object.entries(me?.space_actions ?? {})
    .filter(([, a]) => a.includes("approve"))
    .map(([s]) => s)
    .sort();
