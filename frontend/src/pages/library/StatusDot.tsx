import { t, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";
import type { Doc } from "./api";

/** Approved, changes waiting (editors only see this), draft, not reviewed or retired. */
export function docStatus(doc: Doc): { key: MessageKey; dot: string } {
  if (doc.status === "retired") return { key: "doc.retired", dot: "bg-muted-foreground/40" };
  if (doc.pending_change) return { key: "doc.pending", dot: "bg-amber-500" };
  if (doc.approved) return { key: "doc.approved", dot: "bg-emerald-600" };
  if (doc.status === "draft") return { key: "doc.draft", dot: "bg-sky-500" };
  return { key: "doc.unreviewed", dot: "border border-muted-foreground bg-transparent" };
}

export function StatusDot({ doc, withLabel = false }: { doc: Doc; withLabel?: boolean }) {
  const { key, dot } = docStatus(doc);
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden="true" className={cn("inline-block size-2 rounded-full", dot)} />
      {withLabel ? (
        <span className="text-xs text-muted-foreground">{t(key)}</span>
      ) : (
        <span className="sr-only">{t(key)}</span>
      )}
    </span>
  );
}
