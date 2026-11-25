import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { messageOf } from "@/api/errors";
import { useMe } from "@/auth/hooks";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { TEMPLATE_NAMES, templateBody, type Template } from "@/editor/templates";
import { t } from "@/i18n";
import { plainName } from "@/lib/obsidian";
import { useDocuments, useStages } from "@/pages/library/api";
import { createNote, useAfterSave, useSimilarNotes } from "./api";
import { spaceLabel } from "@/lib/spaceLabel";

/**
 * A new note starts from its template. Started from a gap, the URL carries the
 * programme, stage and related notes (`?programme=&stage=&related=`).
 */
export default function NewNote() {
  const me = useMe();
  const docs = useDocuments();
  const stages = useStages();
  const navigate = useNavigate();
  const afterSave = useAfterSave();
  const [params] = useSearchParams();
  const spaces = Object.entries(me.data?.space_actions ?? {})
    .filter(([, actions]) => actions.includes("contribute"))
    .map(([s]) => s)
    .sort();
  const [title, setTitle] = useState(params.get("title") ?? "");
  const [space, setSpace] = useState(
    me.data?.home_space && spaces.includes(me.data.home_space) ? me.data.home_space : (spaces[0] ?? ""),
  );
  const [sensitivity, setSensitivity] = useState("internal");
  const [kind, setKind] = useState<Template>("sop");
  const [programme, setProgramme] = useState(params.get("programme") ?? "");
  const [stage, setStage] = useState(params.get("stage") ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const programmes = [...new Set((docs.data ?? []).map((d) => plainName(d.programme)).filter(Boolean))] as string[];
  const related = params.getAll("related").slice(0, 10);
  const [settled, setSettled] = useState("");
  useEffect(() => {
    const id = window.setTimeout(() => setSettled(title.trim()), 600);
    return () => window.clearTimeout(id);
  }, [title]);
  const similar = useSimilarNotes(settled);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const out = await createNote({
        title: title.trim(),
        space,
        sensitivity,
        doc_type: kind,
        programme: programme.trim() ? `[[${programme.trim()}]]` : null,
        stage: stage || null,
        body: templateBody(kind, title, related),
      });
      afterSave(out.id);
      navigate(`/write/${out.id}`, { replace: true });
    } catch (err) {
      setError(messageOf(err));
      setBusy(false);
    }
  }

  if (!spaces.length) return <p className="p-6 text-sm">{t("write.noSpaces")}</p>;
  return (
    <form onSubmit={submit} className="mx-auto max-w-xl space-y-4 px-6 py-6">
      <h1 className="text-2xl font-semibold">{t("write.newTitle")}</h1>
      <div className="space-y-1">
        <Label htmlFor="new-title">{t("write.titleField")}</Label>
        <Input id="new-title" required maxLength={150} value={title} onChange={(e) => setTitle(e.target.value)} />
        {(similar.data?.length ?? 0) > 0 && (
          <div role="status" className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
            <p className="font-medium">{t("write.similarTitle")}</p>
            <ul className="mt-1 space-y-0.5">
              {similar.data!.map((n) => (
                <li key={n.id}>
                  <Link to={`/library/${n.id}`} className="underline-offset-2 hover:underline">{n.title}</Link>
                  <span className="text-xs text-muted-foreground"> · {n.folder}</span>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-xs text-muted-foreground">{t("write.similarHint")}</p>
          </div>
        )}
      </div>
      <div className="space-y-1">
        <Label htmlFor="new-template">{t("write.template")}</Label>
        <Select id="new-template" value={kind} onChange={(e) => setKind(e.target.value as Template)}>
          {TEMPLATE_NAMES.map((k) => (
            <option key={k} value={k}>{t(`template.${k}`)}</option>
          ))}
        </Select>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="new-space">{t("write.space")}</Label>
          <Select id="new-space" value={space} onChange={(e) => setSpace(e.target.value)}>
            {spaces.map((s) => (
              <option key={s} value={s}>{spaceLabel(s)}</option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="new-sensitivity">{t("write.sensitivity")}</Label>
          <Select id="new-sensitivity" value={sensitivity} onChange={(e) => setSensitivity(e.target.value)}>
            {(["public", "internal", "restricted"] as const).map((s) => (
              <option key={s} value={s}>{t(`sensitivity.${s}`)}</option>
            ))}
          </Select>
          {sensitivity === "public" && !me.data?.space_actions[space]?.includes("approve") && (
            <p className="text-xs text-amber-700">{t("write.needsLead")}</p>
          )}
        </div>
        <div className="space-y-1">
          <Label htmlFor="new-programme">{t("doc.programme")}</Label>
          <Input id="new-programme" list="new-programmes" value={programme} onChange={(e) => setProgramme(e.target.value)} />
          <datalist id="new-programmes">{programmes.map((p) => <option key={p} value={p} />)}</datalist>
        </div>
        <div className="space-y-1">
          <Label htmlFor="new-stage">{t("doc.stage")}</Label>
          <Select id="new-stage" value={stage} onChange={(e) => setStage(e.target.value)}>
            <option value="">{t("common.none")}</option>
            {(stages.data ?? []).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </Select>
        </div>
      </div>
      {related.length > 0 && (
        <p className="text-xs text-muted-foreground">{t("write.relatedAdded", { count: related.length })}</p>
      )}
      {error && <Alert>{error}</Alert>}
      <Button type="submit" disabled={busy || !title.trim()}>
        {busy ? t("common.saving") : t("write.create")}
      </Button>
    </form>
  );
}
