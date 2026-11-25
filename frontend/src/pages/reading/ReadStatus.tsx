import { Link } from "react-router";
import { Loading } from "@/app/routes";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { shortDate, useReadStatus, useReadingActions, type DocStatus } from "./api";

/** One CSV for the yearly audit: SOP, version, person, status, dates. */
function toCsv(rows: DocStatus[]): string {
  const cell = (v: string | number | null | undefined) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = [["SOP", "Current version", "Person", "Read version", "Read on", "Due", "Overdue", "Can read"]];
  for (const d of rows) {
    for (const p of d.people) {
      lines.push([
        d.title,
        String(d.current_version ?? ""),
        p.name,
        String(p.version ?? ""),
        p.acknowledged_at ?? "",
        p.due_on ?? "",
        p.overdue ? "yes" : "no",
        p.can_read ? "yes" : "no",
      ]);
    }
  }
  return lines.map((l) => l.map(cell).join(",")).join("\n");
}

function download(rows: DocStatus[]) {
  const url = URL.createObjectURL(new Blob([toCsv(rows)], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `read-status-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

/** Retain → Required reading (leads): who has or hasn't read each assigned SOP. */
export function ReadStatus() {
  const report = useReadStatus(true);
  const { unassign } = useReadingActions();
  if (report.isPending) return <Loading />;
  if (report.isError) return <p role="alert" className="text-sm">{t("error.generic")}</p>;
  const rows = report.data;
  if (!rows.length) return <p className="text-sm text-muted-foreground">{t("reading.reportEmpty")}</p>;
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">{t("reading.reportExplain")}</p>
        <Button size="sm" variant="outline" onClick={() => download(rows)}>{t("reading.export")}</Button>
      </div>
      {rows.map((d) => {
        const done = d.people.filter((p) => p.acknowledged_at).length;
        return (
          <section key={d.document_id} aria-label={d.title} className="rounded-lg border p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <Link to={`/library/${d.document_id}`} className="font-medium hover:underline">{d.title}</Link>
              <span className="text-sm text-muted-foreground">
                {t("reading.progress", { done, total: d.people.length, version: d.current_version ?? "—" })}
              </span>
            </div>
            <ul className="mt-2 flex flex-wrap gap-2 text-xs">
              {d.assignments.map((a) => (
                <li key={a.id} className="flex items-center gap-1 rounded-full border py-0.5 pl-2 pr-1">
                  {a.target}
                  {a.due_on && <span className="text-muted-foreground">· {shortDate(a.due_on)}</span>}
                  <button
                    type="button"
                    className="rounded-full px-1 text-muted-foreground hover:text-foreground"
                    aria-label={t("reading.unassign", { target: a.target })}
                    disabled={unassign.isPending}
                    onClick={() => unassign.mutate(a.id)}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
            <table className="mt-3 w-full text-sm">
              <tbody>
                {d.people.map((p) => (
                  <tr key={p.name} className="border-t">
                    <td className="py-1.5 pr-3">{p.name}</td>
                    <td className="py-1.5 pr-3">
                      {p.acknowledged_at ? (
                        t("reading.readOn", { version: p.version ?? "", date: shortDate(p.acknowledged_at) })
                      ) : p.overdue ? (
                        <Badge variant="danger">{t("reading.overdueShort")}</Badge>
                      ) : (
                        <span className="text-muted-foreground">{t("reading.notYet")}</span>
                      )}
                    </td>
                    <td className="py-1.5 text-right">
                      {!p.can_read && <Badge variant="warning">{t("reading.cannotRead")}</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        );
      })}
    </div>
  );
}
