import { ArrowLeft, Download, FileDown, Pencil } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { ApiError } from "@/api/client";
import { useMe } from "@/auth/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { t, type MessageKey } from "@/i18n";
import { plainName } from "@/lib/obsidian";
import { cn } from "@/lib/utils";
import { NotFound } from "@/pages/NotFound";
import {
  downloadFile,
  exportPdf,
  useBacklinks,
  useDocument,
  useDocuments,
  useNoteText,
  useVersion,
  useVersions,
  type Doc,
} from "./api";
import { BookmarkButton } from "./BookmarkButton";
import { AssignReading, ReadingBanner } from "@/pages/reading/ReadingPanel";
import { DeckViewer } from "./DeckViewer";
import { NoteView } from "./NoteView";
import { PdfViewer } from "./PdfViewer";
import { backFromDocument, type Place } from "@/lib/places";

/** "Library", "Ask", "Review"…: the page a document's back link returns to. */
function backLabel(back: Place): string {
  const known = ["ask", "library", "write", "review", "retain", "handovers", "projects", "admin"];
  if (back.section === "" || back.section === "account" || back.section === "notice") return t("nav.home");
  if (back.section === "paths") return t("paths.title");
  return known.includes(back.section) ? t(`nav.${back.section}` as MessageKey) : t("doc.backToLibrary");
}
import { StatusDot } from "./StatusDot";
import { spaceLabel } from "@/lib/spaceLabel";

const ext = (doc: Doc) => doc.vault_path.split(".").pop()?.toLowerCase() ?? "";

function Meta({ doc }: { doc: Doc }) {
  const rows: [MessageKey, ReactNode][] = [
    ["doc.type", doc.doc_type],
    ["doc.programme", plainName(doc.programme)],
    ["doc.stage", doc.stage],
    ["doc.owner", plainName(doc.owner)],
    ["doc.reviewDue", doc.review_due],
    [
      "doc.access",
      doc.access.length ? (
        <span className="flex flex-wrap gap-1">
          {doc.access.map((a) => (
            <Badge key={`${a.space}-${a.sensitivity}`} variant="outline">
              {spaceLabel(a.space)} · {t(`sensitivity.${a.sensitivity}` as MessageKey)}
            </Badge>
          ))}
        </span>
      ) : null,
    ],
  ];
  return (
    <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm">
      <div className="flex items-center gap-2">
        <dt className="sr-only">Status</dt>
        <dd>
          <StatusDot doc={doc} withLabel />
        </dd>
      </div>
      {rows
        .filter(([, v]) => v)
        .map(([label, value]) => (
          <div key={label} className="flex items-center gap-2">
            <dt className="text-muted-foreground">{t(label)}</dt>
            <dd>{value}</dd>
          </div>
        ))}
    </dl>
  );
}

function ExportButton({ doc }: { doc: Doc }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <span className="inline-flex items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setError(null);
          exportPdf({ document_id: doc.id }, doc.title)
            .catch((e) => setError(e instanceof ApiError && e.status === 403 ? t("doc.exportOff") : t("doc.loadFailed")))
            .finally(() => setBusy(false));
        }}
      >
        <FileDown />
        {t("doc.exportPdf")}
      </Button>
      {error && <span className="text-xs text-destructive">{error}</span>}
    </span>
  );
}

function DownloadButton({ doc, commit }: { doc: Doc; commit?: string | null }) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  return (
    <span className="inline-flex items-center gap-2">
      <Button
        variant="outline"
        size="sm"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setFailed(false);
          downloadFile(doc, commit)
            .catch(() => setFailed(true))
            .finally(() => setBusy(false));
        }}
      >
        <Download />
        {t("doc.download")}
      </Button>
      {failed && <span className="text-xs text-destructive">{t("doc.loadFailed")}</span>}
    </span>
  );
}

function Sidebar({ doc, viewing }: { doc: Doc; viewing: string | null }) {
  const backlinks = useBacklinks(doc.id);
  const versions = useVersions(doc.id);
  return (
    <aside className="space-y-8 text-sm print:hidden">
      <section>
        <h2 className="font-medium">{t("doc.usedIn")}</h2>
        {backlinks.data?.length ? (
          <ul className="mt-2 space-y-1">
            {backlinks.data.map((b) => (
              <li key={b.id}>
                <Link to={`/library/${b.id}`} className="underline underline-offset-2">
                  {b.title}
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-muted-foreground">{t("doc.noBacklinks")}</p>
        )}
      </section>
      <section>
        <h2 className="font-medium">{t("doc.history")}</h2>
        <ol className="mt-2 space-y-2">
          {versions.data?.map((v, i) => (
            <li key={v.commit} className={cn("border-l-2 pl-3", v.commit === viewing && "border-primary")}>
              <div className="flex items-center gap-2">
                {v.author_name}
                {v.live && <Badge>{t("version.live")}</Badge>}
                {v.latest && !v.approved && <Badge variant="warning">{t("version.unapproved")}</Badge>}
              </div>
              <div className="text-xs text-muted-foreground">
                {new Date(v.committed_at).toLocaleString()}
                {v.author_source === "git" && ` · ${t("doc.viaObsidian")}`}
              </div>
              {v.author_source === "unattributed" && (
                <Badge variant="warning" className="mt-1">
                  {t("doc.unattributed")}
                </Badge>
              )}
              <div className="mt-1 flex gap-3 text-xs">
                <Link className="underline underline-offset-2" to={`/library/${doc.id}?version=${v.commit}`}>
                  {t("version.read")}
                </Link>
                {i + 1 < (versions.data?.length ?? 0) && (
                  <Link
                    className="underline underline-offset-2"
                    to={`/library/${doc.id}/compare?from=${versions.data![i + 1]!.commit}&to=${v.commit}`}
                  >
                    {t("version.compare")}
                  </Link>
                )}
              </div>
            </li>
          ))}
        </ol>
      </section>
    </aside>
  );
}

function OldVersion({ doc, commit }: { doc: Doc; commit: string }) {
  const v = useVersion(doc.id, commit);
  const docs = useDocuments();
  if (v.isPending || docs.isPending) return <p className="text-sm text-muted-foreground">{t("app.loading")}</p>;
  // Unknown, unapproved or once-narrower versions all answer 404: say only that it isn't available.
  if (v.isError) return <p role="alert" className="text-sm">{t("version.unavailable")}</p>;
  return (
    <>
      <div role="note" className="mb-4 flex flex-wrap items-center gap-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm">
        <span>
          {t("version.banner", {
            when: new Date(v.data.committed_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }),
            who: v.data.author_name,
          })}
          {!v.data.approved && ` ${t("version.bannerUnapproved")}`}
        </span>
        <Link className="underline underline-offset-2" to={`/library/${doc.id}`}>{t("version.backToCurrent")}</Link>
        <Link className="underline underline-offset-2" to={`/library/${doc.id}/compare?from=${commit}`}>
          {t("version.compareWithLatest")}
        </Link>
        {doc.kind !== "note" && <DownloadButton doc={doc} commit={commit} />}
      </div>
      {doc.kind === "note" ? (
        <NoteView text={v.data.content} docs={docs.data ?? []} />
      ) : ext(doc) === "pptx" ? (
        <DeckViewer doc={doc} versionParts={v.data.parts ?? []} commit={commit} />
      ) : ext(doc) === "pdf" ? (
        <PdfViewer doc={doc} commit={commit} />
      ) : (
        <>
          <p className="mb-2 text-xs text-muted-foreground">{t("version.textOnly")}</p>
          <NoteView text={v.data.content} docs={docs.data ?? []} />
        </>
      )}
    </>
  );
}

function Body({ doc, version }: { doc: Doc; version: string | null }) {
  const isNote = doc.kind === "note";
  const text = useNoteText(doc.id, isNote && !version);
  const docs = useDocuments();
  if (version) return <OldVersion doc={doc} commit={version} />;
  if (isNote) {
    if (text.isPending || docs.isPending) {
      return <p className="text-sm text-muted-foreground">{t("app.loading")}</p>;
    }
    if (text.isError) return <p className="text-sm text-muted-foreground">{t("doc.loadFailed")}</p>;
    return <NoteView text={text.data} docs={docs.data ?? []} />;
  }
  if (ext(doc) === "pptx") return <DeckViewer doc={doc} />;
  if (ext(doc) === "pdf") return <PdfViewer doc={doc} />;
  return <DownloadButton doc={doc} />;
}

export default function Reader() {
  const { id = "" } = useParams();
  const doc = useDocument(id);
  const me = useMe();
  const [params] = useSearchParams();
  const version = params.get("version");
  const [assigning, setAssigning] = useState(false);
  if (doc.isPending) return <p className="p-6 text-sm text-muted-foreground">{t("app.loading")}</p>;
  // A hidden document answers 404 like a missing one, and looks the same here.
  if (doc.isError) {
    return doc.error instanceof ApiError && doc.error.status >= 500 ? (
      <p className="p-6 text-sm" role="alert">
        {t("error.generic")}
      </p>
    ) : (
      <NotFound />
    );
  }
  const d = doc.data;
  // Cosmetic only: the save endpoint checks `contribute` again.
  const canEdit = d.access.some((a) => me.data?.space_actions[a.space]?.includes("contribute"));
  // Cosmetic too: assigning reading checks `approve` on the note's space.
  const canAssign =
    d.kind === "note" && d.approved && d.status !== "retired" &&
    d.access.some((a) => me.data?.space_actions[a.space]?.includes("approve"));
  const back = backFromDocument();
  return (
    <div className="mx-auto max-w-6xl px-6 py-6">
      <Link to={back.to} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground print:hidden">
        <ArrowLeft className="size-4" />
        {backLabel(back)}
      </Link>
      <header className="mt-3 border-b pb-4">
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-2xl font-semibold">{d.title}</h1>
          <div className="flex shrink-0 items-center gap-2 print:hidden">
          {d.kind !== "note" && <DownloadButton doc={d} />}
          {d.kind === "note" && !version && <ExportButton doc={d} />}
          <BookmarkButton docId={d.id} />
          {canAssign && !assigning && (
            <Button variant="outline" size="sm" onClick={() => setAssigning(true)}>
              {t("reading.assign")}
            </Button>
          )}
          {d.kind === "note" && canEdit && (
            <Button asChild variant="outline" size="sm">
              <Link to={`/write/${d.id}`}>
                <Pencil />
                {t("doc.edit")}
              </Link>
            </Button>
          )}
          </div>
        </div>
        <Meta doc={d} />
        {assigning && <AssignReading docId={d.id} onDone={() => setAssigning(false)} />}
        {d.kind === "note" && d.approved && !version && <ReadingBanner docId={d.id} />}
      </header>
      <div className="mt-6 grid grid-cols-[1fr_16rem] gap-10 print:block">
        <article className="min-w-0">
          <Body doc={d} version={version} />
        </article>
        <Sidebar doc={d} viewing={version} />
      </div>
    </div>
  );
}
