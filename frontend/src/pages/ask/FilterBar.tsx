import { t } from "@/i18n";
import { plainName } from "@/lib/obsidian";
import { useDocuments, useStages } from "@/pages/library/api";
import type { Filters } from "./api";

const SELECT =
  "h-8 rounded-md border bg-background px-2 text-xs text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** Programme and stage filters: options come from what you can read. */
export function FilterBar({ value, onChange }: { value: Filters; onChange: (f: Filters) => void }) {
  const docs = useDocuments();
  const stages = useStages();
  const programmes = [...new Set((docs.data ?? []).map((d) => d.programme).filter((p): p is string => !!p))].sort(
    (a, b) => (plainName(a) ?? a).localeCompare(plainName(b) ?? b),
  );
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        aria-label={t("ask.filter.programme")}
        className={SELECT}
        value={value.programme ?? ""}
        onChange={(e) => onChange({ ...value, programme: e.target.value || null })}
      >
        <option value="">{t("ask.filter.anyProgramme")}</option>
        {programmes.map((p) => (
          <option key={p} value={p}>
            {plainName(p)}
          </option>
        ))}
      </select>
      <select
        aria-label={t("ask.filter.stage")}
        className={SELECT}
        value={value.stage ?? ""}
        onChange={(e) => onChange({ ...value, stage: e.target.value || null })}
      >
        <option value="">{t("ask.filter.anyStage")}</option>
        {(stages.data ?? []).map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
    </div>
  );
}

/** Filters as URL params (Home → Ask, and kept while you move between conversations). */
export function filtersFrom(params: URLSearchParams): Filters {
  return { programme: params.get("programme"), stage: params.get("stage") };
}

export function filterQuery(f: Filters): string {
  const p = new URLSearchParams();
  if (f.programme) p.set("programme", f.programme);
  if (f.stage) p.set("stage", f.stage);
  const s = p.toString();
  return s ? `&${s}` : "";
}
