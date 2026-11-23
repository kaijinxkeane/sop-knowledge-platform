import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { clashCount, resolve, type Choice, type Part } from "@/editor/merge";

/** Theirs vs yours, chosen per block (frontend spec §6). */
export function MergeDialog({
  parts,
  busy,
  onSave,
  onCancel,
}: {
  parts: Part[];
  busy: boolean;
  onSave: (merged: string) => void;
  onCancel: () => void;
}) {
  const clashes = clashCount(parts);
  const [choices, setChoices] = useState<Choice[]>(() => new Array<Choice>(clashes).fill("mine"));
  let k = -1;
  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="max-w-4xl">
        <DialogTitle>{t("merge.title")}</DialogTitle>
        <DialogDescription>
          {clashes ? t("merge.someClash", { count: clashes }) : t("merge.noClash")}
        </DialogDescription>
        {clashes > 0 && (
          <ol className="space-y-4">
            {parts.map((p, i) => {
              if (p.kind !== "clash") return null;
              const n = ++k;
              return (
                <li key={i} className="space-y-2">
                  <div className="text-sm font-medium">{t("merge.block", { n: n + 1 })}</div>
                  <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-label={t("merge.block", { n: n + 1 })}>
                    {(["theirs", "mine"] as const).map((side) => (
                      <label
                        key={side}
                        className={cn(
                          "cursor-pointer rounded-md border p-2",
                          choices[n] === side && "border-primary ring-1 ring-primary",
                        )}
                      >
                        <span className="flex items-center gap-2 text-xs font-medium">
                          <input
                            type="radio"
                            name={`clash-${n}`}
                            checked={choices[n] === side}
                            onChange={() => setChoices((c) => c.map((v, j) => (j === n ? side : v)))}
                          />
                          {side === "theirs" ? t("merge.theirs") : t("merge.yours")}
                        </span>
                        <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-xs">
                          {(side === "theirs" ? p.theirs : p.mine) || t("merge.removed")}
                        </pre>
                      </label>
                    ))}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => onSave(resolve(parts, choices))} disabled={busy}>
            {busy ? t("common.saving") : t("merge.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
