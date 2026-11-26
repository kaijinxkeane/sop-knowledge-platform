import { useState } from "react";
import { Link } from "react-router";
import { messageOf } from "@/api/errors";
import { Loading } from "@/app/routes";
import { useMe } from "@/auth/hooks";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { t, type MessageKey } from "@/i18n";
import { en } from "@/i18n/en";
import { cn } from "@/lib/utils";
import {
  leadSpaces,
  TOPIC_STATUSES,
  useBusFactor,
  useConflicts,
  useCoverage,
  useFolderCoverage,
  useHrGaps,
  useRetainActions,
  useSpaceGaps,
  useStale,
  type Topic,
} from "./api";
import { spaceLabel } from "@/lib/spaceLabel";
import { TIME_ZONE } from "@/lib/dates";

const day = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString([], { timeZone: TIME_ZONE, dateStyle: "medium" }) : "";

const known = (key: string): key is MessageKey => key in en;

function Failed() {
  return <p role="alert" className="text-sm">{t("error.generic")}</p>;
}

export function SpacePicker({ spaces, value, onChange, id }: { spaces: string[]; value: string; onChange: (s: string) => void; id: string }) {
  if (spaces.length < 2) return null;
  return (
    <div className="w-56 space-y-1">
      <Label htmlFor={id}>{t("retain.space")}</Label>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {spaces.map((s) => <option key={s} value={s}>{spaceLabel(s)}</option>)}
      </Select>
    </div>
  );
}

function StatusSelect({ id, value, enabled }: { id: string; value: string; enabled: boolean }) {
  const { setStatus } = useRetainActions();
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="space-y-1">
      <Label htmlFor={`status-${id}`} className="text-xs">{t("gaps.status")}</Label>
      <Select
        id={`status-${id}`}
        className="h-8 w-44"
        value={value}
        disabled={!enabled || setStatus.isPending}
        onChange={async (e) => {
          setError(null);
          try {
            await setStatus.mutateAsync({ id, status: e.target.value });
          } catch (err) {
            setError(messageOf(err));
          }
        }}
      >
        {TOPIC_STATUSES.map((s) => <option key={s} value={s}>{t(`topic.${s}` as MessageKey)}</option>)}
      </Select>
      {error && <Alert>{error}</Alert>}
    </div>
  );
}

function TopicCard({ topic, canSet }: { topic: Topic; canSet: boolean }) {
  const reasons = Object.entries(topic.reasons ?? {})
    .map(([k, n]) => `${n} ${known(`gaps.reason.${k}`) ? t(`gaps.reason.${k}` as MessageKey) : k}`)
    .join(" · ");
  const draft = new URLSearchParams({ title: topic.label });
  if (topic.programme) draft.set("programme", topic.programme);
  if (topic.stage) draft.set("stage", topic.stage);
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4 space-y-0 pb-3">
        <div className="space-y-1">
          <h3 className="font-semibold">{topic.label}</h3>
          {(topic.programme || topic.stage) && (
            <p className="text-xs text-muted-foreground">{[topic.programme, topic.stage].filter(Boolean).join(" · ")}</p>
          )}
          <p className="text-sm text-muted-foreground">
            {t("gaps.counts", { questions: topic.questions, people: topic.people, recent: topic.last_30_days })}
          </p>
          {reasons && <p className="text-xs text-muted-foreground">{reasons}</p>}
        </div>
        <StatusSelect id={topic.id} value={topic.status} enabled={canSet} />
      </CardHeader>
      <CardContent className="space-y-3">
        {topic.access_gap && (
          <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
            <Link to={`/library/${topic.access_gap.document_id}`} className="underline">
              {t("gaps.accessGap", { title: topic.access_gap.title })}
            </Link>
          </p>
        )}
        {topic.examples.length > 0 && (
          <div>
            <p className="text-sm font-medium">{t("gaps.examples")}</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm">
              {topic.examples.map((q, i) => <li key={i}>{q}</li>)}
            </ul>
          </div>
        )}
        <Button asChild size="sm" variant="outline">
          <Link to={`/write/new?${draft.toString()}`}>{t("gaps.draft")}</Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function LeadGaps({ spaces }: { spaces: string[] }) {
  const me = useMe();
  const [space, setSpace] = useState(spaces[0] ?? "");
  const gaps = useSpaceGaps(space || null);
  const canSet = !!me.data?.space_actions[space]?.includes("approve") || !!me.data?.global_actions.includes("view_gap_reports");
  return (
    <section className="space-y-3">
      <div className="flex items-end justify-between gap-4">
        <h2 className="text-lg font-semibold">{t("gaps.lead")}</h2>
        <SpacePicker id="gaps-space" spaces={spaces} value={space} onChange={setSpace} />
      </div>
      {gaps.isPending ? <Loading /> : gaps.isError ? <Failed /> : gaps.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("gaps.empty")}</p>
      ) : (
        <div className="space-y-3">{gaps.data.map((g) => <TopicCard key={g.id} topic={g} canSet={canSet} />)}</div>
      )}
    </section>
  );
}

function HrGaps() {
  const gaps = useHrGaps(true);
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">{t("gaps.hr")}</h2>
      {gaps.isPending ? <Loading /> : gaps.isError ? <Failed /> : gaps.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("gaps.empty")}</p>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">{t("retain.tab.gaps")}</th>
                <th className="px-3 py-2 font-medium">{t("retain.space")}</th>
                <th className="px-3 py-2 font-medium">{t("gaps.byRole")}</th>
                <th className="px-3 py-2 font-medium">{t("gaps.status")}</th>
              </tr>
            </thead>
            <tbody>
              {gaps.data.map((g) => (
                <tr key={g.id} className="border-t align-top">
                  <td className="px-3 py-2">
                    <p className="font-medium">{g.label}</p>
                    <p className="text-xs text-muted-foreground">
                      {t("gaps.hrCounts", { questions: g.questions, people: g.people })}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {g.before_addressed_30d != null && g.after_addressed_30d != null
                        ? t("gaps.trend", { before: g.before_addressed_30d, after: g.after_addressed_30d })
                        : t("gaps.trendNone")}
                    </p>
                  </td>
                  <td className="px-3 py-2">{spaceLabel(g.space)}</td>
                  <td className="px-3 py-2 text-xs">
                    {Object.entries(g.by_role ?? {}).map(([role, n]) => <div key={role}>{role}: {String(n)}</div>)}
                  </td>
                  <td className="px-3 py-2"><StatusSelect id={g.id} value={g.status} enabled /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** Gaps: leads see their space with anonymous examples; HR sees counts only. */
export function Gaps() {
  const me = useMe();
  const spaces = leadSpaces(me.data?.space_actions);
  const hr = !!me.data?.global_actions.includes("view_gap_reports");
  return (
    <div className="space-y-8">
      {spaces.length > 0 && <LeadGaps spaces={spaces} />}
      {hr && <HrGaps />}
    </div>
  );
}

export function Coverage() {
  const cov = useCoverage();
  const [open, setOpen] = useState<string | null>(null);
  if (cov.isPending) return <Loading />;
  if (cov.isError) return <Failed />;
  const cells = cov.data;
  if (cells.length === 0)
    return (
      <div className="space-y-6">
        <p className="text-sm text-muted-foreground">{t("coverage.empty")}</p>
        <FolderCoverage />
      </div>
    );
  const programmes = [...new Set(cells.map((c) => c.programme))].sort();
  const stages = [...new Set(cells.map((c) => c.stage))];
  const at = new Map(cells.map((c) => [`${c.programme}|${c.stage}`, c]));
  const selected = open ? at.get(open) : undefined;
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">{t("coverage.title")}</h2>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">{t("coverage.programme")}</th>
              {stages.map((s) => <th key={s} className="px-3 py-2 font-medium">{s}</th>)}
            </tr>
          </thead>
          <tbody>
            {programmes.map((p) => (
              <tr key={p} className="border-t">
                <th scope="row" className="px-3 py-2 text-left font-medium">{p}</th>
                {stages.map((s) => {
                  const c = at.get(`${p}|${s}`);
                  const key = `${p}|${s}`;
                  const empty = !c || c.published === 0;
                  return (
                    <td key={s} className="p-1">
                      <button
                        type="button"
                        onClick={() => setOpen(open === key ? null : key)}
                        aria-pressed={open === key}
                        className={cn(
                          "w-full rounded px-2 py-2 text-left hover:ring-1 hover:ring-ring",
                          empty ? "bg-red-50 text-red-900" : c!.stale ? "bg-amber-50" : "bg-green-50",
                        )}
                      >
                        <span className="block">{empty ? t("coverage.none") : t("coverage.cell", { published: c!.published })}</span>
                        {!!c?.stale && <span className="block text-xs">{t("coverage.stale", { n: c.stale })}</span>}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {open && (
        <Card>
          <CardHeader className="pb-2">
            <h3 className="font-semibold">{t("coverage.titles", { programme: open.split("|")[0]!, stage: open.split("|")[1]! })}</h3>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* Titles only for leads; HR gets counts (the backend leaves titles out). */}
            {selected?.titles?.length ? (
              <ul className="list-disc pl-5 text-sm">{selected.titles.map((x) => <li key={x}>{x}</li>)}</ul>
            ) : null}
            <Button asChild size="sm" variant="outline">
              <Link to={`/write/new?${new URLSearchParams({ programme: open.split("|")[0]!, stage: open.split("|")[1]! })}`}>
                {t("coverage.create")}
              </Link>
            </Button>
          </CardContent>
        </Card>
      )}
      <FolderCoverage />
    </div>
  );
}

/** A lead's department, folder by folder (counts only). */
function FolderCoverage() {
  const me = useMe();
  const spaces = leadSpaces(me.data?.space_actions);
  const [space, setSpace] = useState(spaces[0] ?? "");
  const rows = useFolderCoverage(space || null);
  if (!spaces.length) return null;
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t("coverage.byFolder")}</h2>
          <p className="text-sm text-muted-foreground">{t("coverage.byFolderExplain")}</p>
        </div>
        {spaces.length > 1 && <SpacePicker id="folder-cov-space" spaces={spaces} value={space} onChange={setSpace} />}
      </div>
      {rows.isPending ? <Loading /> : rows.isError ? <Failed /> : rows.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("coverage.noFolders")}</p>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">{t("coverage.folder")}</th>
                <th className="px-3 py-2 font-medium">{t("coverage.documents")}</th>
                <th className="px-3 py-2 font-medium">{t("coverage.approved")}</th>
                <th className="px-3 py-2 font-medium">{t("coverage.overdue")}</th>
                <th className="px-3 py-2 font-medium">{t("coverage.openGaps")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.data.map((r) => (
                <tr key={r.folder} className="border-t">
                  <th scope="row" className="px-3 py-2 text-left font-medium">
                    <Link
                      to={`/library?${new URLSearchParams({ view: "folders", group: space, folder: r.folder })}`}
                      className="hover:underline"
                    >
                      {r.folder}
                    </Link>
                  </th>
                  <td className="px-3 py-2">{r.documents}</td>
                  <td className={cn("px-3 py-2", r.approved < r.documents && "text-amber-900")}>{r.approved}</td>
                  <td className={cn("px-3 py-2", r.stale > 0 && "text-amber-900")}>{r.stale}</td>
                  <td className={cn("px-3 py-2", r.open_gaps > 0 && "font-medium text-red-900")}>
                    {r.open_gaps > 0 ? t("coverage.gapsCell", { n: r.open_gaps, q: r.gap_questions }) : "0"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function Due() {
  const me = useMe();
  const spaces = leadSpaces(me.data?.space_actions);
  const [space, setSpace] = useState(spaces[0] ?? "");
  const [days, setDays] = useState(30);
  const stale = useStale(space || null, days);
  return (
    <div className="space-y-4">
      <div className="flex items-end gap-4">
        <SpacePicker id="due-space" spaces={spaces} value={space} onChange={setSpace} />
        <div className="w-40 space-y-1">
          <Label htmlFor="due-days">{t("due.within")}</Label>
          <Select id="due-days" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[0, 30, 60, 90].map((n) => <option key={n} value={n}>{t("due.days", { n })}</option>)}
          </Select>
        </div>
      </div>
      {stale.isPending ? <Loading /> : stale.isError ? <Failed /> : stale.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("due.empty")}</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {stale.data.map((d) => (
            <li key={d.document_id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
              <Link to={`/library/${d.document_id}`} className="font-medium hover:underline">{d.title}</Link>
              <span className="flex items-center gap-2 text-xs text-muted-foreground">
                {t("due.dueOn", { date: day(d.review_due) })}
                {d.approved_on && <> · {t("due.approvedOn", { date: day(d.approved_on) })}</>}
                {d.overdue && <Badge variant="danger">{t("due.overdue")}</Badge>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function BusFactorReport() {
  const bus = useBusFactor(true);
  if (bus.isPending) return <Loading />;
  if (bus.isError) return <Failed />;
  const { single_author, leaving } = bus.data;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader className="pb-3"><h2 className="font-semibold">{t("bus.single")} ({single_author.length})</h2></CardHeader>
        <CardContent>
          {single_author.length === 0 ? <p className="text-sm text-muted-foreground">{t("bus.singleEmpty")}</p> : (
            <ul className="space-y-1">
              {single_author.map((d) => (
                <li key={d.document_id} className="flex items-baseline justify-between gap-3 text-sm">
                  <Link to={`/library/${d.document_id}`} className="hover:underline">{d.title}</Link>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {t("bus.onlyAuthor", { name: d.only_author })}
                    {d.author_leaving_on && <> · <span className="text-destructive">{t("bus.leavingOn", { date: day(d.author_leaving_on) })}</span></>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-3"><h2 className="font-semibold">{t("bus.leaving")} ({leaving.length})</h2></CardHeader>
        <CardContent>
          {leaving.length === 0 ? <p className="text-sm text-muted-foreground">{t("bus.leavingEmpty")}</p> : (
            <ul className="space-y-1 text-sm">
              {leaving.map((p) => (
                <li key={p.name}>{t("bus.leavingLine", { name: p.name, date: day(p.leaving_on), owner: p.owner_of, sole: p.sole_author_of })}</li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function Conflicts() {
  const list = useConflicts();
  const { dismiss } = useRetainActions();
  const [error, setError] = useState<string | null>(null);
  if (list.isPending) return <Loading />;
  if (list.isError) return <Failed />;
  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold">{t("conflicts.title")}</h2>
      {error && <Alert>{error}</Alert>}
      {list.data.length === 0 ? <p className="text-sm text-muted-foreground">{t("conflicts.empty")}</p> : (
        list.data.map((c) => (
          <Card key={c.id}>
            <CardContent className="space-y-2 pt-6">
              <p className="text-sm">
                <Link to={`/library/${c.document_a}`} className="font-medium underline">{c.title_a}</Link>
                {" ↔ "}
                <Link to={`/library/${c.document_b}`} className="font-medium underline">{c.title_b}</Link>
                <span className="ml-2 text-xs text-muted-foreground">{t("conflicts.found", { date: day(c.created_at) })}</span>
              </p>
              <p className="whitespace-pre-wrap text-sm text-muted-foreground">{c.explanation}</p>
              <Button
                size="sm"
                variant="outline"
                disabled={dismiss.isPending}
                onClick={async () => {
                  setError(null);
                  try {
                    await dismiss.mutateAsync(c.id);
                  } catch (e) {
                    setError(messageOf(e));
                  }
                }}
              >
                {t("conflicts.dismiss")}
              </Button>
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}
