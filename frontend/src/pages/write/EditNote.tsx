import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Link, useBlocker, useParams } from "react-router";
import { messageOf } from "@/api/errors";
import { Loading } from "@/app/routes";
import { useMe } from "@/auth/hooks";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { bodyToSave } from "@/editor/editor";
import type { EditorHandle } from "@/editor/MilkdownEditor";
import { merge3, type Part } from "@/editor/merge";
import { readMeta, writeMeta, type Meta } from "@/editor/meta";
import { t } from "@/i18n";
import { splitFrontmatter } from "@/lib/obsidian";
import { useDocument } from "@/pages/library/api";
import { NotFound } from "@/pages/NotFound";
import { Clash, getSource, saveNote, submitNote, uploadAttachment, useAfterSave, useSource } from "./api";
import { LinkDialog } from "./LinkDialog";
import { MergeDialog } from "./MergeDialog";
import { MetaForm } from "./MetaForm";
import { UploadDialog } from "./UploadDialog";

const MilkdownEditor = lazy(() => import("@/editor/MilkdownEditor"));

/** Drafts save themselves this long after the last keystroke (frontend spec §6). */
export const AUTOSAVE_MS = 8_000;

type Saved = { text: string; version: string };

const STATUS = {
  draft: "doc.draft",
  in_review: "write.inReview",
  published: "write.published",
  retired: "doc.retired",
} as const;
const statusLabel = (s: string | undefined) => t(STATUS[(s || "draft") as keyof typeof STATUS] ?? "doc.unreviewed");

function time(d: Date) {
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function Editor({ id, opened }: { id: string; opened: Saved }) {
  const doc = useDocument(id);
  const afterSave = useAfterSave();
  const editor = useRef<EditorHandle | null>(null);

  // What is saved, as far as this screen knows: the merge base.
  const [saved, setSaved] = useState<Saved>(opened);
  const [meta, setMeta] = useState<Meta | null>(() => readMeta(opened.text));
  const [body, setBody] = useState(() => splitFrontmatter(opened.text).body);
  // The editor's serialisation of `saved`: equal to it means "no change".
  const [baseline, setBaseline] = useState<string | null>(null);
  const ready = baseline !== null;

  const [state, setState] = useState<"idle" | "saving" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [merge, setMerge] = useState<{ parts: Part[]; theirs: Saved } | null>(null);
  const [dialog, setDialog] = useState<"upload" | "link" | null>(null);

  const savedBody = splitFrontmatter(saved.text).body;
  const savedHead = saved.text.slice(0, saved.text.length - savedBody.length);

  /** The full file this screen would save now. */
  const compose = useCallback((): string => {
    const nextBody = baseline === null ? savedBody : bodyToSave(savedBody, baseline, body);
    const text = savedHead + nextBody;
    return meta ? writeMeta(text, meta) : text;
  }, [baseline, body, meta, savedBody, savedHead]);

  const dirty = ready && compose() !== saved.text;

  /** Load new saved text into the screen (after a merge or an upload). */
  const reset = (next: Saved) => {
    setSaved(next);
    setMeta(readMeta(next.text));
    const nb = splitFrontmatter(next.text).body;
    const b = editor.current?.replace(nb) ?? null;
    setBaseline(b);
    setBody(b ?? nb);
  };

  const onChange = useCallback((md: string) => setBody(md), []);

  const save = useCallback(
    async (quiet = false): Promise<boolean> => {
      let content: string;
      try {
        content = compose();
      } catch {
        setError(t("write.badYaml"));
        return false;
      }
      if (content === saved.text) return true;
      setState("saving");
      setError(null);
      try {
        const out = await saveNote(id, saved.version, content);
        setSaved({ text: content, version: out.version });
        setBaseline(body);
        setLastSaved(new Date());
        setState("idle");
        afterSave(id);
        return true;
      } catch (err) {
        if (err instanceof Clash) {
          const now = await getSource(id);
          setMerge({ parts: merge3(saved.text, content, now.content), theirs: { text: now.content, version: now.version } });
          setState("idle");
          return false;
        }
        setState("error");
        if (!quiet) setError(messageOf(err));
        else setError(t("write.autosaveFailed"));
        return false;
      }
    },
    [afterSave, body, compose, id, saved],
  );

  // Autosave drafts a few seconds after the last change.
  const isDraft = (readMeta(saved.text)?.status ?? "draft") === "draft";
  useEffect(() => {
    if (!dirty || !isDraft || merge || state === "saving") return;
    const timer = setTimeout(() => void save(true), AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [dirty, isDraft, merge, save, state, body, meta]);

  // Don't lose work: warn before leaving with unsaved changes.
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function saveMerged(text: string) {
    if (!merge) return;
    setState("saving");
    try {
      const out = await saveNote(id, merge.theirs.version, text);
      setMerge(null);
      reset({ text, version: out.version });
      setLastSaved(new Date());
      setState("idle");
      afterSave(id);
    } catch (err) {
      setState("idle");
      if (err instanceof Clash) {
        // Someone saved again while merging: merge against the newest.
        const now = await getSource(id);
        setMerge({ parts: merge3(saved.text, text, now.content), theirs: { text: now.content, version: now.version } });
      } else {
        setMerge(null);
        setError(messageOf(err));
      }
    }
  }

  async function submit() {
    setNotice(null);
    if (dirty && !(await save())) return;
    try {
      await submitNote(id);
      setNotice(t("write.submitted"));
      afterSave(id);
    } catch (err) {
      setError(messageOf(err));
    }
  }

  async function upload(file: File, tool: string, link: string) {
    if (dirty && !(await save())) throw new Error(t("write.saveFirst"));
    await uploadAttachment(id, file, tool, link);
    // The server adds the embed line to the note: start again from what is saved.
    const now = await getSource(id);
    reset({ text: now.content, version: now.version });
    afterSave(id);
  }

  const title = meta?.title || doc.data?.title || "";
  const status = state === "saving"
    ? t("common.saving")
    : dirty
      ? t("write.unsaved")
      : lastSaved
        ? (isDraft ? t("write.autosavedAt", { time: time(lastSaved) }) : t("write.savedAt", { time: time(lastSaved) }))
        : t("write.noChanges");

  return (
    <div className="mx-auto max-w-5xl space-y-4 px-6 py-6">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <Link to={`/library/${id}`} className="text-sm text-muted-foreground hover:underline">
            ← {t("write.backToNote")}
          </Link>
          <h1 className="text-2xl font-semibold">{title}</h1>
        </div>
        <p className="text-sm text-muted-foreground" role="status" aria-live="polite">
          {statusLabel(readMeta(saved.text)?.status)} · {status}
        </p>
      </header>

      {meta ? (
        <MetaForm meta={meta} onChange={setMeta} doc={doc.data} />
      ) : (
        <Alert>{t("write.badYaml")}</Alert>
      )}

      <Suspense fallback={<Loading />}>
        <MilkdownEditor
          initial={splitFrontmatter(opened.text).body}
          label={t("write.bodyLabel")}
          handle={editor}
          onChange={onChange}
          onReady={(b) => {
            setBaseline(b);
            setBody(b);
          }}
          onInsertLink={() => setDialog("link")}
        />
      </Suspense>

      {error && <Alert>{error}</Alert>}
      {notice && <p role="status" className="text-sm">{notice}</p>}

      <footer className="flex flex-wrap items-center gap-2">
        <Button variant="outline" onClick={() => setDialog("upload")}>
          {t("write.upload")}
        </Button>
        <Button variant="outline" asChild>
          <Link to={`/library/${id}`}>{t("write.preview")}</Link>
        </Button>
        <span className="flex-1" />
        <Button variant="outline" onClick={() => void save()} disabled={!dirty || state === "saving"}>
          {t("common.save")}
        </Button>
        <Button onClick={() => void submit()} disabled={state === "saving"}>
          {t("write.submit")}
        </Button>
      </footer>

      {merge && (
        <MergeDialog
          parts={merge.parts}
          busy={state === "saving"}
          onSave={(text) => void saveMerged(text)}
          onCancel={() => setMerge(null)}
        />
      )}
      {dialog === "upload" && <UploadDialog onUpload={upload} onClose={() => setDialog(null)} />}
      {dialog === "link" && (
        <LinkDialog
          onPick={(md) => {
            editor.current?.insert(md, true);
            setDialog(null);
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {blocker.state === "blocked" && (
        <Dialog open onOpenChange={(open) => !open && blocker.reset()}>
          <DialogContent>
            <DialogTitle>{t("write.leaveTitle")}</DialogTitle>
            <DialogDescription>{t("write.leaveBody")}</DialogDescription>
            <DialogFooter>
              <Button variant="outline" onClick={() => blocker.reset()}>
                {t("write.stay")}
              </Button>
              <Button onClick={() => blocker.proceed()}>
                {t("write.leave")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

export default function EditNote() {
  const { id = "" } = useParams();
  const source = useSource(id);
  const me = useMe();
  if (source.isError) return <NotFound />;
  if (source.isPending || !me.data) return <Loading />;
  return <Editor key={id} id={id} opened={{ text: source.data.content, version: source.data.version }} />;
}
