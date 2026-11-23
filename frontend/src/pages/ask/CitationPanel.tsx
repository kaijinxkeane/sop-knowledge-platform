import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { BookmarkButton } from "@/pages/library/BookmarkButton";
import { NoteView } from "@/pages/library/NoteView";
import { PdfViewer } from "@/pages/library/PdfViewer";
import { useDocument, useDocuments, useNoteText, useParts } from "@/pages/library/api";
import type { Citation } from "./api";

function Slides({ id, start }: { id: string; start: number }) {
  const parts = useParts(id, true);
  const slides = (parts.data ?? []).filter((p) => p.part === "slide");
  const [n, setN] = useState(start);
  const slide = slides.find((s) => s.number === n);
  if (parts.isPending) return <p className="text-sm text-muted-foreground">{t("app.loading")}</p>;
  if (!slide) return <p className="text-sm text-muted-foreground">{t("doc.loadFailed")}</p>;
  return (
    <div className="space-y-3">
      <div className="rounded-md border bg-muted/30 p-4">
        <p className="text-xs text-muted-foreground">{t("doc.slideOf", { n, total: slides.length })}</p>
        <h3 className="mt-1 font-semibold">{slide.title || "—"}</h3>
      </div>
      <div className="flex items-center justify-between">
        <Button variant="outline" size="icon" aria-label={t("doc.previousSlide")} disabled={n <= 1} onClick={() => setN(n - 1)}>
          <ChevronLeft />
        </Button>
        <Button
          variant="outline"
          size="icon"
          aria-label={t("doc.nextSlide")}
          disabled={n >= slides.length}
          onClick={() => setN(n + 1)}
        >
          <ChevronRight />
        </Button>
      </div>
      <div className={n === start ? "rounded-md bg-amber-50 p-2" : "p-2"}>
        <div className="text-xs font-medium text-muted-foreground">{t("doc.speakerNotes")}</div>
        <p className="mt-1 whitespace-pre-wrap text-sm">{slide.speaker_notes || t("doc.noNotes")}</p>
      </div>
    </div>
  );
}

/** The cited section of a note, scrolled to and highlighted. */
function NoteExcerpt({ id, heading }: { id: string; heading?: string | null }) {
  const text = useNoteText(id, true);
  const docs = useDocuments();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!heading || !box.current) return;
    // headings are stored as "Title › Section"; the panel looks for the section
    const want = heading.split(/\s*[›>]\s*/).pop()!.trim().toLowerCase();
    const el = [...box.current.querySelectorAll("h1,h2,h3,h4,h5,h6")].find(
      (h) => h.textContent?.trim().toLowerCase() === want,
    );
    if (el) {
      el.classList.add("sop-cited");
      el.scrollIntoView?.({ block: "start" });
    }
  }, [heading, text.data, docs.data]);
  if (text.isPending || docs.isPending) return <p className="text-sm text-muted-foreground">{t("app.loading")}</p>;
  if (text.isError) return <p className="text-sm text-muted-foreground">{t("doc.loadFailed")}</p>;
  return (
    <div ref={box} className="max-h-[60vh] overflow-y-auto text-sm">
      <NoteView text={text.data} docs={docs.data ?? []} />
    </div>
  );
}

/** Side panel for one citation (frontend spec §4): the passage, and who wrote and approved it. */
export function CitationPanel({ citation: c, onClose }: { citation: Citation; onClose: () => void }) {
  const doc = useDocument(c.document_id);
  const where = c.part === "slide" ? `?slide=${c.part_number}` : c.part === "page" ? `?page=${c.part_number}` : "";
  return (
    <aside aria-label={t("ask.source")} className="space-y-3 border-l p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs text-muted-foreground">
            {t("ask.sourceN", { n: c.n })}
            {c.heading && ` · ${c.heading}`}
          </div>
          <h2 className="font-semibold">{c.title}</h2>
        </div>
        <Button variant="ghost" size="icon" aria-label={t("common.close")} onClick={onClose}>
          <X />
        </Button>
      </div>
      <div className="flex flex-wrap gap-1">
        {c.version && <Badge variant="outline">{t("ask.version", { v: c.version.slice(0, 7) })}</Badge>}
        {c.written_by && <Badge variant="outline">{t("ask.writtenBy", { who: c.written_by })}</Badge>}
        {c.approved_by ? (
          <Badge>{t("ask.approvedBy", { who: c.approved_by, on: c.approved_on ?? "" })}</Badge>
        ) : (
          c.approval && <Badge variant="warning">{c.approval}</Badge>
        )}
        {/* Only people who can see unapproved changes get pending_change. */}
        {doc.data?.pending_change && <Badge variant="warning">{t("ask.pendingReview")}</Badge>}
      </div>
      {doc.isError ? (
        <p className="text-sm text-muted-foreground">{t("doc.loadFailed")}</p>
      ) : !doc.data ? (
        <p className="text-sm text-muted-foreground">{t("app.loading")}</p>
      ) : c.part === "slide" && c.part_number ? (
        <Slides key={`${c.document_id}-${c.part_number}`} id={c.document_id} start={c.part_number} />
      ) : c.part === "page" && c.part_number ? (
        <PdfViewer doc={doc.data} page={c.part_number} />
      ) : (
        <NoteExcerpt id={c.document_id} heading={c.heading} />
      )}
      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline" size="sm">
          <Link to={`/library/${c.document_id}${where}`}>{t("ask.openInLibrary")}</Link>
        </Button>
        <BookmarkButton docId={c.document_id} part={c.part_number ?? undefined} />
      </div>
    </aside>
  );
}
