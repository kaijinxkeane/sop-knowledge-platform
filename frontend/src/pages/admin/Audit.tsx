import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, type Schemas } from "@/api/client";
import { call, messageOf } from "@/api/errors";
import { Loading } from "@/app/routes";
import { useMe } from "@/auth/hooks";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { t } from "@/i18n";
import { useUsers } from "./api";
import { actionText, detailRows, targetText } from "./auditText";

type Event = Schemas["AuditOut"];
type Filter = { action: string; since: string; until: string; target: string; limit: number };

// Known event names, offered as suggestions (any name can still be typed).
const ACTIONS = [
  "account_locked", "attachment_uploaded", "audit_verified", "audit_viewed", "classification_approved",
  "classification_rejected", "conflict_dismissed", "conversation_hidden", "document_classified", "gap_report_viewed",
  "gap_topic_status", "grant_added", "grant_removed", "handover_acknowledged", "handover_created", "handover_sent",
  "handover_updated", "handover_viewed", "invite_issued", "login_failed", "login_succeeded", "logout", "names_reviewed",
  "note_created", "note_saved", "notice_acknowledged", "password_set", "project_closed", "project_created",
  "project_member_removed", "project_members_added", "project_renewed", "project_share_approved",
  "project_share_declined", "project_share_requested", "project_share_revoked", "project_updated",
  "question_answered", "reading_acknowledged", "reading_assigned", "reading_unassigned", "refresh_token_reuse", "retention_applied", "retraction_applied", "review_changes_requested",
  "review_requested", "role_created", "role_deleted", "role_updated", "sop_approved", "sop_requested", "sop_retired",
  "totp_enrolled", "totp_reset", "unattributed_changes", "user_created", "user_unlocked", "user_updated",
];

const iso = (d: string) => (d ? new Date(`${d}T00:00:00`).toISOString() : undefined);

function useAudit(f: Filter) {
  return useQuery({
    queryKey: ["admin", "audit", f],
    queryFn: () =>
      call(
        api.GET("/api/v1/admin/audit", {
          params: {
            query: {
              action: f.action || undefined,
              target_id: f.target || undefined,
              since: iso(f.since),
              until: iso(f.until),
              limit: f.limit,
            },
          },
        }),
      ),
    staleTime: 0,
  });
}

/**
 * CSV for people first (plain-words columns), then the raw record unchanged
 * for auditors and tools. Every cell is quoted; formula-looking cells are
 * neutralised for spreadsheets.
 */
export function toCsv(
  rows: Event[],
  name: (id: string | null | undefined) => string,
  nameOf: (id: string) => string | undefined = () => undefined,
): string {
  const cell = (v: unknown) => {
    let s = typeof v === "string" ? v : v == null ? "" : JSON.stringify(v);
    if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`;
    return `"${s.replace(/"/g, '""')}"`;
  };
  const when = (ts: string) => new Date(ts).toLocaleString([], { dateStyle: "medium", timeStyle: "medium" });
  const readable = (e: Event) =>
    detailRows(e.details, nameOf)
      .map((r) => `${r.label}: ${r.value}`)
      .join("; ");
  const head = [
    t("audit.csvNumber"), t("audit.when"), t("audit.who"), t("audit.what"), t("audit.csvTarget"), t("audit.details"),
    "ts", "actor_id", "action", "target_type", "target_id", "details_raw",
  ];
  const lines = rows.map((e) =>
    [
      e.id, when(e.ts), name(e.actor_id), actionText(e.action), targetText(e.target_type, e.target_id, nameOf) ?? "", readable(e),
      e.ts, e.actor_id, e.action, e.target_type, e.target_id, e.details,
    ].map(cell).join(","),
  );
  return [head.map(cell).join(","), ...lines].join("\r\n");
}

function download(text: string, filename: string) {
  const url = URL.createObjectURL(new Blob(["\uFEFF", text], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

function AuditDetails({ details, nameOf }: { details: Record<string, unknown>; nameOf: (id: string) => string | undefined }) {
  const rows = detailRows(details, nameOf);
  if (!rows.length) return null;
  return (
    <div className="space-y-1">
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
        {rows.map((r) => (
          <div key={r.label} className="contents">
            <dt className="text-muted-foreground">{r.label}</dt>
            <dd className="break-words">{r.value}</dd>
          </div>
        ))}
      </dl>
      <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer">{t("audit.raw")}</summary>
        <code className="block break-all font-mono">{JSON.stringify(details)}</code>
      </details>
    </div>
  );
}

/** Admin → Audit log: search, export and chain verification (view_audit). */
export default function Audit() {
  const me = useMe();
  const canManage = !!me.data?.global_actions.includes("manage_users");
  const users = useUsers(canManage);
  const [draft, setDraft] = useState<Filter>({ action: "", since: "", until: "", target: "", limit: 100 });
  const [filter, setFilter] = useState(draft);
  const events = useAudit(filter);
  const [chain, setChain] = useState<Schemas["ChainOut"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const names = new Map((users.data ?? []).map((u) => [u.id, u.display_name]));
  const name = (id: string | null | undefined) => (id ? (names.get(id) ?? id.slice(0, 8)) : t("audit.system"));
  const nameOf = (id: string) => names.get(id);

  const search = (e: FormEvent) => {
    e.preventDefault();
    setFilter(draft);
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("audit.note")}</p>
      <form onSubmit={search} className="grid grid-cols-[1fr_10rem_10rem_1fr_6rem_auto] items-end gap-2">
        <div className="space-y-1">
          <Label htmlFor="audit-action">{t("audit.action")}</Label>
          <Input id="audit-action" list="audit-actions" placeholder={t("audit.anyAction")} maxLength={64} value={draft.action} onChange={(e) => setDraft({ ...draft, action: e.target.value.trim() })} />
          <datalist id="audit-actions">{ACTIONS.map((a) => <option key={a} value={a} label={actionText(a)} />)}</datalist>
        </div>
        <div className="space-y-1">
          <Label htmlFor="audit-since">{t("audit.since")}</Label>
          <Input id="audit-since" type="date" value={draft.since} onChange={(e) => setDraft({ ...draft, since: e.target.value })} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="audit-until">{t("audit.until")}</Label>
          <Input id="audit-until" type="date" value={draft.until} onChange={(e) => setDraft({ ...draft, until: e.target.value })} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="audit-target">{t("audit.target")}</Label>
          <Input id="audit-target" maxLength={64} value={draft.target} onChange={(e) => setDraft({ ...draft, target: e.target.value.trim() })} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="audit-limit">{t("audit.limit")}</Label>
          <Select id="audit-limit" value={draft.limit} onChange={(e) => setDraft({ ...draft, limit: Number(e.target.value) })}>
            {[100, 500, 1000].map((n) => <option key={n} value={n}>{n}</option>)}
          </Select>
        </div>
        <Button type="submit">{t("audit.search")}</Button>
      </form>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!events.data?.length}
          onClick={() => download(toCsv(events.data ?? [], name, nameOf), `audit-${new Date().toISOString().slice(0, 10)}.csv`)}
        >
          {t("audit.export")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={async () => {
            setError(null);
            try {
              setChain(await call(api.GET("/api/v1/admin/audit/verify")));
            } catch (e) {
              setError(messageOf(e));
            }
          }}
        >
          {t("audit.verify")}
        </Button>
      </div>
      {chain &&
        (chain.ok ? (
          <p role="status" className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-900">
            {t("audit.verifyOk", { n: chain.events })}
          </p>
        ) : (
          <Alert>{t("audit.verifyBad", { id: chain.first_bad_id ?? "?" })}</Alert>
        ))}
      {error && <Alert>{error}</Alert>}
      {events.isPending ? <Loading /> : events.isError ? <Alert>{messageOf(events.error)}</Alert> : events.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("audit.empty")}</p>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">#</th>
                <th className="px-3 py-2 font-medium">{t("audit.when")}</th>
                <th className="px-3 py-2 font-medium">{t("audit.who")}</th>
                <th className="px-3 py-2 font-medium">{t("audit.what")}</th>
                <th className="px-3 py-2 font-medium">{t("audit.details")}</th>
              </tr>
            </thead>
            <tbody>
              {events.data.map((e) => (
                <tr key={e.id} className="border-t align-top">
                  <td className="px-3 py-1.5 text-xs text-muted-foreground">{e.id}</td>
                  <td className="whitespace-nowrap px-3 py-1.5">{new Date(e.ts).toLocaleString([], { dateStyle: "medium", timeStyle: "medium" })}</td>
                  <td className="px-3 py-1.5">{name(e.actor_id)}</td>
                  <td className="px-3 py-1.5">
                    <span className="font-medium" title={e.action}>{actionText(e.action)}</span>
                    {(e.target_type || e.target_id) && (
                      <span className="block text-xs text-muted-foreground">{targetText(e.target_type, e.target_id, nameOf)}</span>
                    )}
                  </td>
                  <td className="px-3 py-1.5">
                    <AuditDetails details={e.details} nameOf={nameOf} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
