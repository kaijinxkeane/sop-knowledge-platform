import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { messageOf } from "@/api/errors";
import { Loading } from "@/app/routes";
import { useMe } from "@/auth/hooks";
import { PeoplePicker } from "@/components/PeoplePicker";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { t } from "@/i18n";
import type { Colleague } from "@/pages/handovers/api";
import { useDocuments } from "@/pages/library/api";
import { NotFound } from "@/pages/NotFound";
import { shortDate, useAssignableRoles } from "@/pages/reading/api";
import { departmentFolders, docsIn, stepsFromFolder } from "@/lib/pathFolders";
import { placeFor } from "@/lib/places";
import {
  canManagePaths,
  leadOf,
  useCompletion,
  useManagedPath,
  useManagedPaths,
  useMyPath,
  useMyPaths,
  usePathActions,
  type Path,
  type PathBody,
  type PathItem,
} from "./api";
import { spaceLabel } from "@/lib/spaceLabel";

function Progress({ done, total }: { done: number; total: number }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="space-y-1">
      <div
        className="h-2 rounded bg-muted"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
        aria-label={t("paths.progress", { done, total })}
      >
        <div className="h-2 rounded bg-primary" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs text-muted-foreground">{t("paths.progress", { done, total })}</p>
    </div>
  );
}

/** Paths: mine (anyone with an assignment) and, for leads and HR, the ones they manage. */
export function PathList() {
  const me = useMe();
  const mine = useMyPaths();
  const manage = canManagePaths(me.data);
  const managed = useManagedPaths(manage);
  const completion = useCompletion(manage);
  const leads = leadOf(me.data);
  if (mine.isPending) return <Loading />;
  const byPath = new Map((completion.data ?? []).map((c) => [c.path_id, c]));
  return (
    <div className="mx-auto max-w-4xl space-y-8 px-6 py-6">
      <section className="space-y-3">
        <h1 className="text-2xl font-semibold">{t("paths.title")}</h1>
        {mine.isError ? (
          <p role="alert" className="text-sm">{t("error.generic")}</p>
        ) : mine.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("paths.none")}</p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {mine.data.map((p) => (
              <li key={p.id} className="rounded-lg border p-4">
                <Link to={`/paths/${p.id}`} className="font-medium hover:underline">{p.title}</Link>
                {p.due_on && <p className="text-xs text-muted-foreground">{t("reading.due", { date: shortDate(p.due_on) })}</p>}
                <div className="mt-3"><Progress done={p.done} total={p.total} /></div>
              </li>
            ))}
          </ul>
        )}
      </section>
      {manage && (
        <section className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">{t("paths.manage")}</h2>
            {leads.length > 0 && (
              <Button asChild size="sm"><Link to="/paths/new">{t("paths.new")}</Link></Button>
            )}
          </div>
          {managed.isPending ? (
            <Loading />
          ) : (managed.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("paths.manageNone")}</p>
          ) : (
            <ul className="divide-y rounded-lg border">
              {managed.data!.map((p) => {
                const c = byPath.get(p.id);
                const finished = c ? c.people.filter((x) => x.done >= x.total).length : 0;
                const overdue = c ? c.people.filter((x) => x.overdue).length : 0;
                return (
                  <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 p-3">
                    <div>
                      <Link to={`/paths/${p.id}/edit`} className="font-medium hover:underline">{p.title}</Link>
                      <p className="text-xs text-muted-foreground">
                        {spaceLabel(p.space)} · {t("paths.items", { n: p.total })}
                        {c && ` · ${t("paths.finished", { done: finished, total: c.people.length })}`}
                      </p>
                    </div>
                    {overdue > 0 && <Badge variant="danger">{t("paths.overdue", { n: overdue })}</Badge>}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

function ItemRow({ item, next }: { item: PathItem; next: boolean }) {
  const { done } = usePathActions();
  const [error, setError] = useState<string | null>(null);
  if (!item.readable) {
    // No title, link or type: only that something is there.
    return <li className="py-2 text-sm text-muted-foreground">{t("paths.hiddenItem")}</li>;
  }
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-2">
      <div className="flex items-center gap-2">
        <span aria-hidden className={item.done ? "text-primary" : "text-muted-foreground"}>{item.done ? "✓" : "○"}</span>
        <Link to={`/library/${item.document_id}`} className="text-sm hover:underline">{item.title}</Link>
        {item.required && <Badge variant="outline">{t("paths.required")}</Badge>}
        {next && <Badge>{t("paths.nextUp")}</Badge>}
      </div>
      <div className="flex items-center gap-2">
        {!item.done && !item.required && (
          <Button
            size="sm"
            variant="outline"
            disabled={done.isPending}
            onClick={() => done.mutateAsync(item.id).catch((e) => setError(messageOf(e)))}
          >
            {t("paths.markDone")}
          </Button>
        )}
        {!item.done && item.required && <span className="text-xs text-muted-foreground">{t("paths.signOff")}</span>}
        {!item.done && (
          <Button asChild size="sm" variant="ghost">
            <Link to={`/ask?q=${encodeURIComponent(t("paths.askQuestion", { title: item.title ?? "" }))}`}>{t("paths.ask")}</Link>
          </Button>
        )}
      </div>
      {error && <Alert className="w-full">{error}</Alert>}
    </li>
  );
}

function Steps({ p }: { p: Path }) {
  return (
    <ol className="space-y-6">
      {p.steps.map((s, n) => (
        <li key={n}>
          <h2 className="font-medium">{s.title}</h2>
          <ul className="divide-y">
            {s.items.map((i) => <ItemRow key={i.id} item={i} next={i.id === p.next_item} />)}
          </ul>
        </li>
      ))}
    </ol>
  );
}

/** A learner's path: progress, "next up" and per-item Done. */
export function PathView() {
  const { id = "" } = useParams();
  const p = useMyPath(id);
  if (p.isPending) return <Loading />;
  if (p.isError) return <NotFound />;
  return (
    <div className="mx-auto max-w-3xl space-y-6 px-6 py-6">
      <Link to={placeFor("paths", "/paths")} className="text-sm text-muted-foreground hover:text-foreground">← {t("paths.title")}</Link>
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">{p.data.title}</h1>
        {p.data.description && <p className="text-sm text-muted-foreground">{p.data.description}</p>}
        {p.data.due_on && <p className="text-sm">{t("reading.due", { date: shortDate(p.data.due_on) })}</p>}
        <Progress done={p.data.done} total={p.data.total} />
        {p.data.done === p.data.total && <p role="status" className="text-sm font-medium">{t("paths.complete")}</p>}
      </header>
      <Steps p={p.data} />
    </div>
  );
}

type Draft = { title: string; items: { document_id: string; required: boolean }[] };

/** Approved notes can be required (people sign them off against a version). */
const requirable = (d: { kind: string; approved?: boolean | null } | undefined) => d?.kind === "note" && !!d.approved;

function StepEditor({
  step,
  onChange,
  onRemove,
  n,
  space,
}: {
  step: Draft;
  onChange: (s: Draft) => void;
  onRemove: () => void;
  n: number;
  space: string;
}) {
  const docs = useDocuments();
  const [q, setQ] = useState("");
  const folders = departmentFolders(docs.data ?? [], space);
  const byId = new Map((docs.data ?? []).map((d) => [d.id, d]));
  const chosen = new Set(step.items.map((i) => i.document_id));
  const matches = q.trim()
    ? (docs.data ?? []).filter((d) => !chosen.has(d.id) && d.title.toLowerCase().includes(q.trim().toLowerCase())).slice(0, 6)
    : [];
  return (
    <fieldset className="space-y-3 rounded-md border p-3">
      <legend className="px-1 text-sm font-medium">{t("paths.step", { n: n + 1 })}</legend>
      <div className="flex gap-2">
        <Input aria-label={t("paths.stepTitle")} placeholder={t("paths.stepTitle")} value={step.title} onChange={(e) => onChange({ ...step, title: e.target.value })} required />
        <Button type="button" variant="ghost" size="sm" onClick={onRemove}>{t("paths.removeStep")}</Button>
      </div>
      <ul className="space-y-1">
        {step.items.map((it, k) => {
          const d = byId.get(it.document_id);
          const canRequire = requirable(d);
          return (
            <li key={it.document_id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span>{d?.title ?? t("paths.hiddenItem")}</span>
              <span className="flex items-center gap-3">
                <label className="flex items-center gap-1 text-xs">
                  <input
                    type="checkbox"
                    checked={it.required}
                    disabled={!canRequire}
                    onChange={(e) => {
                      const items = [...step.items];
                      items[k] = { ...it, required: e.target.checked };
                      onChange({ ...step, items });
                    }}
                  />
                  {t("paths.required")}
                </label>
                <button type="button" className="text-xs underline" onClick={() => onChange({ ...step, items: step.items.filter((_, j) => j !== k) })}>
                  {t("paths.removeItem")}
                </button>
              </span>
            </li>
          );
        })}
      </ul>
      <div className="space-y-1">
        <Input aria-label={t("paths.addItem")} placeholder={t("paths.addItem")} value={q} onChange={(e) => setQ(e.target.value)} />
        {folders.length > 0 && (
          <Select
            aria-label={t("paths.addFolder")}
            value=""
            onChange={(e) => {
              const add = docsIn(docs.data ?? [], space, e.target.value).filter((d) => !chosen.has(d.id));
              onChange({ ...step, items: [...step.items, ...add.map((d) => ({ document_id: d.id, required: false }))] });
            }}
          >
            <option value="">{t("paths.addFolder")}</option>
            {folders.map((f) => <option key={f} value={f}>{f}</option>)}
          </Select>
        )}
        {matches.length > 0 && (
          <ul className="rounded-md border bg-card text-sm">
            {matches.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  className="w-full px-3 py-1.5 text-left hover:bg-muted"
                  onClick={() => {
                    onChange({ ...step, items: [...step.items, { document_id: d.id, required: false }] });
                    setQ("");
                  }}
                >
                  {d.title} <span className="text-xs text-muted-foreground">{d.doc_type}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </fieldset>
  );
}

function AssignPath({ p }: { p: Path }) {
  const roles = useAssignableRoles(true);
  const { assign } = usePathActions();
  const [people, setPeople] = useState<Colleague[]>([]);
  const [picked, setPicked] = useState("");
  const [due, setDue] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <form
      className="space-y-3 rounded-md border p-4"
      aria-label={t("paths.assign")}
      onSubmit={async (e) => {
        e.preventDefault();
        setMsg(null);
        try {
          await assign.mutateAsync({
            id: p.id,
            body: { user_ids: people.map((x) => x.id), roles: picked ? [picked] : [], due_on: due || null },
          });
          setPeople([]);
          setPicked("");
          setMsg(t("paths.assigned"));
        } catch (err) {
          setMsg(messageOf(err));
        }
      }}
    >
      <h2 className="font-medium">{t("paths.assign")}</h2>
      {p.assignments.length > 0 && (
        <p className="text-sm text-muted-foreground">
          {t("paths.assignedTo", { list: p.assignments.map((a) => a.target).join(", ") })}
        </p>
      )}
      <PeoplePicker id="path-people" label={t("reading.people")} value={people} onChange={setPeople} />
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="path-role">{t("paths.role")}</Label>
          <Select id="path-role" value={picked} onChange={(e) => setPicked(e.target.value)}>
            <option value="">—</option>
            {(roles.data ?? []).map((r) => <option key={r.name} value={r.name}>{r.name}</option>)}
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="path-due">{t("reading.dueOn")}</Label>
          <Input id="path-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
        </div>
      </div>
      {msg && <p role="status" className="text-sm">{msg}</p>}
      <Button type="submit" size="sm" disabled={assign.isPending || (!people.length && !picked)}>{t("paths.assignButton")}</Button>
    </form>
  );
}

function CompletionTable({ pathId }: { pathId: string }) {
  const c = useCompletion(true).data?.find((x) => x.path_id === pathId);
  if (!c || !c.people.length) return null;
  return (
    <section aria-label={t("paths.completion")} className="space-y-2">
      <h2 className="font-medium">{t("paths.completion")}</h2>
      <table className="w-full text-sm">
        <tbody>
          {c.people.map((x) => (
            <tr key={x.name} className="border-t">
              <td className="py-1.5">{x.name}</td>
              <td className="py-1.5">{t("paths.progress", { done: x.done, total: x.total })}</td>
              <td className="py-1.5 text-right">{x.overdue && <Badge variant="danger">{t("reading.overdueShort")}</Badge>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

const toDraft = (p: Path | undefined): Draft[] =>
  p?.steps.map((s) => ({
    title: s.title,
    items: s.items.filter((i) => i.document_id).map((i) => ({ document_id: i.document_id!, required: i.required })),
  })) ?? [{ title: t("paths.week", { n: 1 }), items: [] }];

/** A lead builds or edits a path; HR can assign and see completion. */
export function PathEditor() {
  const { id } = useParams();
  const existing = useManagedPath(id);
  if (id && existing.isPending) return <Loading />;
  if (id && existing.isError) return <NotFound />;
  return <EditorForm key={existing.data?.id ?? "new"} p={existing.data} />;
}

function FromFolder({ space, onSteps }: { space: string; onSteps: (s: Draft[]) => void }) {
  const docs = useDocuments();
  const folders = departmentFolders(docs.data ?? [], space);
  if (!folders.length) return null;
  return (
    <div className="space-y-1">
      <Label htmlFor="path-from-folder">{t("paths.fromFolder")}</Label>
      <Select
        id="path-from-folder"
        value=""
        onChange={(e) => {
          const steps = stepsFromFolder(docs.data ?? [], space, e.target.value);
          if (steps.length) {
            onSteps(steps.map((s) => ({ title: s.title, items: s.docs.map((d) => ({ document_id: d.id, required: false })) })));
          }
        }}
      >
        <option value="">{t("paths.fromFolderPick")}</option>
        {folders.map((f) => <option key={f} value={f}>{f}</option>)}
      </Select>
      <p className="text-xs text-muted-foreground">{t("paths.fromFolderExplain")}</p>
    </div>
  );
}

function EditorForm({ p }: { p: Path | undefined }) {
  const me = useMe();
  const navigate = useNavigate();
  const { create, update, remove } = usePathActions();
  const leads = leadOf(me.data);
  const [space, setSpace] = useState(p?.space ?? leads[0] ?? "");
  const [title, setTitle] = useState(p?.title ?? "");
  const [description, setDescription] = useState(p?.description ?? "");
  const [steps, setSteps] = useState<Draft[]>(toDraft(p));
  const [error, setError] = useState<string | null>(null);
  const editable = !p || p.can_edit;
  const hiddenCount = p ? p.total - steps.reduce((n, s) => n + s.items.length, 0) : 0;

  const save = async () => {
    setError(null);
    const body: PathBody = { space, title, description, steps };
    try {
      const out = p ? await update.mutateAsync({ id: p.id, body }) : await create.mutateAsync(body);
      if (!p) navigate(`/paths/${out.id}/edit`, { replace: true });
    } catch (e) {
      setError(messageOf(e));
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-6 py-6">
      <Link to={placeFor("paths", "/paths")} className="text-sm text-muted-foreground hover:text-foreground">← {t("paths.title")}</Link>
      <h1 className="text-2xl font-semibold">{p ? p.title : t("paths.new")}</h1>
      {editable ? (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
            <div className="space-y-1">
              <Label htmlFor="path-title">{t("paths.name")}</Label>
              <Input id="path-title" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={200} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="path-space">{t("labels.space")}</Label>
              <Select id="path-space" value={space} disabled={!!p} onChange={(e) => setSpace(e.target.value)}>
                {(p ? [p.space] : leads).map((s) => <option key={s} value={s}>{spaceLabel(s)}</option>)}
              </Select>
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="path-desc">{t("paths.description")}</Label>
            <textarea
              id="path-desc"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              rows={2}
              maxLength={2000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          {hiddenCount > 0 && <Alert>{t("paths.hiddenOnEdit", { n: hiddenCount })}</Alert>}
          {!p && <FromFolder space={space} onSteps={setSteps} />}
          {steps.map((s, n) => (
            <StepEditor
              key={n}
              n={n}
              step={s}
              onChange={(next) => setSteps(steps.map((x, j) => (j === n ? next : x)))}
              onRemove={() => setSteps(steps.filter((_, j) => j !== n))}
              space={space}
            />
          ))}
          <Button type="button" variant="outline" size="sm" onClick={() => setSteps([...steps, { title: t("paths.week", { n: steps.length + 1 }), items: [] }])}>
            {t("paths.addStep")}
          </Button>
          {error && <Alert>{error}</Alert>}
          <div className="flex gap-2">
            <Button type="submit" disabled={create.isPending || update.isPending || !space}>{t("common.save")}</Button>
            {p && (
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  if (window.confirm(t("paths.deleteConfirm"))) remove.mutateAsync(p.id).then(() => navigate("/paths"));
                }}
              >
                {t("paths.delete")}
              </Button>
            )}
          </div>
        </form>
      ) : (
        p && (
          <ol className="space-y-4">
            {p.steps.map((st, n) => (
              <li key={n}>
                <h2 className="font-medium">{st.title}</h2>
                <ul className="text-sm">
                  {st.items.map((i) => (
                    <li key={i.id} className="py-1 text-muted-foreground">
                      {i.readable ? i.title : t("paths.hiddenItem")}
                      {i.required && ` · ${t("paths.required")}`}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        )
      )}
      {p && <AssignPath p={p} />}
      {p && <CompletionTable pathId={p.id} />}
    </div>
  );
}
