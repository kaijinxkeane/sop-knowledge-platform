import { ArrowLeft } from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { Loading } from "@/app/routes";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { t } from "@/i18n";
import { fold, lineDiff, stats, type Row } from "@/lib/diff";
import { cn } from "@/lib/utils";
import { NotFound } from "@/pages/NotFound";
import { useDocument, useVersion, useVersions, type Version } from "./api";

export function versionLabel(v: Version): string {
  const when = new Date(v.committed_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  const tags = [v.live && t("version.live"), v.latest && !v.approved && t("version.unapproved")].filter(Boolean);
  return `${when} · ${v.author_name}${tags.length ? ` (${tags.join(", ")})` : ""}`;
}

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

function DiffTable({ rows }: { rows: Row[] }) {
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

/** Two versions of a note side by side (frontend spec §5). Only versions this
 * reader may see are offered; the backend refuses the rest with 404. */
export default function Compare() {
  const { id = "" } = useParams();
  const doc = useDocument(id);
  const versions = useVersions(id);
  const [params, setParams] = useSearchParams();
  const list = versions.data ?? [];
  const to = params.get("to") ?? list[0]?.commit ?? null;
  const toIndex = list.findIndex((v) => v.commit === to);
  const defaultFrom =
    list.find((v, i) => i > toIndex && v.live)?.commit ?? list[toIndex + 1]?.commit ?? null;
  const from = params.get("from") ?? defaultFrom;
  const left = useVersion(id, from);
  const right = useVersion(id, to);
  const rows = useMemo(
    () => (left.data && right.data ? lineDiff(left.data.content, right.data.content) : null),
    [left.data, right.data],
  );

  if (doc.isError || versions.isError) return <NotFound />;
  if (doc.isPending || versions.isPending) return <Loading />;
  const set = (k: "from" | "to", v: string) =>
    setParams((p) => {
      p.set(k, v);
      if (k === "to" && !p.get("from") && from) p.set("from", from);
      return p;
    }, { replace: true });
  const s = rows ? stats(rows) : null;

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-6 py-6">
      <Link to={`/library/${id}`} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" />
        {doc.data.title}
      </Link>
      <h1 className="text-2xl font-semibold">{t("compare.title")}</h1>
      {doc.data.kind !== "note" && <p className="text-sm text-muted-foreground">{t("compare.textOnly")}</p>}
      {list.length < 2 ? (
        <p className="text-sm text-muted-foreground">{t("compare.onlyOne")}</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4">
            {(["from", "to"] as const).map((k) => (
              <div key={k} className="space-y-1">
                <Label htmlFor={`compare-${k}`}>{k === "from" ? t("compare.older") : t("compare.newer")}</Label>
                <Select id={`compare-${k}`} value={(k === "from" ? from : to) ?? ""} onChange={(e) => set(k, e.target.value)}>
                  {list.map((v) => (
                    <option key={v.commit} value={v.commit}>{versionLabel(v)}</option>
                  ))}
                </Select>
              </div>
            ))}
          </div>
          {left.isError || right.isError ? (
            <p role="alert" className="text-sm">{t("compare.unavailable")}</p>
          ) : !rows ? (
            <Loading />
          ) : (
            <>
              <p className="text-sm text-muted-foreground" role="status">
                {s!.added + s!.removed + s!.changed === 0
                  ? t("compare.same")
                  : t("compare.stats", { added: s!.added, removed: s!.removed, changed: s!.changed })}
              </p>
              <div className="overflow-x-auto rounded-md border"><DiffTable rows={rows} /></div>
            </>
          )}
        </>
      )}
    </div>
  );
}
