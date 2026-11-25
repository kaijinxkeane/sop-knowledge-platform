import { Fragment, useMemo, useState } from "react";
import { DiffTable } from "@/components/DiffTable";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { t } from "@/i18n";
import { blockDiff, detailChanges } from "@/lib/blockDiff";
import { fold, lineDiff, stats, type Row } from "@/lib/diff";
import { cn } from "@/lib/utils";
import { useDocuments } from "@/pages/library/api";
import { NoteView } from "@/pages/library/NoteView";

type Mode = "formatted" | "source";

/**
 * Two versions of a note (Library compare, Review). "Formatted" shows the note
 * the way it reads, with removed parts struck through in red and added parts
 * in green, like tracked changes; "Source" is the exact text, line by line.
 */
export function VersionDiff({ before, after, formatted = true }: { before: string; after: string; formatted?: boolean }) {
  const [mode, setMode] = useState<Mode>(formatted ? "formatted" : "source");
  const lines = useMemo(() => lineDiff(before, after), [before, after]);
  const s = stats(lines);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground" role="status">
          {s.added + s.removed + s.changed === 0
            ? t("compare.same")
            : t("compare.stats", { added: s.added, removed: s.removed, changed: s.changed })}
        </p>
        <div role="group" aria-label={t("compare.view")} className="inline-flex rounded-md border p-0.5">
          {(["formatted", "source"] as const).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={mode === m}
              onClick={() => setMode(m)}
              className={cn("rounded px-3 py-1 text-sm", mode === m ? "bg-accent font-medium" : "text-muted-foreground")}
            >
              {t(m === "formatted" ? "compare.formatted" : "compare.source")}
            </button>
          ))}
        </div>
      </div>
      {mode === "formatted" ? (
        <Formatted before={before} after={after} />
      ) : (
        <div className="overflow-x-auto rounded-md border"><DiffTable rows={lines} /></div>
      )}
    </div>
  );
}

function Formatted({ before, after }: { before: string; after: string }) {
  const docs = useDocuments().data ?? [];
  const rows = useMemo(() => blockDiff(before, after), [before, after]);
  const details = useMemo(() => detailChanges(before, after), [before, after]);
  const [onlyChanges, setOnlyChanges] = useState(false);
  const [open, setOpen] = useState<Set<number>>(new Set());

  const block = (text: string, kind: "same" | "removed" | "added", key: string) =>
    kind === "same" ? (
      <NoteView key={key} text={text} docs={docs} />
    ) : (
      <div key={key} data-change={kind} className={cn("sop-change", kind === "removed" ? "sop-change-removed" : "sop-change-added")}>
        <span className="sr-only">{t(kind === "removed" ? "compare.removedBlock" : "compare.addedBlock")}</span>
        <NoteView text={text} docs={docs} />
      </div>
    );
  const render = (r: Row, k: string) => (
    <Fragment key={k}>
      {r.kind === "same" && block(r.right, "same", `${k}s`)}
      {(r.kind === "removed" || r.kind === "changed") && block(r.left, "removed", `${k}r`)}
      {(r.kind === "added" || r.kind === "changed") && block(r.right, "added", `${k}a`)}
    </Fragment>
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5"><span className="sop-change-key sop-change-removed" />{t("compare.keyRemoved")}</span>
        <span className="inline-flex items-center gap-1.5"><span className="sop-change-key sop-change-added" />{t("compare.keyAdded")}</span>
        <Checkbox
          id="compare-only-changes"
          checked={onlyChanges}
          onChange={(e) => setOnlyChanges(e.target.checked)}
          label={t("compare.onlyChanges")}
        />
      </div>
      {details.length > 0 && (
        <div className="rounded-md border bg-muted/30 px-4 py-3 text-sm">
          <p className="mb-1 font-medium">{t("compare.detailsChanged")}</p>
          <ul className="space-y-0.5">
            {details.map((d) => (
              <li key={d.key}>
                <span className="text-muted-foreground">{d.key}: </span>
                {d.before !== null && <del className="sop-change-removed-text">{d.before || t("common.none")}</del>}
                {d.before !== null && d.after !== null && " → "}
                {d.after !== null && <ins className="sop-change-added-text">{d.after || t("common.none")}</ins>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <article className="rounded-md border px-6 py-4">
        {onlyChanges
          ? fold(rows, 1).map((f, i) =>
              "hidden" in f && !open.has(f.from) ? (
                <div key={`h${i}`} className="my-2 text-center">
                  <Button variant="link" size="sm" onClick={() => setOpen((o) => new Set(o).add(f.from))}>
                    {t("compare.unchangedBlocks", { count: f.hidden })}
                  </Button>
                </div>
              ) : (
                ("hidden" in f ? rows.slice(f.from, f.from + f.hidden) : f.rows).map((r, k) => render(r, `${i}-${k}`))
              ),
            )
          : rows.map((r, i) => render(r, String(i)))}
        {rows.length === 0 && <p className="text-sm text-muted-foreground">{t("compare.empty")}</p>}
      </article>
    </div>
  );
}
