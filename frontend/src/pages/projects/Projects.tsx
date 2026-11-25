import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { messageOf } from "@/api/errors";
import { Loading } from "@/app/routes";
import { useMe } from "@/auth/hooks";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { PeoplePicker } from "@/components/PeoplePicker";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { t, type MessageKey } from "@/i18n";
import { en } from "@/i18n/en";
import type { Colleague } from "@/pages/handovers/api";
import { useDocuments } from "@/pages/library/api";
import { NotFound } from "@/pages/NotFound";
import { useSpaces } from "@/pages/review/api";
import { useProject, useProjectActions, useProjects, useShareRequests, type Project, type ShareRequest } from "./api";

const day = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString([], { dateStyle: "medium" }) : "");
const tomorrow = () => new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
const label = (key: string, fallback: string) => (key in en ? t(key as MessageKey) : fallback);
const level = (s: string) => label(`sensitivity.${s}`, s);

function useLeadSpaces() {
  const me = useMe();
  return Object.entries(me.data?.space_actions ?? {})
    .filter(([, a]) => a.includes("approve"))
    .map(([s]) => s);
}

function Status({ p }: { p: Project }) {
  return p.active ? (
    <Badge variant={p.days_left <= 14 ? "warning" : "default"}>{t("project.daysLeft", { n: p.days_left })}</Badge>
  ) : (
    <Badge variant="outline">{t("project.ended")}</Badge>
  );
}

/** A department lead decides what (if anything) a project may read. */
function ApproveShare({ r }: { r: ShareRequest }) {
  const docs = useDocuments();
  const { approve, decline, revoke } = useProjectActions();
  const [scope, setScope] = useState<"space" | "selected">("space");
  const [max, setMax] = useState("internal");
  const [folders, setFolders] = useState<string[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const inSpace = (docs.data ?? []).filter((d) => d.access.some((a) => a.space === r.space));
  const folderList = [...new Set(inSpace.map((d) => d.vault_path.split("/").slice(0, -1).join("/")).filter(Boolean))].sort();
  const sops = inSpace.filter((d) => d.kind === "note");
  const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(messageOf(e));
    }
  };
  return (
    <li className="space-y-3 border-t pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{r.space}</span>
        <span>{t("project.requestLine", { project: r.project, lead: r.project_lead, members: r.members, date: day(r.ends_on) })}</span>
        <Badge variant="outline">{label(`project.share.status.${r.status}`, r.status)}</Badge>
        {r.renewal_requested && <Badge variant="warning">{t("project.renewalAsked")}</Badge>}
      </div>
      {r.note && <p className="whitespace-pre-wrap text-sm text-muted-foreground">{r.note}</p>}
      {(r.status === "requested" || r.renewal_requested) && (
        <form
          className="space-y-3 rounded-md border bg-muted/30 p-3"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            if (scope === "selected" && !folders.length && !picked.length) return setError(t("project.pickSome"));
            void run(() => approve.mutateAsync({ id: r.id, body: { scope, max_sensitivity: max, folders, document_ids: picked } }));
          }}
        >
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor={`scope-${r.id}`}>{t("project.scope")}</Label>
              <Select id={`scope-${r.id}`} value={scope} onChange={(e) => setScope(e.target.value as "space" | "selected")}>
                <option value="space">{t("project.scope.space")}</option>
                <option value="selected">{t("project.scope.selected")}</option>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor={`max-${r.id}`}>{t("project.level")}</Label>
              <Select id={`max-${r.id}`} value={max} onChange={(e) => setMax(e.target.value)}>
                {["public", "internal", "restricted"].map((s) => <option key={s} value={s}>{level(s)}</option>)}
              </Select>
              <p className="text-xs text-muted-foreground">{t("project.levelHint")}</p>
            </div>
          </div>
          {scope === "selected" && (
            <div className="grid grid-cols-2 gap-4">
              <fieldset className="space-y-1">
                <legend className="text-sm font-medium">{t("project.folders")}</legend>
                {folderList.map((f) => (
                  <Checkbox key={f} label={f} checked={folders.includes(f)} onChange={() => setFolders(toggle(folders, f))} />
                ))}
              </fieldset>
              <fieldset className="max-h-64 space-y-1 overflow-y-auto">
                <legend className="text-sm font-medium">{t("project.sops")}</legend>
                {sops.map((d) => (
                  <Checkbox key={d.id} label={d.title} checked={picked.includes(d.id)} onChange={() => setPicked(toggle(picked, d.id))} />
                ))}
              </fieldset>
            </div>
          )}
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={approve.isPending}>{t("project.approve")}</Button>
            <Button type="button" size="sm" variant="ghost" disabled={decline.isPending} onClick={() => run(() => decline.mutateAsync(r.id))}>
              {t("project.decline")}
            </Button>
          </div>
        </form>
      )}
      {r.status === "approved" && !r.renewal_requested && (
        <ConfirmDialog
          label={t("project.revoke")}
          title={t("project.revoke")}
          body={t("project.closeBody")}
          variant="outline"
          size="sm"
          onConfirm={() => revoke.mutateAsync(r.id)}
        />
      )}
      {error && <Alert>{error}</Alert>}
    </li>
  );
}

function NewProject({ onDone }: { onDone: () => void }) {
  const spaces = useSpaces();
  const navigate = useNavigate();
  const { create } = useProjectActions();
  const [name, setName] = useState("");
  const [lead, setLead] = useState<Colleague[]>([]);
  const [members, setMembers] = useState<Colleague[]>([]);
  const [ends, setEnds] = useState("");
  const [share, setShare] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  return (
    <Card>
      <CardHeader className="pb-3">
        <h2 className="font-semibold">{t("project.new")}</h2>
        <p className="text-sm text-muted-foreground">{t("project.createExplain")}</p>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            try {
              const p = await create.mutateAsync({
                name,
                ends_on: ends,
                lead_id: lead[0]?.id ?? null,
                members: members.map((m) => m.id),
                shares: share.map((space) => ({ space, note: "" })),
              });
              onDone();
              void navigate(`/projects/${p.id}`);
            } catch (err) {
              setError(messageOf(err));
            }
          }}
        >
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="pr-name">{t("project.name")}</Label>
              <Input id="pr-name" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="pr-ends">{t("project.endsOn")}</Label>
              <Input id="pr-ends" type="date" required min={tomorrow()} value={ends} onChange={(e) => setEnds(e.target.value)} />
              <p className="text-xs text-muted-foreground">{t("project.endsHint")}</p>
            </div>
          </div>
          <PeoplePicker id="pr-lead" label={t("project.lead")} hint={t("project.leadHint")} value={lead} onChange={setLead} single />
          <PeoplePicker id="pr-members" label={t("project.members")} value={members} onChange={setMembers} />
          <fieldset className="space-y-1">
            <legend className="text-sm font-medium">{t("project.shareWith")}</legend>
            <div className="flex flex-wrap gap-4">
              {(spaces.data ?? []).map((s) => (
                <Checkbox
                  key={s.name}
                  label={s.title}
                  checked={share.includes(s.name)}
                  onChange={() => setShare(share.includes(s.name) ? share.filter((x) => x !== s.name) : [...share, s.name])}
                />
              ))}
            </div>
          </fieldset>
          {error && <Alert>{error}</Alert>}
          <div className="flex gap-2">
            <Button type="submit" disabled={create.isPending}>{t("project.create")}</Button>
            <Button type="button" variant="ghost" onClick={onDone}>{t("common.cancel")}</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export function ProjectList() {
  const projects = useProjects();
  const requests = useShareRequests();
  const leadSpaces = useLeadSpaces();
  const [creating, setCreating] = useState(false);
  if (projects.isPending) return <Loading />;
  if (projects.isError) return <p role="alert" className="p-6 text-sm">{t("error.generic")}</p>;
  return (
    <div className="mx-auto max-w-5xl space-y-6 px-6 py-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t("project.title")}</h1>
        {leadSpaces.length > 0 && !creating && <Button onClick={() => setCreating(true)}>{t("project.new")}</Button>}
      </div>
      {creating && <NewProject onDone={() => setCreating(false)} />}
      {projects.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("project.empty")}</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {projects.data.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
              <Link to={`/projects/${p.id}`} className="font-medium hover:underline">{p.name}</Link>
              <span className="flex items-center gap-2 text-xs text-muted-foreground">
                {label(`project.role.${p.my_role}`, p.my_role)} · {p.lead.name}
                <Status p={p} />
              </span>
            </li>
          ))}
        </ul>
      )}
      {leadSpaces.length > 0 && (
        <Card>
          <CardHeader className="pb-3"><h2 className="font-semibold">{t("project.requests")}</h2></CardHeader>
          <CardContent>
            {!requests.data?.length ? (
              <p className="text-sm text-muted-foreground">{t("project.requestsEmpty")}</p>
            ) : (
              <ul className="space-y-3">{requests.data.map((r) => <ApproveShare key={r.id} r={r} />)}</ul>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function LeadTools({ p }: { p: Project }) {
  const spaces = useSpaces();
  const a = useProjectActions();
  const [add, setAdd] = useState<Colleague[]>([]);
  const [space, setSpace] = useState("");
  const [note, setNote] = useState("");
  const [ends, setEnds] = useState(p.ends_on);
  const [name, setName] = useState(p.name);
  const [error, setError] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>, after?: () => void) => {
    setError(null);
    try {
      await fn();
      after?.();
    } catch (e) {
      setError(messageOf(e));
    }
  };
  const asked = new Set(p.shares.map((s) => s.space));
  return (
    <div className="space-y-4">
      {error && <Alert>{error}</Alert>}
      <form className="flex items-end gap-2" onSubmit={(e) => (e.preventDefault(), void run(() => a.rename.mutateAsync({ id: p.id, name })))}>
        <div className="flex-1 space-y-1">
          <Label htmlFor="pr-rename">{t("project.name")}</Label>
          <Input id="pr-rename" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
        </div>
        <Button type="submit" variant="outline" size="sm" disabled={!name.trim() || name === p.name}>{t("project.rename")}</Button>
      </form>
      <div className="space-y-2">
        <PeoplePicker id="pr-add" label={t("project.addMembers")} value={add} onChange={setAdd} />
        <Button size="sm" variant="outline" disabled={!add.length} onClick={() => run(() => a.addMembers.mutateAsync({ id: p.id, user_ids: add.map((x) => x.id) }), () => setAdd([]))}>
          {t("project.add")}
        </Button>
      </div>
      <form
        className="space-y-2"
        onSubmit={(e) => (e.preventDefault(), void run(() => a.requestShare.mutateAsync({ id: p.id, space, note }), () => (setSpace(""), setNote(""))))}
      >
        <p className="text-sm font-medium">{t("project.requestShare")}</p>
        <div className="grid grid-cols-[12rem_1fr] gap-2">
          <Select aria-label={t("project.department")} value={space} onChange={(e) => setSpace(e.target.value)} required>
            <option value="" disabled>{t("project.department")}</option>
            {(spaces.data ?? []).filter((s) => s.name !== p.space && !asked.has(s.name)).map((s) => (
              <option key={s.name} value={s.name}>{s.title}</option>
            ))}
          </Select>
          <Input aria-label={t("project.note")} placeholder={t("project.note")} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <Button type="submit" size="sm" variant="outline" disabled={!space}>{t("project.send")}</Button>
      </form>
      <form className="flex items-end gap-2" onSubmit={(e) => (e.preventDefault(), void run(() => a.renew.mutateAsync({ id: p.id, ends_on: ends })))}>
        <div className="space-y-1">
          <Label htmlFor="pr-renew">{t("project.renew")}</Label>
          <Input id="pr-renew" type="date" min={tomorrow()} value={ends} onChange={(e) => setEnds(e.target.value)} />
          <p className="text-xs text-muted-foreground">{t("project.renewExplain")}</p>
        </div>
        <Button type="submit" size="sm" variant="outline" disabled={ends === p.ends_on}>{t("common.save")}</Button>
      </form>
      <ConfirmDialog label={t("project.close")} title={t("project.close")} body={t("project.closeBody")} variant="outline" size="sm" onConfirm={() => a.close.mutateAsync(p.id)} />
    </div>
  );
}

export function ProjectView() {
  const { id = "" } = useParams();
  const project = useProject(id);
  const { removeMember } = useProjectActions();
  if (project.isPending) return <Loading />;
  if (project.isError) return <NotFound />;
  const p = project.data;
  const isLead = p.my_role === "lead";
  return (
    <div className="mx-auto grid max-w-6xl grid-cols-[1fr_22rem] gap-6 px-6 py-6">
      <div className="space-y-4">
        <Link to="/projects" className="text-sm text-muted-foreground hover:text-foreground">← {t("project.title")}</Link>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">{p.name}</h1>
          <Status p={p} />
        </div>
        <p className="text-sm text-muted-foreground">
          {t("project.lead")}: {p.lead.name} · {day(p.starts_on)} – {day(p.ends_on)}
        </p>
        {p.active && (p.my_role === "lead" || p.my_role === "member") && (
          <div className="flex gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to={`/library?view=department&group=${encodeURIComponent(p.space)}`}>{t("project.openLibrary")}</Link>
            </Button>
            <Button asChild variant="outline" size="sm"><Link to="/write/new">{t("project.writeNote")}</Link></Button>
          </div>
        )}
        <Card>
          <CardHeader className="pb-3"><h2 className="font-semibold">{t("project.shares")}</h2></CardHeader>
          <CardContent>
            {p.shares.length === 0 ? <p className="text-sm text-muted-foreground">{t("project.noShares")}</p> : (
              <ul className="space-y-1 text-sm">
                {p.shares.map((s) => (
                  <li key={s.id} className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{s.space}</span>
                    <Badge variant={s.in_force ? "default" : "outline"}>{label(`project.share.status.${s.status}`, s.status)}</Badge>
                    {s.status === "approved" && (
                      <span className="text-xs text-muted-foreground">
                        {t("project.shareScope", {
                          scope: s.scope === "selected" ? t("project.shareSome", { folders: s.folders.length, docs: s.documents }) : t("project.shareWhole"),
                          level: level(s.max_sensitivity),
                        })}
                        {s.approved_until && <> · {t("project.shareUntil", { date: day(s.approved_until) })}</>}
                      </span>
                    )}
                    {s.renewal_requested && <Badge variant="warning">{t("project.renewalAsked")}</Badge>}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        {isLead && p.active && <LeadTools p={p} />}
      </div>
      <aside>
        <Card>
          <CardHeader className="pb-3"><h2 className="font-semibold">{t("project.members")} ({p.members.length})</h2></CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {p.members.map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-2">
                  {m.name}
                  {isLead && p.active && m.id !== p.lead.id && (
                    <Button variant="ghost" size="sm" aria-label={t("project.remove", { name: m.name })} onClick={() => removeMember.mutate({ id: p.id, user: m.id })}>
                      ×
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}
