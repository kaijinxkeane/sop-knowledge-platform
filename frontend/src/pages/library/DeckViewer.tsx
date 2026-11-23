import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect } from "react";
import { useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { BookmarkButton } from "./BookmarkButton";
import { cn } from "@/lib/utils";
import { useParts, type Doc } from "./api";

/**
 * Slide by slide: each slide's text and speaker notes. ?slide=N (from a
 * citation or search hit) opens that slide. Slide pictures need server-side
 * rendering, which isn't built yet.
 */
export function DeckViewer({ doc }: { doc: Doc }) {
  const parts = useParts(doc.id, true);
  const [params, setParams] = useSearchParams();
  const slides = (parts.data ?? []).filter((p) => p.part === "slide");
  const total = slides.length;
  const wanted = Number(params.get("slide") ?? "1");
  const index = Math.min(Math.max(Number.isFinite(wanted) ? wanted : 1, 1), Math.max(total, 1)) - 1;
  const slide = slides[index];

  const go = (n: number) =>
    setParams((p) => {
      p.set("slide", String(n));
      return p;
    }, { replace: true });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement | null)?.closest("input, textarea, select")) return;
      if (e.key === "ArrowRight" && index + 1 < total) go(index + 2);
      if (e.key === "ArrowLeft" && index > 0) go(index);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (parts.isPending) return <p className="text-sm text-muted-foreground">{t("app.loading")}</p>;
  if (parts.isError || !slide) return <p className="text-sm text-muted-foreground">{t("doc.loadFailed")}</p>;

  return (
    <div className="grid grid-cols-[12rem_1fr] gap-6">
      <ol className="max-h-[70vh] space-y-1 overflow-y-auto text-sm" aria-label={doc.title}>
        {slides.map((s, i) => (
          <li key={s.number}>
            <button
              type="button"
              onClick={() => go(i + 1)}
              aria-current={i === index ? "true" : undefined}
              className={cn(
                "w-full truncate rounded px-2 py-1 text-left hover:bg-accent",
                i === index && "bg-accent font-medium",
              )}
            >
              {s.number}. {s.title || "—"}
            </button>
          </li>
        ))}
      </ol>
      <div className="space-y-4">
        <div className="flex aspect-video flex-col justify-center rounded-lg border bg-muted/30 p-10">
          <p className="text-xs text-muted-foreground">{t("doc.slideOf", { n: slide.number, total })}</p>
          <h2 className="mt-2 text-2xl font-semibold">{slide.title || "—"}</h2>
        </div>
        <div className="flex items-center justify-between">
          <Button
            variant="outline"
            size="sm"
            onClick={() => go(index)}
            disabled={index === 0}
            aria-label={t("doc.previousSlide")}
          >
            <ChevronLeft />
          </Button>
          <span className="flex items-center gap-2 text-sm text-muted-foreground">
            <span aria-live="polite">{t("doc.slideOf", { n: slide.number, total })}</span>
            <BookmarkButton docId={doc.id} part={slide.number} label={t("bookmark.slide")} />
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => go(index + 2)}
            disabled={index + 1 >= total}
            aria-label={t("doc.nextSlide")}
          >
            <ChevronRight />
          </Button>
        </div>
        <section>
          <h3 className="text-sm font-medium">{t("doc.speakerNotes")}</h3>
          <p className="mt-1 whitespace-pre-wrap text-sm">
            {slide.speaker_notes || <span className="text-muted-foreground">{t("doc.noNotes")}</span>}
          </p>
        </section>
        <p className="text-xs text-muted-foreground">{t("doc.slideImagesLater")}</p>
      </div>
    </div>
  );
}
