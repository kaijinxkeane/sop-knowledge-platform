import { Link } from "react-router";
import { useMe } from "@/auth/hooks";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { useDocuments } from "@/pages/library/api";
import { StatusDot } from "@/pages/library/StatusDot";

/** Write home: start a note, or carry on with drafts and unreviewed changes. */
export default function Write() {
  const me = useMe();
  const docs = useDocuments();
  const canEdit = (spaces: string[]) => spaces.some((s) => me.data?.space_actions[s]?.includes("contribute"));
  const open = (docs.data ?? []).filter(
    (d) =>
      d.kind === "note" &&
      (d.status === "draft" || d.status === "in_review" || d.pending_change) &&
      canEdit(d.access.map((a) => a.space)),
  );
  return (
    <div className="mx-auto max-w-3xl space-y-6 px-6 py-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t("nav.write")}</h1>
        <Button asChild>
          <Link to="/write/new">{t("write.newTitle")}</Link>
        </Button>
      </div>
      <section>
        <h2 className="text-sm font-medium text-muted-foreground">{t("write.inProgress")}</h2>
        {docs.isPending ? (
          <p className="text-sm text-muted-foreground">{t("app.loading")}</p>
        ) : open.length ? (
          <ul className="divide-y">
            {open.map((d) => (
              <li key={d.id} className="flex items-center gap-3 py-2">
                <StatusDot doc={d} />
                <Link to={`/write/${d.id}`} className="font-medium hover:underline">
                  {d.title}
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{t("write.nothingOpen")}</p>
        )}
      </section>
    </div>
  );
}
