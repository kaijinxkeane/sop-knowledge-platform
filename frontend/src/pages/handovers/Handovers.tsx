import { useState } from "react";
import { Link, useParams } from "react-router";
import { messageOf } from "@/api/errors";
import { Loading } from "@/app/routes";
import { useMe } from "@/auth/hooks";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { t, type MessageKey } from "@/i18n";
import { useDocuments } from "@/pages/library/api";
import { NoteView } from "@/pages/library/NoteView";
import { NotFound } from "@/pages/NotFound";
import { placeFor } from "@/lib/places";
import { useComments, useHandover, useHandoverActions, useHandovers, type Handover, type Issue } from "./api";

const day = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";

const statusLabel = (s: string) =>
  ["draft", "sent", "acknowledged"].includes(s) ? t(`handover.status.${s}` as MessageKey) : s;

function Row({ h }: { h: Handover }) {
  const acked = h.receivers.filter((r) => r.acknowledged_at).length;
  return (
    <li className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
      <Link to={`/handovers/${h.id}`} className="font-medium hover:underline">{h.title}</Link>
      <span className="flex items-center gap-2 text-xs text-muted-foreground">
        {t("handover.by", { name: h.author })} · {acked}/{h.receivers.length}
        <Badge variant={h.status === "draft" ? "outline" : "default"}>{statusLabel(h.status)}</Badge>
      </span>
    </li>
  );
}

function Section({ title, items }: { title: string; items: Handover[] }) {
  if (!items.length) return null;
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-medium text-muted-foreground">{title}</h2>
      <ul className="divide-y rounded-md border">{items.map((h) => <Row key={h.id} h={h} />)}</ul>
    </section>
  );
}

/** Handover notes: mine, awaiting my acknowledgement, and others I may read (leads, CEO). */
export function HandoverList() {
  const me = useMe();
  const list = useHandovers();
  const canWrite = Object.values(me.data?.space_actions ?? {}).some((a) => a.includes("contribute"));
  if (list.isPending) return <Loading />;
  if (list.isError) return <p role="alert" className="p-6 text-sm">{t("error.generic")}</p>;
  const myId = me.data?.id;
  const awaiting = list.data.filter((h) => h.status !== "draft" && h.receivers.some((r) => r.user_id === myId && !r.acknowledged_at));
  const mine = list.data.filter((h) => h.mine);
  const others = list.data.filter((h) => !h.mine && !awaiting.includes(h));
  return (
    <div className="mx-auto max-w-4xl space-y-6 px-6 py-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t("handover.title")}</h1>
        {canWrite && <Button asChild><Link to="/handovers/new">{t("handover.new")}</Link></Button>}
      </div>
      {list.data.length === 0 && <p className="text-sm text-muted-foreground">{t("handover.empty")}</p>}
      <Section title={t("handover.awaiting")} items={awaiting} />
      <Section title={t("handover.mine")} items={mine} />
      <Section title={t("handover.others")} items={others} />
    </div>
  );
}

function Issues({ issues }: { issues: Issue[] }) {
  if (!issues.length) return <p role="status" className="text-sm text-green-800">{t("handover.checkOk")}</p>;
  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
      <p className="font-medium">{t("handover.issues")}</p>
      <ul className="mt-1 list-disc pl-5">
        {issues.map((i, k) => <li key={k}><span className="font-medium">{i.section}:</span> {i.message}</li>)}
      </ul>
    </div>
  );
}

function Comments({ id }: { id: string }) {
  const comments = useComments(id);
  const { comment } = useHandoverActions();
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <Card>
      <CardHeader className="pb-3"><h2 className="font-semibold">{t("handover.comments")}</h2></CardHeader>
      <CardContent className="space-y-3">
        {comments.data?.length ? (
          <ul className="space-y-2">
            {comments.data.map((c) => (
              <li key={c.id} className="text-sm">
                <p className="text-xs text-muted-foreground">{c.author} · {day(c.created_at)}</p>
                <p className="whitespace-pre-wrap">{c.body}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{t("handover.noComments")}</p>
        )}
        <form
          className="space-y-2"
          onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            try {
              await comment.mutateAsync({ id, body });
              setBody("");
            } catch (err) {
              setError(messageOf(err));
            }
          }}
        >
          <textarea
            aria-label={t("handover.commentPlaceholder")}
            placeholder={t("handover.commentPlaceholder")}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            rows={2}
            maxLength={4000}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          {error && <Alert>{error}</Alert>}
          <Button type="submit" size="sm" disabled={!body.trim() || comment.isPending}>{t("handover.post")}</Button>
        </form>
      </CardContent>
    </Card>
  );
}

export function HandoverView() {
  const { id = "" } = useParams();
  const me = useMe();
  const h = useHandover(id);
  const docs = useDocuments();
  const actions = useHandoverActions();
  const [issues, setIssues] = useState<Issue[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  if (h.isPending) return <Loading />;
  if (h.isError) return <NotFound />;
  const d = h.data;
  const mineAsReceiver = d.receivers.find((r) => r.user_id === me.data?.id);
  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(messageOf(e));
    }
  };

  return (
    <div className="mx-auto grid max-w-6xl grid-cols-[1fr_20rem] gap-6 px-6 py-6">
      <div className="space-y-4">
        <Link to={placeFor("handovers", "/handovers")} className="text-sm text-muted-foreground hover:text-foreground">← {t("handover.title")}</Link>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">{d.title}</h1>
          <Badge variant={d.status === "draft" ? "outline" : "default"}>{statusLabel(d.status)}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">{t("handover.by", { name: d.author })} · {d.space}</p>
        {d.mine && (
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm"><Link to={`/handovers/${d.id}/edit`}>{t("handover.edit")}</Link></Button>
            <Button
              variant="outline"
              size="sm"
              disabled={actions.check.isPending}
              onClick={() => run(async () => setIssues(await actions.check.mutateAsync(d.id)))}
            >
              {actions.check.isPending ? t("app.loading") : t("handover.check")}
            </Button>
            {d.status === "draft" && (
              <Button size="sm" disabled={actions.send.isPending} onClick={() => run(async () => (await actions.send.mutateAsync(d.id), setNotice(t("handover.sent"))))}>
                {t("handover.send")}
              </Button>
            )}
          </div>
        )}
        {notice && <p role="status" className="text-sm">{notice}</p>}
        {error && <Alert>{error}</Alert>}
        {d.mine && <Issues issues={issues ?? d.issues} />}
        {mineAsReceiver && d.status !== "draft" && !mineAsReceiver.acknowledged_at && (
          <Button onClick={() => run(() => actions.acknowledge.mutateAsync(d.id))} disabled={actions.acknowledge.isPending}>
            {t("handover.acknowledge")}
          </Button>
        )}
        <article className="rounded-md border p-6">
          <NoteView text={d.markdown} docs={docs.data ?? []} />
        </article>
      </div>
      <aside className="space-y-4">
        <Card>
          <CardHeader className="pb-3"><h2 className="font-semibold">{t("handover.receivers")}</h2></CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {d.receivers.map((r) => (
                <li key={r.user_id} className="flex justify-between gap-2">
                  <span>{r.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {r.acknowledged_at ? t("handover.acknowledged", { date: day(r.acknowledged_at) }) : t("handover.waiting")}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Comments id={d.id} />
      </aside>
    </div>
  );
}
