import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Schemas } from "@/api/client";
import { call } from "@/api/errors";

export type Handover = Schemas["HandoverOut"];
export type HandoverDetail = Schemas["HandoverDetail"];
type Action = NonNullable<Schemas["HandoverFields"]["actions"]>[number];
type Session = NonNullable<Schemas["HandoverFields"]["sessions"]>[number];
/** The form's fields, with the lists always present. */
export type Fields = Schemas["HandoverFields"] & { actions: Action[]; sessions: Session[] };
export type Issue = Schemas["IssueOut"];
export type Colleague = Schemas["ColleagueOut"];

export const emptyFields = (): Fields => ({
  client: "",
  programme: "",
  stage: "",
  done: "",
  actions: [],
  sessions: [],
  no_upcoming_sessions: false,
  preferences: "",
  files: "",
  contacts: "",
  risks: "",
});

const ID = (id: string) => ({ params: { path: { handover_id: id } } });

export const useHandovers = () =>
  useQuery({ queryKey: ["handovers"], queryFn: () => call(api.GET("/api/v1/handovers")) });

export const useHandover = (id: string) =>
  useQuery({ queryKey: ["handovers", id], queryFn: () => call(api.GET("/api/v1/handovers/{handover_id}", ID(id))) });

export const useComments = (id: string) =>
  useQuery({
    queryKey: ["handovers", id, "comments"],
    queryFn: () => call(api.GET("/api/v1/handovers/{handover_id}/comments", ID(id))),
  });

/** Names only, for picking receivers or members; the search text isn't kept. */
export const usePeople = (q: string) =>
  useQuery({
    queryKey: ["people", q],
    queryFn: () => call(api.GET("/api/v1/people", { params: { query: { q } } })),
    staleTime: 60_000,
    gcTime: 60_000,
    placeholderData: (prev) => prev,
  });

export function useHandoverActions() {
  const qc = useQueryClient();
  const refresh = () =>
    Promise.all([qc.invalidateQueries({ queryKey: ["handovers"] }), qc.invalidateQueries({ queryKey: ["notifications"] })]);
  return {
    create: useMutation({
      mutationFn: (body: Schemas["HandoverIn"]) => call(api.POST("/api/v1/handovers", { body })),
      onSettled: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: string; body: Schemas["HandoverUpdate"] }) =>
        call(api.PUT("/api/v1/handovers/{handover_id}", { ...ID(id), body })),
      onSettled: refresh,
    }),
    check: useMutation({ mutationFn: (id: string) => call(api.POST("/api/v1/handovers/{handover_id}/check", ID(id))) }),
    send: useMutation({
      mutationFn: (id: string) => call(api.POST("/api/v1/handovers/{handover_id}/send", ID(id))),
      onSettled: refresh,
    }),
    acknowledge: useMutation({
      mutationFn: (id: string) => call(api.POST("/api/v1/handovers/{handover_id}/acknowledge", ID(id))),
      onSettled: refresh,
    }),
    comment: useMutation({
      mutationFn: ({ id, body }: { id: string; body: string }) =>
        call(api.POST("/api/v1/handovers/{handover_id}/comments", { ...ID(id), body: { body } })),
      onSettled: (_d, _e, v) => qc.invalidateQueries({ queryKey: ["handovers", v.id, "comments"] }),
    }),
  };
}
