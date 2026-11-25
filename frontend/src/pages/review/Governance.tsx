import { Link } from "react-router";
import { Loading } from "@/app/routes";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { t, type MessageKey } from "@/i18n";
import { useGovernance, type Governance as Report, type GovernanceItem } from "./api";

const LISTS = [
  "changes_awaiting_review",
  "review_overdue",
  "self_approved",
  "unattributed_edits",
  "never_approved",
  "published_outside_platform",
  "possible_instructions",
] as const satisfies readonly (keyof Report)[];

const day = (iso: unknown) =>
  typeof iso === "string" ? new Date(iso).toLocaleDateString([], { dateStyle: "medium" }) : "";

function detail(kind: (typeof LISTS)[number], d: Record<string, unknown>): string {
  if (kind === "changes_awaiting_review") return d.submitted ? t("gov.submitted") : "";
  if (kind === "review_overdue") return day(d.due);
  if (kind === "self_approved" || kind === "unattributed_edits") return day(d.at);
  return "";
}

function Item({ kind, item }: { kind: (typeof LISTS)[number]; item: GovernanceItem }) {
  const extra = detail(kind, item.detail ?? {});
  return (
    <li className="flex items-baseline justify-between gap-3 text-sm">
      {/* Titles come only for documents this reader may open; otherwise an id-less placeholder. */}
      {item.title ? (
        <Link to={`/library/${item.document_id}`} className="underline-offset-2 hover:underline">{item.title}</Link>
      ) : (
        <span className="italic text-muted-foreground">{t("gov.hidden")}</span>
      )}
      <span className="shrink-0 text-xs text-muted-foreground">
        {[item.space, extra].filter(Boolean).join(" · ")}
      </span>
    </li>
  );
}

function AccessChange({ c }: { c: Record<string, unknown> }) {
  const str = (v: unknown) => (Array.isArray(v) ? v.join(", ") : typeof v === "string" ? v : "");
  const grant = (c.grant ?? {}) as Record<string, unknown>;
  return (
    <li className="text-sm">
      {c.action === "grant_added"
        ? t("gov.accessGrant", { by: str(c.by), role: str(c.role), space: str(grant.space), when: day(c.at) })
        : t("gov.accessRole", {
            by: str(c.by),
            person: str(c.person),
            roles: str(c.roles_added),
            spaces: str(c.spaces),
            when: day(c.at),
          })}
    </li>
  );
}

/** Review → Governance: the lead's (or auditor's) report, quiet lists, no alerts. */
export function Governance() {
  const report = useGovernance(true);
  if (report.isPending) return <Loading />;
  if (report.isError) return <p role="alert" className="text-sm">{t("error.generic")}</p>;
  const r = report.data;
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("gov.spaces", { list: r.spaces.join(", ") })}</p>
      <div className="grid gap-4 lg:grid-cols-2">
        {LISTS.map((kind) => (
          <Card key={kind}>
            <CardHeader className="pb-3">
              <h2 className="font-semibold">
                {t(`gov.${kind}` as MessageKey)} <span className="font-normal text-muted-foreground">({r[kind].length})</span>
              </h2>
            </CardHeader>
            <CardContent>
              {r[kind].length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("gov.none")}</p>
              ) : (
                <ul className="space-y-1">{r[kind].map((item, i) => <Item key={`${item.document_id}${i}`} kind={kind} item={item} />)}</ul>
              )}
            </CardContent>
          </Card>
        ))}
        <Card>
          <CardHeader className="pb-3">
            <h2 className="font-semibold">
              {t("gov.access_changes")} <span className="font-normal text-muted-foreground">({r.access_changes?.length ?? 0})</span>
            </h2>
          </CardHeader>
          <CardContent>
            {!r.access_changes?.length ? (
              <p className="text-sm text-muted-foreground">{t("gov.none")}</p>
            ) : (
              <ul className="space-y-1">{r.access_changes.map((c, i) => <AccessChange key={i} c={c} />)}</ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
