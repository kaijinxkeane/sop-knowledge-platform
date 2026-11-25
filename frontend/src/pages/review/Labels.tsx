import { useState } from "react";
import { Link } from "react-router";
import { messageOf } from "@/api/errors";
import { Loading } from "@/app/routes";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { t, type MessageKey } from "@/i18n";
import { useLabelActions, useQueue, useSpaces, widens, type Group, type Labels, type Proposal } from "./api";

const SENSITIVITIES = ["public", "internal", "restricted"] as const;
const level = (s: string) =>
  (SENSITIVITIES as readonly string[]).includes(s) ? t(`sensitivity.${s}` as MessageKey) : t("sensitivity.restricted");

export function labelText(l: Labels): string {
  const main = `${l.space} · ${level(l.sensitivity)}`;
  const shared = (l.shared_with ?? []).map((s) => `${s.space} · ${level(s.sensitivity)}`);
  return shared.length ? `${main} (${t("labels.sharedWith", { list: shared.join(", ") })})` : main;
}

function EditLabels({ p, onDone }: { p: Proposal; onDone: () => void }) {
  const spaces = useSpaces();
  const { approve } = useLabelActions();
  const [space, setSpace] = useState(p.proposed?.space ?? "");
  const [sensitivity, setSensitivity] = useState(p.proposed?.sensitivity ?? "restricted");
  const [error, setError] = useState<string | null>(null);
  // Personal data or unconfirmed names: only restricted can be approved (backend rule).
  const locked = p.safeguards.length > 0 || p.names.length > 0;
  const next: Labels = { space, sensitivity, shared_with: p.proposed?.shared_with ?? [] };
  return (
    <form
      className="mt-3 space-y-3 rounded-md border bg-muted/30 p-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          await approve.mutateAsync({ id: p.id, edit: next });
          onDone();
        } catch (err) {
          setError(messageOf(err));
        }
      }}
    >
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor={`space-${p.id}`}>{t("labels.space")}</Label>
          <Select id={`space-${p.id}`} value={space} onChange={(e) => setSpace(e.target.value)} required>
            <option value="" disabled>—</option>
            {(spaces.data ?? []).map((s) => (
              <option key={s.name} value={s.name}>{s.title}</option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor={`sens-${p.id}`}>{t("labels.sensitivity")}</Label>
          <Select id={`sens-${p.id}`} value={sensitivity} onChange={(e) => setSensitivity(e.target.value)}>
            {SENSITIVITIES.map((s) => (
              <option key={s} value={s} disabled={locked && s !== "restricted"}>{level(s)}</option>
            ))}
          </Select>
        </div>
      </div>
      {space && <WidensLine current={p.current} next={next} />}
      {error && <Alert>{error}</Alert>}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={!space || approve.isPending}>{t("labels.save")}</Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>{t("common.cancel")}</Button>
      </div>
    </form>
  );
}

function WidensLine({ current, next }: { current?: Labels | null; next?: Labels | null }) {
  return widens(current, next) ? (
    <p className="text-sm font-medium text-amber-900">{t("labels.widens")}</p>
  ) : (
    <p className="text-sm text-muted-foreground">{t("labels.narrows")}</p>
  );
}

function ProposalCard({ p }: { p: Proposal }) {
  const { approve, reject } = useLabelActions();
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busy = approve.isPending || reject.isPending;
  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(messageOf(e));
    }
  };
  return (
    <li className="space-y-2 border-t pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center gap-2">
        {p.current ? (
          <Link to={`/library/${p.document_id}`} className="font-medium underline-offset-2 hover:underline">{p.title}</Link>
        ) : (
          <span className="font-medium">{p.title}</span>
        )}
        <span className="text-xs text-muted-foreground">{p.vault_path}</span>
        <Badge variant="outline">{t("labels.confidence", { n: Math.round(p.confidence * 100) })}</Badge>
        {p.needs === "approve" && <Badge>{t("labels.needsLead")}</Badge>}
        {p.stale && <Badge variant="warning">{t("labels.stale")}</Badge>}
      </div>
      <p className="text-sm">
        {p.current ? t("labels.current", { labels: labelText(p.current) }) : t("labels.currentNone")}
        {" → "}
        {p.proposed ? t("labels.proposed", { labels: labelText(p.proposed) }) : t("labels.unsure")}
      </p>
      {p.proposed && <WidensLine current={p.current} next={p.proposed} />}
      {p.decision === "forwarded" && <p className="text-sm text-muted-foreground">{t("labels.forwarded")}</p>}
      {p.safeguards.length > 0 && <Alert>{t("labels.safeguards", { list: p.safeguards.join(", ") })}</Alert>}
      {p.names.length > 0 && (
        <p className="text-sm text-amber-900">{t("labels.names", { list: p.names.join(", ") })}</p>
      )}
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground">{t("labels.reasoning")}</summary>
        {/* The rationale and quotes are note content: shown as plain text only. */}
        <p className="mt-1 whitespace-pre-wrap">{p.rationale}</p>
        {p.evidence.length > 0 && (
          <>
            <p className="mt-2 font-medium">{t("labels.evidence")}</p>
            <ul className="mt-1 space-y-1">
              {p.evidence.map((e, i) => (
                <li key={i}><blockquote className="border-l-2 pl-2 text-muted-foreground">{e}</blockquote></li>
              ))}
            </ul>
          </>
        )}
      </details>
      {error && <Alert>{error}</Alert>}
      {editing ? (
        <EditLabels p={p} onDone={() => setEditing(false)} />
      ) : (
        <div className="flex gap-2">
          <Button size="sm" disabled={busy || p.stale || !p.proposed} onClick={() => act(() => approve.mutateAsync({ id: p.id }))}>
            {t("labels.approve")}
          </Button>
          <Button size="sm" variant="outline" disabled={busy || p.stale} onClick={() => setEditing(true)}>
            {t("labels.edit")}
          </Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(() => reject.mutateAsync(p.id))}>
            {t("labels.reject")}
          </Button>
        </div>
      )}
    </li>
  );
}

function GroupCard({ g, items }: { g: Group; items: Proposal[] }) {
  const { bulk } = useLabelActions();
  const [result, setResult] = useState<string[] | null>(null);
  const ready = items.filter((p) => !p.stale && p.proposed);
  const anyWidens = ready.some((p) => widens(p.current, p.proposed));
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3 space-y-0 pb-3">
        <div>
          <h2 className="font-semibold">{t("labels.group", { count: items.length, folder: g.folder || "/" })}</h2>
          <p className="text-sm text-muted-foreground">
            {g.proposed_space
              ? t("labels.groupTarget", { space: g.proposed_space, sensitivity: level(g.proposed_sensitivity) })
              : t("labels.unsure")}
          </p>
        </div>
        {ready.length > 1 && (
          <Button
            size="sm"
            variant={anyWidens ? "outline" : "default"}
            disabled={bulk.isPending}
            onClick={async () => {
              try {
                const out = await bulk.mutateAsync(ready.map((p) => p.id));
                const title = new Map(ready.map((p) => [p.id, p.title]));
                const failed = out.filter((r) => !r.ok);
                setResult([
                  t("labels.bulkDone", { ok: out.length - failed.length, failed: failed.length }),
                  ...failed.map((r) => t("labels.bulkFailed", { title: title.get(r.id) ?? "", error: r.error ?? "" })),
                ]);
              } catch (e) {
                setResult([messageOf(e)]);
              }
            }}
          >
            {anyWidens ? t("labels.approveAllWidens") : t("labels.approveAll")}
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {result && (
          <ul role="status" className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
            {result.map((line, i) => <li key={i}>{line}</li>)}
          </ul>
        )}
        <ul className="space-y-3">
          {items.map((p) => <ProposalCard key={p.id} p={p} />)}
        </ul>
      </CardContent>
    </Card>
  );
}

/**
 * Review → AI label suggestions (notes that already have labels) or Unplaced
 * notes (no labels yet, so nobody can read them). Same queue, split in two.
 */
export function LabelQueue({ unplaced }: { unplaced: boolean }) {
  const queue = useQueue();
  if (queue.isPending) return <Loading />;
  if (queue.isError) return <p role="alert" className="text-sm">{t("error.generic")}</p>;
  const groups = queue.data
    .map((g) => ({ g, items: g.items.filter((p) => (p.current == null) === unplaced) }))
    .filter((x) => x.items.length > 0);
  return (
    <div className="space-y-4">
      {unplaced && <p className="text-sm text-muted-foreground">{t("labels.unplacedExplain")}</p>}
      {groups.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t(unplaced ? "review.empty.unplaced" : "review.empty.labels")}</p>
      ) : (
        groups.map(({ g, items }) => <GroupCard key={g.group_key} g={g} items={items} />)
      )}
    </div>
  );
}
