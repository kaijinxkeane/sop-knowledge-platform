import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Schemas } from "@/api/client";
import { call } from "@/api/errors";

export type Project = Schemas["ProjectOut"];
export type ShareRequest = Schemas["ShareRequestOut"];
export type ApproveShare = Schemas["ApproveShareIn"];

const P = (id: string) => ({ params: { path: { project_id: id } } });
const S = (id: string) => ({ params: { path: { share_id: id } } });

export const useProjects = () =>
  useQuery({ queryKey: ["projects"], queryFn: () => call(api.GET("/api/v1/projects")) });

export const useProject = (id: string) =>
  useQuery({ queryKey: ["projects", id], queryFn: () => call(api.GET("/api/v1/projects/{project_id}", P(id))) });

export const useShareRequests = () =>
  useQuery({ queryKey: ["project-shares"], queryFn: () => call(api.GET("/api/v1/project-shares")) });

export function useProjectActions() {
  const qc = useQueryClient();
  const refresh = () =>
    Promise.all(
      [["projects"], ["project-shares"], ["documents"], ["me"], ["spaces"]].map((queryKey) => qc.invalidateQueries({ queryKey })),
    );
  const useAction = <A, R>(fn: (a: A) => Promise<R>) => useMutation({ mutationFn: fn, onSettled: refresh });
  return {
    create: useAction((body: Schemas["ProjectIn"]) => call(api.POST("/api/v1/projects", { body }))),
    rename: useAction(({ id, ...body }: { id: string } & Schemas["ProjectUpdateIn"]) =>
      call(api.PATCH("/api/v1/projects/{project_id}", { ...P(id), body }))),
    addMembers: useAction(({ id, user_ids }: { id: string; user_ids: string[] }) =>
      call(api.POST("/api/v1/projects/{project_id}/members", { ...P(id), body: { user_ids } }))),
    removeMember: useAction(({ id, user }: { id: string; user: string }) =>
      call(api.DELETE("/api/v1/projects/{project_id}/members/{user_id}", { params: { path: { project_id: id, user_id: user } } }))),
    requestShare: useAction(({ id, space, note }: { id: string; space: string; note: string }) =>
      call(api.POST("/api/v1/projects/{project_id}/shares", { ...P(id), body: { space, note } }))),
    renew: useAction(({ id, ends_on }: { id: string; ends_on: string }) =>
      call(api.POST("/api/v1/projects/{project_id}/renew", { ...P(id), body: { ends_on } }))),
    close: useAction((id: string) => call(api.POST("/api/v1/projects/{project_id}/close", P(id)))),
    approve: useAction(({ id, body }: { id: string; body: ApproveShare }) =>
      call(api.POST("/api/v1/project-shares/{share_id}/approve", { ...S(id), body }))),
    decline: useAction((id: string) => call(api.POST("/api/v1/project-shares/{share_id}/decline", S(id)))),
    revoke: useAction((id: string) => call(api.POST("/api/v1/project-shares/{share_id}/revoke", S(id)))),
  };
}
