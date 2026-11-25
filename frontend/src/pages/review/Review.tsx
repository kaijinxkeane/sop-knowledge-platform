import { useSearchParams } from "react-router";
import { useMe } from "@/auth/hooks";
import { t, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";
import { countQueue, useQueue, useReviews } from "./api";
import { Changes } from "./Changes";
import { Governance } from "./Governance";
import { LabelQueue } from "./Labels";

type Tab = "changes" | "labels" | "unplaced" | "governance";

/** Review (frontend spec §7). Tabs are cosmetic: every list is filtered by the backend. */
export default function Review() {
  const me = useMe();
  const reviews = useReviews();
  const queue = useQueue();
  const [params, setParams] = useSearchParams();
  const actions = new Set(Object.values(me.data?.space_actions ?? {}).flat());
  const governance = actions.has("approve") || (me.data?.global_actions ?? []).includes("view_audit");
  const tabs: Tab[] = ["changes", "labels", "unplaced", ...(governance ? (["governance"] as const) : [])];
  const asked = params.get("tab") as Tab | null;
  const tab: Tab = asked && tabs.includes(asked) ? asked : "changes";
  const counts: Partial<Record<Tab, number | undefined>> = {
    changes: reviews.data?.length,
    labels: queue.data && countQueue(queue.data, false),
    unplaced: queue.data && countQueue(queue.data, true),
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-6 py-6">
      <h1 className="text-2xl font-semibold">{t("review.title")}</h1>
      <div role="tablist" aria-label={t("review.tabs")} className="flex gap-1 border-b">
        {tabs.map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            onClick={() => setParams({ tab: k }, { replace: true })}
            className={cn(
              "-mb-px border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground hover:text-foreground",
              tab === k && "border-primary font-medium text-foreground",
            )}
          >
            {t(`review.tab.${k}` as MessageKey)}
            {counts[k] ? <span className="ml-1.5 rounded-full bg-muted px-1.5 text-xs">{counts[k]}</span> : null}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === "changes" && <Changes />}
        {tab === "labels" && <LabelQueue unplaced={false} />}
        {tab === "unplaced" && <LabelQueue unplaced />}
        {tab === "governance" && <Governance />}
      </div>
    </div>
  );
}
