import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { messageOf } from "@/api/errors";
import { Loading } from "@/app/routes";
import { useMe } from "@/auth/hooks";
import { VersionDiff } from "@/components/VersionDiff";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { useVersion } from "@/pages/library/api";
import { useReviewActions, useReviews, type ReviewItem } from "./api";

const when = (iso: string) => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

/** The submitted version against the last approved one, side by side. */
function ReviewDiff({ r }: { r: ReviewItem }) {
  const left = useVersion(r.document_id, r.base_commit ?? null);
  const right = useVersion(r.document_id, r.git_commit ?? null);
  const before = r.base_commit ? left.data?.content : "";
  if (left.isError || right.isError || !r.git_commit) {
    return <p role="alert" className="text-sm">{t("review.diffUnavailable")}</p>;
  }
  if (before === undefined || !right.data) return <Loading />;
  return (
    <div className="space-y-2">
      {!r.base_commit && <p className="text-sm text-muted-foreground">{t("review.firstVersion")}</p>}
      <VersionDiff before={before} after={right.data.content} />
    </div>
  );
}

function Detail({ r }: { r: ReviewItem }) {
  const me = useMe();
  const actions = useReviewActions();
  const [comment, setComment] = useState("");
  const [material, setMaterial] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const spaceActions = (r.space && me.data?.space_actions[r.space]) || [];
  const canApprove = spaceActions.includes("approve");
  const canReview = canApprove || spaceActions.includes("review");
  const busy = actions.approve.isPending || actions.requestChanges.isPending || actions.withdraw.isPending;

  const run = async (fn: () => Promise<unknown>, message: string) => {
    setError(null);
    try {
      await fn();
      setDone(message);
    } catch (e) {
      setError(messageOf(e));
    }
  };

  if (done) return <p role="status" className="text-sm">{done}</p>;
  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h2 className="text-xl font-semibold">{r.title}</h2>
        <p className="text-sm text-muted-foreground">
          {t("review.requestedBy", { name: r.requested_by, when: when(r.requested_at) })}
          {r.space && <> · {t("review.space", { space: r.space })}</>}
          {" · "}
          <Link to={`/library/${r.document_id}`} className="underline">{t("review.openNote")}</Link>
        </p>
      </div>
      {r.stale && <Alert>{t("review.stale")}</Alert>}
      {r.flags.length > 0 && (
        <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">{t("review.flags")}</p>
      )}
      {r.self_review && canApprove && (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {t("review.selfReview")}
        </p>
      )}
      <section className="space-y-1">
        <h3 className="text-sm font-medium">{t("review.summary")}</h3>
        <p className="text-sm text-muted-foreground">
          {r.summary ?? (r.summary_pending ? t("review.summaryPending") : t("review.summaryNone"))}
        </p>
      </section>
      <ReviewDiff r={r} />
      {canReview && (
        <div className="space-y-2">
          <Label htmlFor="review-comment">{t("review.comment")}</Label>
          <textarea
            id="review-comment"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            rows={3}
            maxLength={4000}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
      )}
      {canApprove && r.base_commit && (
        <Checkbox
          checked={material}
          onChange={(e) => setMaterial(e.target.checked)}
          label={t("review.material")}
          hint={t("review.materialHint")}
        />
      )}
      {error && <Alert>{error}</Alert>}
      <div className="flex flex-wrap gap-2">
        {canApprove && (
          <Button
            disabled={busy || r.stale}
            onClick={() => run(() => actions.approve.mutateAsync({ id: r.id, comment, material }), t("review.approved"))}
          >
            {t("review.approve")}
          </Button>
        )}
        {canReview && (
          <Button
            variant="outline"
            disabled={busy}
            onClick={() =>
              comment.trim()
                ? run(() => actions.requestChanges.mutateAsync({ id: r.id, comment }), t("review.changesRequested"))
                : setError(t("review.commentNeeded"))
            }
          >
            {t("review.requestChanges")}
          </Button>
        )}
        {/* Only the person who sent it can withdraw; the backend checks that. */}
        {r.self_review && (
          <Button variant="ghost" disabled={busy} onClick={() => run(() => actions.withdraw.mutateAsync(r.id), t("review.withdrawn"))}>
            {t("review.withdraw")}
          </Button>
        )}
      </div>
    </div>
  );
}

/** Review → SOP changes (frontend spec §7). */
export function Changes() {
  const reviews = useReviews();
  const [params, setParams] = useSearchParams();
  if (reviews.isPending) return <Loading />;
  if (reviews.isError) return <p role="alert" className="text-sm">{t("error.generic")}</p>;
  const list = reviews.data;
  if (list.length === 0) return <p className="text-sm text-muted-foreground">{t("review.empty.changes")}</p>;
  const selected = list.find((r) => r.id === params.get("id")) ?? null;
  return (
    <div className="grid grid-cols-[18rem_1fr] gap-6">
      <ul className="space-y-1" aria-label={t("review.tab.changes")}>
        {list.map((r) => (
          <li key={r.id}>
            <button
              type="button"
              aria-current={selected?.id === r.id}
              onClick={() => setParams((p) => (p.set("id", r.id), p), { replace: true })}
              className={cn(
                "w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-accent",
                selected?.id === r.id && "border-primary bg-accent",
              )}
            >
              <span className="block font-medium">{r.title}</span>
              <span className="block text-xs text-muted-foreground">
                {r.requested_by} · {when(r.requested_at)}
              </span>
              {r.stale && <Badge variant="warning" className="mt-1">{t("review.staleBadge")}</Badge>}
            </button>
          </li>
        ))}
      </ul>
      <div>{selected ? <Detail key={selected.id} r={selected} /> : <p className="text-sm text-muted-foreground">{t("review.pick")}</p>}</div>
    </div>
  );
}
