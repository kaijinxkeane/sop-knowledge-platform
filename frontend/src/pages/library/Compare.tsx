import { ArrowLeft } from "lucide-react";
import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { Loading } from "@/app/routes";
import { DiffTable } from "@/components/DiffTable";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { t } from "@/i18n";
import { lineDiff, stats } from "@/lib/diff";
import { NotFound } from "@/pages/NotFound";
import { useDocument, useVersion, useVersions, type Version } from "./api";

export function versionLabel(v: Version): string {
  const when = new Date(v.committed_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  const tags = [v.live && t("version.live"), v.latest && !v.approved && t("version.unapproved")].filter(Boolean);
  return `${when} · ${v.author_name}${tags.length ? ` (${tags.join(", ")})` : ""}`;
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
