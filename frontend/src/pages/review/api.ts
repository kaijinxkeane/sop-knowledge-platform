import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Schemas } from "@/api/client";
import { call } from "@/api/errors";

export type ReviewItem = Schemas["ReviewOut"];
export type Group = Schemas["GroupOut"];
export type Proposal = Schemas["ProposalOut"];
export type Labels = Schemas["LabelsIn"];
export type Governance = Schemas["GovernanceOut"];
export type GovernanceItem = Schemas["GovernanceItem"];
export type Space = Schemas["SpaceOut"];

const REVIEWS = ["reviews"] as const;
const QUEUE = ["classifications", "queue"] as const;

export const useReviews = () =>
  useQuery({
    queryKey: REVIEWS,
    queryFn: () => call(api.GET("/api/v1/reviews", { params: { query: { state: "open" } } })),
  });

/** The AI Classifier's open proposals the backend lets this user see. */
export const useQueue = (enabled = true) =>
  useQuery({ queryKey: QUEUE, queryFn: () => call(api.GET("/api/v1/classifications/queue")), enabled });

/** How many proposals are for unplaced notes (no labels yet) or for placed ones. */
export const countQueue = (groups: Group[] | undefined, unplaced: boolean) =>
  (groups ?? []).reduce((n, g) => n + g.items.filter((p) => (p.current == null) === unplaced).length, 0);

export const useSpaces = () =>
  useQuery({ queryKey: ["spaces"], queryFn: () => call(api.GET("/api/v1/spaces")), staleTime: 60_000 });

export const useGovernance = (enabled: boolean) =>
  useQuery({
    queryKey: ["reports", "governance"],
    queryFn: () => call(api.GET("/api/v1/reports/governance")),
    enabled,
    retry: false,
  });

/** After a decision: queues, Home's counts, the document and the Library may all change. */
function useRefresh() {
  const qc = useQueryClient();
  return () =>
    Promise.all(
      [REVIEWS, QUEUE, ["me", "waiting"], ["me", "recent"], ["documents"], ["document"], ["reports"]].map(
        (queryKey) => qc.invalidateQueries({ queryKey }),
      ),
    );
}

const review = (id: string) => ({ params: { path: { review_id: id } } });
const proposal = (id: string) => ({ params: { path: { proposal_id: id } } });

export function useReviewActions() {
  const refresh = useRefresh();
  return {
    approve: useMutation({
      mutationFn: ({ id, comment, material }: { id: string; comment: string; material?: boolean }) =>
        call(
          api.POST("/api/v1/reviews/{review_id}/approve", {
            ...review(id),
            body: { comment, material_change: !!material },
          }),
        ),
      onSettled: refresh,
    }),
    requestChanges: useMutation({
      mutationFn: ({ id, comment }: { id: string; comment: string }) =>
        call(api.POST("/api/v1/reviews/{review_id}/request-changes", { ...review(id), body: { comment } })),
      onSettled: refresh,
    }),
    withdraw: useMutation({
      mutationFn: (id: string) => call(api.POST("/api/v1/reviews/{review_id}/withdraw", review(id))),
      onSettled: refresh,
    }),
  };
}

export function useLabelActions() {
  const refresh = useRefresh();
  return {
    approve: useMutation({
      mutationFn: ({ id, edit }: { id: string; edit?: Labels }) =>
        call(api.POST("/api/v1/classifications/{proposal_id}/approve", { ...proposal(id), body: edit ?? null })),
      onSettled: refresh,
    }),
    reject: useMutation({
      mutationFn: (id: string) => call(api.POST("/api/v1/classifications/{proposal_id}/reject", proposal(id))),
      onSettled: refresh,
    }),
    bulk: useMutation({
      mutationFn: (ids: string[]) => call(api.POST("/api/v1/classifications/bulk-approve", { body: { ids } })),
      onSettled: refresh,
    }),
  };
}

// --- wording helpers ----------------------------------------------------------------

const RANK: Record<string, number> = { public: 0, internal: 1, restricted: 2 };

/**
 * Does approving `next` let more people read the note than `current` does?
 * Only for the plain-words warning: the backend decides who may approve it.
 * An unplaced note (no labels) is readable by nobody, so any placement widens.
 */
export function widens(current: Labels | null | undefined, next: Labels | null | undefined): boolean {
  if (!next) return false;
  if (!current) return true;
  const level = (s: string) => RANK[s] ?? 2; // unknown counts as restricted (fail closed)
  if (next.space !== current.space) return true;
  if (level(next.sensitivity) < level(current.sensitivity)) return true;
  const had = new Map(current.shared_with?.map((s) => [s.space, level(s.sensitivity)]) ?? []);
  return (next.shared_with ?? []).some((s) => !had.has(s.space) || level(s.sensitivity) < had.get(s.space)!);
}
