import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Folder, FolderPlus } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api, unwrap, type Schemas } from "@/api/client";
import { call, messageOf } from "@/api/errors";
import { useMe } from "@/auth/hooks";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { t } from "@/i18n";
import type { Doc } from "./api";
import { StatusDot } from "./StatusDot";
import { spaceLabel } from "@/lib/spaceLabel";

type FolderInfo = Schemas["FolderOut"];

/** Folders that keep their own rules and aren't arranged here. */
const CLOSED = ["Help", "Inbox", "Drafts", "Handovers", "Projects"];
const isClosed = (path: string) => CLOSED.some((c) => path === c || path.startsWith(`${c}/`));
const parentOf = (path: string) => (path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "");
const nameOf = (path: string) => path.slice(path.lastIndexOf("/") + 1);
const folderOf = (d: Doc) => parentOf(d.vault_path);

export const useFolders = () =>
  useQuery({ queryKey: ["library", "folders"], queryFn: () => unwrap(api.GET("/api/v1/library/folders")) });

export function useFolderActions() {
  const qc = useQueryClient();
  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["library", "folders"] }),
      qc.invalidateQueries({ queryKey: ["documents"] }),
    ]);
  return {
    create: useMutation({
      mutationFn: (body: Schemas["FolderIn"]) => unwrap(api.POST("/api/v1/library/folders", { body })),
      onSettled: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) =>
        call(api.DELETE("/api/v1/library/folders/{folder_id}", { params: { path: { folder_id: id } } })),
      onSettled: refresh,
    }),
    move: useMutation({
      mutationFn: ({ id, folder }: { id: string; folder: string }) =>
        unwrap(api.POST("/api/v1/library/documents/{doc_id}/move", { params: { path: { doc_id: id } }, body: { folder } })),
      onSettled: refresh,
    }),
  };
}

/** Every folder of a department: the ones made in the app or set up for it,
 * and every folder its readable documents are in (with their parents). */
function departmentFolders(space: string, docs: Doc[], folders: FolderInfo[]): string[] {
  const all = new Set<string>();
  const add = (path: string) => {
    for (let p = path; p; p = parentOf(p)) all.add(p);
  };
  folders.filter((f) => f.space === space).forEach((f) => add(f.path));
  docs.filter((d) => d.space === space).forEach((d) => add(folderOf(d)));
  return [...all].sort((a, b) => a.localeCompare(b));
}

function MoveControl({ doc, folders, onMoved }: { doc: Doc; folders: string[]; onMoved: (msg: string) => void }) {
  const { move } = useFolderActions();
  const [open, setOpen] = useState(false);
  const here = folderOf(doc);
  const [to, setTo] = useState(folders.find((f) => f !== here) ?? "");
  const [error, setError] = useState<string | null>(null);
  if (!open)
    return (
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        {t("folders.move")}
      </Button>
    );
  return (
    <form
      aria-label={t("folders.moveTitle", { title: doc.title })}
      className="flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        move.mutateAsync({ id: doc.id, folder: to }).then(
          () => onMoved(t("folders.moved", { title: doc.title, folder: to })),
          (err) => setError(messageOf(err)),
        );
      }}
    >
      <Select aria-label={t("folders.moveTo")} value={to} onChange={(e) => setTo(e.target.value)}>
        {folders.filter((f) => f !== here).map((f) => (
          <option key={f} value={f}>{f}</option>
        ))}
      </Select>
      <Button type="submit" size="sm" disabled={!to || move.isPending}>{t("folders.moveButton")}</Button>
      <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>{t("common.cancel")}</Button>
      {error && <span role="alert" className="text-xs text-destructive">{error}</span>}
    </form>
  );
}

/**
 * Library → Folders: one department at a time, browsed like a file explorer.
 * People who can write in the department make folders and move documents;
 * the backend keeps every document inside its own department, with the same access.
 */
export function FolderBrowser({
  space,
  path,
  docs,
  onOpen,
}: {
  space: string;
  path: string;
  docs: Doc[];
  onOpen: (path: string | null) => void;
}) {
  const me = useMe();
  const folders = useFolders();
  const { create, remove } = useFolderActions();
  const [naming, setNaming] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canEdit = !!me.data?.space_actions[space]?.includes("contribute");
  const info = useMemo(() => folders.data ?? [], [folders.data]);
  const all = useMemo(() => departmentFolders(space, docs, info), [space, docs, info]);
  const mine = docs.filter((d) => d.space === space);
  const children = all.filter((f) => parentOf(f) === path);
  const here = mine.filter((d) => folderOf(d) === path).sort((a, b) => a.title.localeCompare(b.title));
  const countIn = (f: string) => mine.filter((d) => d.vault_path.startsWith(`${f}/`)).length;
  const appFolder = info.find((f) => f.path === path && f.id);
  const destinations = all.filter((f) => !isClosed(f));
  const crumbs = path ? path.split("/").map((_, i, parts) => parts.slice(0, i + 1).join("/")) : [];

  async function addFolder(e: FormEvent) {
    e.preventDefault();
    if (!naming?.trim()) return;
    setError(null);
    try {
      const out = await create.mutateAsync({ space, parent: path, name: naming.trim() });
      setNaming(null);
      onOpen(out.path);
    } catch (err) {
      setError(messageOf(err));
    }
  }

  return (
    <div className="space-y-4">
      <nav aria-label={t("folders.breadcrumb")} className="flex flex-wrap items-center gap-1 text-sm">
        <button type="button" className="font-semibold hover:underline" onClick={() => onOpen(null)}>
          {spaceLabel(space)}
        </button>
        {crumbs.map((c) => (
          <span key={c} className="inline-flex items-center gap-1">
            <ChevronRight className="size-3 text-muted-foreground" aria-hidden />
            <button type="button" className="hover:underline" aria-current={c === path ? "page" : undefined} onClick={() => onOpen(c)}>
              {nameOf(c)}
            </button>
          </span>
        ))}
        {path && !isClosed(path) && (
          <Link to={`/ask?folder=${encodeURIComponent(path)}`} className="ml-auto text-sm text-primary hover:underline">
            {t("folders.ask")}
          </Link>
        )}
      </nav>
      {notice && <p role="status" className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-900">{notice}</p>}
      {error && <Alert>{error}</Alert>}
      {canEdit && path && !isClosed(path) && (
        <div className="flex flex-wrap items-center gap-2">
          {naming === null ? (
            <Button size="sm" variant="outline" onClick={() => setNaming("")}>
              <FolderPlus className="size-4" aria-hidden />
              {t("folders.new")}
            </Button>
          ) : (
            <form aria-label={t("folders.new")} className="flex items-center gap-2" onSubmit={(e) => void addFolder(e)}>
              <Input aria-label={t("folders.name")} value={naming} maxLength={80} autoFocus onChange={(e) => setNaming(e.target.value)} />
              <Button type="submit" size="sm" disabled={!naming.trim() || create.isPending}>{t("folders.create")}</Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => setNaming(null)}>{t("common.cancel")}</Button>
            </form>
          )}
          {appFolder && children.length === 0 && here.length === 0 && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => remove.mutateAsync(appFolder.id!).then(() => onOpen(parentOf(path) || null), (err) => setError(messageOf(err)))}
            >
              {t("folders.remove")}
            </Button>
          )}
        </div>
      )}
      {canEdit && !path && <p className="text-xs text-muted-foreground">{t("folders.openToAdd")}</p>}
      {children.length > 0 && (
        <ul className="grid gap-2 sm:grid-cols-2">
          {children.map((f) => (
            <li key={f}>
              <button type="button" onClick={() => onOpen(f)} className="flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left text-sm hover:bg-accent">
                <Folder className="size-4 text-muted-foreground" aria-hidden />
                <span className="font-medium">{nameOf(f)}</span>
                <span className="ml-auto text-xs text-muted-foreground">{t("folders.count", { n: countIn(f) })}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {here.length > 0 && (
        <ul className="divide-y">
          {here.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-3 py-2">
              <StatusDot doc={d} />
              <Link to={`/library/${d.id}`} className="font-medium hover:underline">{d.title}</Link>
              <span className="text-xs text-muted-foreground">{d.doc_type}</span>
              {canEdit && !isClosed(path) && destinations.length > 1 && (
                <span className="ml-auto">
                  <MoveControl doc={d} folders={destinations} onMoved={setNotice} />
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {children.length === 0 && here.length === 0 && <p className="text-sm text-muted-foreground">{t("folders.empty")}</p>}
    </div>
  );
}

/** The departments to list in Folders view: where I can read something or write. */
export function folderDepartments(docs: Doc[], me: { space_actions: Record<string, string[]> } | undefined): string[] {
  const spaces = new Set(docs.map((d) => d.space).filter((s): s is string => !!s && !s.startsWith("p-")));
  for (const [s, actions] of Object.entries(me?.space_actions ?? {})) {
    if (actions.includes("contribute") && !s.startsWith("p-")) spaces.add(s);
  }
  return [...spaces].sort();
}
