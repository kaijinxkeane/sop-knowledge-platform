import { useState } from "react";
import { Link } from "react-router";
import { messageOf } from "@/api/errors";
import { useMe } from "@/auth/hooks";
import { visibleSections } from "@/auth/permissions";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { plainName } from "@/lib/obsidian";
import { useBookmarks } from "@/pages/library/api";
import { BookmarkList } from "@/pages/library/Bookmarks";
import { requestSop } from "@/pages/ask/api";
import { useMyGaps, useRecent, useWaiting } from "./api";
import { Card, HandoverCard, PathCard, ReadingCard, RoleCards } from "./RoleCards";

type Gap = NonNullable<ReturnType<typeof useMyGaps>["data"]>[number];

function GapRow({ gap, canWrite }: { gap: Gap; canWrite: boolean }) {
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [experts, setExperts] = useState(false);
  return (
    <li className="space-y-1">
      <div className="text-sm">
        {gap.label} <span className="text-xs text-muted-foreground">({t("home.times", { n: gap.count })})</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {gap.space && (
          <Button
            size="sm"
            variant="outline"
            disabled={sent}
            onClick={() =>
              requestSop(gap.key, gap.space!)
                .then(() => setSent(true))
                .catch((e) => setError(messageOf(e)))
            }
          >
            {sent ? t("ask.requested") : t("ask.requestSop")}
          </Button>
        )}
        {canWrite && (
          <Button asChild size="sm" variant="outline">
            <Link
              to={`/write/new?title=${encodeURIComponent(gap.label.slice(0, 150))}${gap.programme ? `&programme=${encodeURIComponent(gap.programme)}` : ""}${gap.stage ? `&stage=${encodeURIComponent(gap.stage)}` : ""}`}
            >
              {t("ask.startDraft")}
            </Link>
          </Button>
        )}
        <Button size="sm" variant="outline" onClick={() => setExperts(true)}>
          {t("ask.suggestExpert")}
        </Button>
      </div>
      {experts && (
        <p role="status" className="text-xs text-muted-foreground">
          {gap.experts.length ? t("ask.experts", { names: gap.experts.join(", ") }) : t("ask.noExperts")}
        </p>
      )}
      {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    </li>
  );
}

/** Home cards (frontend spec §3). A card appears only when it has something in it. */
export function HomeCards() {
  const me = useMe();
  const sections = me.data ? visibleSections(me.data) : [];
  const canWrite = sections.includes("write");
  const gaps = useMyGaps();
  const waiting = useWaiting();
  const recent = useRecent();
  const marks = useBookmarks();
  const w = waiting.data;
  const waitingItems = w
    ? (
        [
          ["home.waiting.reviews", w.reviews, "/review?tab=changes"],
          ["home.waiting.drafts", w.drafts, "/write"],
          ["home.waiting.labels", w.labels, "/review?tab=labels"],
        ] as const
      ).filter(([, n]) => n > 0)
    : [];
  return (
    <div className="mx-auto mt-12 grid max-w-4xl gap-4 sm:grid-cols-2">
      <ReadingCard />
      <PathCard />
      <HandoverCard />
      {!!gaps.data?.length && (
        <Card title={t("home.gaps")}>
          <ul className="space-y-3">
            {gaps.data.slice(0, 3).map((g) => (
              <GapRow key={g.key} gap={g} canWrite={canWrite} />
            ))}
          </ul>
        </Card>
      )}
      {waitingItems.length > 0 && (
        <Card title={t("home.waiting")}>
          <ul className="space-y-1 text-sm">
            {waitingItems.map(([key, n, to]) => (
              <li key={key}>
                <Link className="underline underline-offset-2" to={to}>
                  {t(key, { n })}
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <RoleCards />
      {!!recent.data?.length && (
        <Card title={t("home.recent")}>
          <ul className="space-y-1 text-sm">
            {recent.data.map((d) => (
              <li key={d.id} className="flex items-baseline justify-between gap-2">
                <Link className="truncate hover:underline" to={`/library/${d.id}`}>
                  {d.title}
                </Link>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {[plainName(d.programme), new Date(d.approved_at).toLocaleDateString([], { day: "numeric", month: "short" })]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {!!marks.data?.length && (
        <div className="rounded-lg border p-4 text-left">
          <BookmarkList limit={6} />
        </div>
      )}
    </div>
  );
}
