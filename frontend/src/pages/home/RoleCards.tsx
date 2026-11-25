import type { ReactNode } from "react";
import { Link } from "react-router";
import { useMe } from "@/auth/hooks";
import { t } from "@/i18n";
import { usd, useUsage } from "@/pages/admin/usageApi";
import { useHandovers } from "@/pages/handovers/api";
import { useMyPaths } from "@/pages/paths/api";
import { shortDate, useMyReading } from "@/pages/reading/api";
import { leadSpaces, useCoverage, useHrGaps, useStaleAll } from "@/pages/retain/api";
import { countQueue, useQueue } from "@/pages/review/api";

export function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="rounded-lg border p-4 text-left">
      <h2 className="text-xs font-medium uppercase text-muted-foreground">{title}</h2>
      <div className="mt-2">{children}</div>
    </section>
  );
}

/** Handovers sent to me and not yet acknowledged: every role can receive one. */
export function HandoverCard() {
  const me = useMe();
  const list = useHandovers();
  const mine = (list.data ?? []).filter(
    (h) => h.status !== "draft" && h.receivers.some((r) => r.user_id === me.data?.id && !r.acknowledged_at),
  );
  if (!mine.length) return null;
  return (
    <Card title={t("home.handovers")}>
      <ul className="space-y-1 text-sm">
        {mine.slice(0, 5).map((h) => (
          <li key={h.id} className="flex items-baseline justify-between gap-2">
            <Link className="truncate hover:underline" to={`/handovers/${h.id}`}>{h.title}</Link>
            <span className="shrink-0 text-xs text-muted-foreground">{t("home.handoverFrom", { name: h.author })}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** Must-read SOPs not yet acknowledged (or to re-read after a material change). */
export function ReadingCard() {
  const mine = useMyReading();
  const todo = (mine.data ?? []).filter((r) => !r.acknowledged_at);
  if (!todo.length) return null;
  return (
    <Card title={t("home.reading")}>
      <ul className="space-y-1 text-sm">
        {todo.slice(0, 5).map((r) => (
          <li key={r.document_id} className="flex items-baseline justify-between gap-2">
            <Link className="truncate hover:underline" to={`/library/${r.document_id}`}>{r.title}</Link>
            <span className={r.overdue ? "shrink-0 text-xs font-medium text-amber-900" : "shrink-0 text-xs text-muted-foreground"}>
              {r.reread
                ? t("home.readingReread")
                : r.due_on
                  ? t(r.overdue ? "reading.overdue" : "reading.due", { date: shortDate(r.due_on) })
                  : ""}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** My onboarding paths that aren't finished, with the next item to open. */
export function PathCard() {
  const paths = useMyPaths();
  const open = (paths.data ?? []).filter((p) => p.done < p.total);
  if (!open.length) return null;
  return (
    <Card title={t("home.paths")}>
      <ul className="space-y-2 text-sm">
        {open.slice(0, 3).map((p) => {
          const next = p.steps.flatMap((s) => s.items).find((i) => i.id === p.next_item);
          return (
            <li key={p.id}>
              <Link className="font-medium hover:underline" to={`/paths/${p.id}`}>{p.title}</Link>
              <span className="ml-2 text-xs text-muted-foreground">{t("paths.progress", { done: p.done, total: p.total })}</span>
              {next?.document_id && (
                <p className="text-xs">
                  {t("paths.nextUp")}:{" "}
                  <Link className="underline" to={`/library/${next.document_id}`}>{next.title}</Link>
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/** CEO, leads and HR (frontend spec §3): unplaced notes, review due, coverage, top gaps. */
export function RoleCards() {
  const me = useMe();
  const reviewer = leadSpaces(me.data?.space_actions);
  const lead = leadSpaces(me.data?.space_actions, "approve");
  const hr = !!me.data?.global_actions.includes("view_gap_reports");
  const queue = useQueue(reviewer.length > 0);
  const stale = useStaleAll(reviewer);
  const coverage = useCoverage(lead.length > 0 || hr);
  const gaps = useHrGaps(hr);
  const admin = !!me.data?.global_actions.some((a) => a === "manage_users" || a === "view_audit");
  const usage = useUsage(null, admin);

  const unplaced = countQueue(queue.data, true);
  const due = stale.data ?? [];
  const overdue = due.filter((d) => d.overdue).length;
  const cells = coverage.data ?? [];
  const covered = cells.filter((c) => c.published > 0).length;
  const staleCells = cells.filter((c) => c.stale > 0).length;
  const topGaps = [...(gaps.data ?? [])].filter((g) => g.status !== "addressed").sort((a, b) => b.people - a.people).slice(0, 3);

  return (
    <>
      {usage.data && (
        <Card title={t("home.cost")}>
          <Link className="text-2xl font-semibold tabular-nums hover:underline" to="/admin/usage">
            {usd(usage.data.total_cost_usd)}
          </Link>
          <p className="text-xs text-muted-foreground">
            {t("home.costLine", { cloud: usage.data.cloud_calls, local: usage.data.local_calls })}
          </p>
        </Card>
      )}
      {unplaced > 0 && (
        <Card title={t("home.unplaced")}>
          <Link className="text-sm underline underline-offset-2" to="/review?tab=unplaced">{t("home.unplacedCount", { n: unplaced })}</Link>
        </Card>
      )}
      {due.length > 0 && (
        <Card title={t("home.due")}>
          <ul className="space-y-1 text-sm">
            {due.slice(0, 4).map((d) => (
              <li key={d.document_id} className="flex items-baseline justify-between gap-2">
                <Link className="truncate hover:underline" to={`/library/${d.document_id}`}>{d.title}</Link>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {new Date(d.review_due).toLocaleDateString([], { day: "numeric", month: "short" })}
                </span>
              </li>
            ))}
          </ul>
          <Link className="mt-2 block text-xs text-muted-foreground underline" to="/retain?tab=due">
            {overdue > 0 ? t("home.dueOverdue", { n: overdue }) : t("retain.tab.due")} →
          </Link>
        </Card>
      )}
      {cells.length > 0 && (
        <Card title={t("home.coverage")}>
          <Link className="text-sm underline underline-offset-2" to="/retain?tab=coverage">
            {t("home.coverageLine", { covered, total: cells.length })}
          </Link>
          {staleCells > 0 && <p className="text-xs text-muted-foreground">{t("home.coverageStale", { n: staleCells })}</p>}
        </Card>
      )}
      {topGaps.length > 0 && (
        <Card title={t("home.hrGaps")}>
          <ul className="space-y-1 text-sm">
            {topGaps.map((g) => (
              <li key={g.id} className="flex items-baseline justify-between gap-2">
                <Link className="truncate hover:underline" to="/retain?tab=gaps">{g.label}</Link>
                <span className="shrink-0 text-xs text-muted-foreground">{t("home.hrGapLine", { people: g.people })}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
