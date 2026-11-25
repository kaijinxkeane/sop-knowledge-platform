import { Fragment, useState } from "react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { fold, type Row } from "@/lib/diff";
import { cn } from "@/lib/utils";

/** Two texts side by side, unchanged runs folded (Library compare, Review). */
function Cell({ no, text, kind }: { no?: number; text?: string; kind: "left" | "right" | "blank"; }) {
  return (
    <>
      <td className="w-10 select-none pr-2 text-right align-top text-xs text-muted-foreground">{no ?? ""}</td>
      <td className={cn("whitespace-pre-wrap break-words px-2 align-top font-mono text-xs", kind === "blank" && "bg-muted/40")}>
        {text ?? ""}
      </td>
    </>
  );
}

const TONE: Record<Row["kind"], [string, string]> = {
  same: ["", ""],
  changed: ["bg-red-50", "bg-green-50"],
  removed: ["bg-red-50", ""],
  added: ["", "bg-green-50"],
};

export function DiffTable({ rows }: { rows: Row[] }) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  const shown = fold(rows);
  return (
    <table className="w-full table-fixed border-collapse text-sm">
      <colgroup>
        <col className="w-10" /><col /><col className="w-10" /><col />
      </colgroup>
      <tbody>
        {shown.map((s, i) =>
          "hidden" in s && !open.has(s.from) ? (
            <tr key={`h${i}`}>
              <td colSpan={4} className="py-1 text-center">
                <Button variant="link" size="sm" onClick={() => setOpen((o) => new Set(o).add(s.from))}>
                  {t("compare.unchanged", { count: s.hidden })}
                </Button>
              </td>
            </tr>
          ) : (
            <Fragment key={`r${i}`}>
              {("hidden" in s ? rows.slice(s.from, s.from + s.hidden) : s.rows).map((r, k) => {
                const [l, rt] = TONE[r.kind];
                return (
                  <tr key={k} data-kind={r.kind} className="border-b border-border/40">
                    <td colSpan={2} className={cn("p-0", l)}>
                      <table className="w-full"><tbody><tr>
                        {r.kind === "added" ? <Cell kind="blank" /> : <Cell no={r.leftNo} text={r.left} kind="left" />}
                      </tr></tbody></table>
                    </td>
                    <td colSpan={2} className={cn("p-0", rt)}>
                      <table className="w-full"><tbody><tr>
                        {r.kind === "removed" ? <Cell kind="blank" /> : <Cell no={r.rightNo} text={r.right} kind="right" />}
                      </tr></tbody></table>
                    </td>
                  </tr>
                );
              })}
            </Fragment>
          ),
        )}
      </tbody>
    </table>
  );
}

