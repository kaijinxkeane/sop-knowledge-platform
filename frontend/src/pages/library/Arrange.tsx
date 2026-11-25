import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp } from "lucide-react";
import { useState, type ReactNode } from "react";
import { api, unwrap } from "@/api/client";
import { call, messageOf } from "@/api/errors";
import { useMe } from "@/auth/hooks";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import type { Doc } from "./api";

const ORDER = ["library", "order"] as const;

/** Hand-arranged positions (ids only, for documents you can read). */
export const useProgrammeOrder = () =>
  useQuery({ queryKey: ORDER, queryFn: () => unwrap(api.GET("/api/v1/library/order")) });

/** Arranged documents first, in their order; the rest after, by title. */
export function arranged(docs: Doc[], order: { document_id: string; position: number }[] | undefined): Doc[] {
  const at = new Map((order ?? []).map((o) => [o.document_id, o.position]));
  return [...docs].sort((a, b) => {
    const pa = at.get(a.id) ?? Infinity;
    const pb = at.get(b.id) ?? Infinity;
    return pa !== pb ? pa - pb : a.title.localeCompare(b.title);
  });
}

/**
 * One stage of a programme. People who can contribute in the department of
 * every document listed may arrange them; the order is the same for everyone.
 */
export function StageSection({
  title,
  docs,
  programme,
  stage,
  row,
}: {
  title: ReactNode;
  docs: Doc[];
  programme: string | null;
  stage: string | null;
  row: (d: Doc) => ReactNode;
}) {
  const me = useMe();
  const order = useProgrammeOrder();
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Doc[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (ids: string[]) =>
      call(api.PUT("/api/v1/library/order", { body: { programme: programme!, stage, document_ids: ids } })),
    onSettled: () => qc.invalidateQueries({ queryKey: ORDER }),
  });
  const items = arranged(docs, order.data);
  const canArrange =
    !!programme &&
    items.length > 1 &&
    items.every((d) => !!d.space && (me.data?.space_actions[d.space] ?? []).includes("contribute"));
  const move = (i: number, by: number) =>
    setDraft((list) => {
      const next = [...(list ?? items)];
      const [d] = next.splice(i, 1);
      next.splice(i + by, 0, d!);
      return next;
    });
  return (
    <section>
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium capitalize text-muted-foreground">{title}</h3>
        {canArrange && !draft && (
          <Button variant="link" size="sm" className="h-auto px-0 text-xs" onClick={() => setDraft(items)}>
            {t("library.arrange")}
          </Button>
        )}
      </div>
      {draft ? (
        <div className="space-y-2">
          <ol className="divide-y rounded-md border" aria-label={t("library.arrangeList")}>
            {draft.map((d, i) => (
              <li key={d.id} className="flex items-center gap-2 px-2 py-1.5 text-sm">
                <span className="w-5 text-right text-xs text-muted-foreground">{i + 1}</span>
                <span className="flex-1">{d.title}</span>
                <Button size="icon" variant="ghost" className="size-7" disabled={i === 0} onClick={() => move(i, -1)} aria-label={t("library.moveUp", { title: d.title })}>
                  <ArrowUp className="size-4" aria-hidden />
                </Button>
                <Button size="icon" variant="ghost" className="size-7" disabled={i === draft.length - 1} onClick={() => move(i, 1)} aria-label={t("library.moveDown", { title: d.title })}>
                  <ArrowDown className="size-4" aria-hidden />
                </Button>
              </li>
            ))}
          </ol>
          {error && <Alert>{error}</Alert>}
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={save.isPending}
              onClick={async () => {
                setError(null);
                try {
                  await save.mutateAsync(draft.map((d) => d.id));
                  setDraft(null);
                } catch (e) {
                  setError(messageOf(e));
                }
              }}
            >
              {t("library.arrangeSave")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>{t("common.cancel")}</Button>
          </div>
          <p className="text-xs text-muted-foreground">{t("library.arrangeExplain")}</p>
        </div>
      ) : (
        <ul className="divide-y">{items.map(row)}</ul>
      )}
    </section>
  );
}
