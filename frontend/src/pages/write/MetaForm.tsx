import { useMe } from "@/auth/hooks";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { rank, SENSITIVITIES, type Meta } from "@/editor/meta";
import { TEMPLATE_NAMES } from "@/editor/templates";
import { t } from "@/i18n";
import { plainName } from "@/lib/obsidian";
import { useDocuments, useStages, type Doc } from "@/pages/library/api";

export const DOC_TYPES = [...new Set([...TEMPLATE_NAMES, "policy", "guide", "deck"])];

/** True when choosing `next` would loosen access and so needs the space lead (one-way rule). */
export function needsApproval(current: string, next: string, canApprove: boolean): boolean {
  return !canApprove && rank(next) < rank(current);
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id} className="text-xs text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  );
}

/** Metadata is a form, not YAML (frontend spec §6). Status and approval stay read-only. */
export function MetaForm({ meta, onChange, doc }: { meta: Meta; onChange: (m: Meta) => void; doc?: Doc }) {
  const me = useMe();
  const docs = useDocuments();
  const stages = useStages();
  const set = (k: keyof Meta) => (e: { target: { value: string } }) => onChange({ ...meta, [k]: e.target.value });
  const programmes = [...new Set((docs.data ?? []).map((d) => plainName(d.programme)).filter(Boolean))] as string[];
  const owners = [...new Set((docs.data ?? []).map((d) => plainName(d.owner)).filter(Boolean))] as string[];
  const space = doc?.access[0]?.space ?? null;
  // The level in force now: the tightest of the note's rows.
  const current = doc?.access.length
    ? SENSITIVITIES[Math.max(...doc.access.map((a) => rank(a.sensitivity)))]!
    : "internal";
  const canApprove = !!space && !!me.data?.space_actions[space]?.includes("approve");
  const chosen = meta.sensitivity || current;

  return (
    <fieldset className="grid grid-cols-2 gap-3 rounded-md border p-3 md:grid-cols-4">
      <legend className="px-1 text-xs text-muted-foreground">{t("write.details")}</legend>
      <Field id="meta-title" label={t("write.titleField")}>
        <Input id="meta-title" value={meta.title} maxLength={150} onChange={set("title")} />
      </Field>
      <Field id="meta-type" label={t("doc.type")}>
        <Select id="meta-type" value={meta.doc_type} onChange={set("doc_type")}>
          {[...new Set([meta.doc_type, ...DOC_TYPES])].filter(Boolean).map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </Select>
      </Field>
      <Field id="meta-owner" label={t("doc.owner")}>
        <Input id="meta-owner" list="meta-owners" value={meta.owner} onChange={set("owner")} />
        <datalist id="meta-owners">{owners.map((o) => <option key={o} value={o} />)}</datalist>
      </Field>
      <Field id="meta-programme" label={t("doc.programme")}>
        <Input id="meta-programme" list="meta-programmes" value={meta.programme} onChange={set("programme")} />
        <datalist id="meta-programmes">{programmes.map((p) => <option key={p} value={p} />)}</datalist>
      </Field>
      <Field id="meta-stage" label={t("doc.stage")}>
        <Select id="meta-stage" value={meta.stage} onChange={set("stage")}>
          <option value="">{t("common.none")}</option>
          {(stages.data ?? []).map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </Select>
      </Field>
      <Field id="meta-review" label={t("write.reviewEvery")}>
        <Select id="meta-review" value={meta.review_cycle_days} onChange={set("review_cycle_days")}>
          <option value="">{t("common.none")}</option>
          {[...new Set(["90", "180", "365", meta.review_cycle_days].filter(Boolean))].map((d) => (
            <option key={d} value={d}>{t("write.days", { n: d })}</option>
          ))}
        </Select>
      </Field>
      <Field id="meta-space" label={t("write.space")}>
        <Input id="meta-space" value={space ?? t("write.fromFolder")} readOnly disabled />
      </Field>
      <Field id="meta-sensitivity" label={t("write.sensitivity")}>
        <Select id="meta-sensitivity" value={chosen} onChange={set("sensitivity")}>
          {SENSITIVITIES.map((s) => (
            <option key={s} value={s}>{t(`sensitivity.${s}`)}</option>
          ))}
        </Select>
        {needsApproval(current, chosen, canApprove) && (
          <p className="text-xs text-amber-700">{t("write.needsLead")}</p>
        )}
      </Field>
    </fieldset>
  );
}
