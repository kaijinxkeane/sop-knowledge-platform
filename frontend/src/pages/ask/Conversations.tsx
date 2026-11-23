import { useQueryClient } from "@tanstack/react-query";
import { Check, EyeOff, Pencil, Plus, Search, X } from "lucide-react";
import { useDeferredValue, useState } from "react";
import { Link } from "react-router";
import { messageOf } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { hideConversation, renameConversation, useConversations, type Conversation } from "./api";

type Group = "today" | "yesterday" | "week" | "earlier";
const GROUPS: Group[] = ["today", "yesterday", "week", "earlier"];

export function dayGroup(iso: string, now = new Date()): Group {
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  const day = new Date(iso);
  day.setHours(0, 0, 0, 0);
  const days = (start.getTime() - day.getTime()) / 86_400_000;
  return days <= 0 ? "today" : days <= 1 ? "yesterday" : days <= 7 ? "week" : "earlier";
}

function Row({ c, current, onHidden }: { c: Conversation; current: boolean; onHidden: () => void }) {
  const qc = useQueryClient();
  const [mode, setMode] = useState<"view" | "rename" | "hide">("view");
  const [title, setTitle] = useState(c.title);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["conversations"] });

  if (mode === "rename")
    return (
      <form
        className="flex items-center gap-1 px-1"
        onSubmit={(e) => {
          e.preventDefault();
          if (!title.trim()) return;
          renameConversation(c.id, title.trim())
            .then(() => {
              setMode("view");
              void refresh();
            })
            .catch((err) => setError(messageOf(err)));
        }}
      >
        <Input
          autoFocus
          aria-label={t("ask.renameLabel")}
          className="h-7 text-sm"
          maxLength={120}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Escape" && setMode("view")}
        />
        <Button type="submit" variant="ghost" size="icon" aria-label={t("common.save")} disabled={!title.trim()}>
          <Check />
        </Button>
        {error && <span role="alert" className="sr-only">{error}</span>}
      </form>
    );

  if (mode === "hide")
    return (
      <div role="alertdialog" aria-label={t("ask.hideTitle")} className="space-y-2 rounded-md border p-2 text-xs">
        <p>{t("ask.hideExplain")}</p>
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() =>
              hideConversation(c.id)
                .then(async () => {
                  await refresh();
                  if (current) onHidden();
                })
                .catch((err) => setError(messageOf(err)))
            }
          >
            {t("ask.hide")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setMode("view")}>
            {t("common.cancel")}
          </Button>
        </div>
        {error && <p role="alert" className="text-destructive">{error}</p>}
      </div>
    );

  return (
    <div className="group flex items-center rounded hover:bg-accent">
      <Link
        to={`/ask?conversation=${c.id}`}
        aria-current={current ? "page" : undefined}
        className={cn("min-w-0 flex-1 truncate px-2 py-1 text-sm", current && "font-medium")}
      >
        {c.title || t("bookmark.untitled")}
      </Link>
      <span className="hidden shrink-0 group-focus-within:flex group-hover:flex">
        <Button
          variant="ghost"
          size="icon"
          className="size-6"
          aria-label={t("ask.rename", { title: c.title })}
          onClick={() => {
            setTitle(c.title);
            setMode("rename");
          }}
        >
          <Pencil className="size-3" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="size-6"
          aria-label={t("ask.hideOne", { title: c.title })}
          onClick={() => setMode("hide")}
        >
          <EyeOff className="size-3" />
        </Button>
      </span>
    </div>
  );
}

/** History grouped by day, searchable; rename and hide (frontend spec §4). */
export function ConversationList({
  current,
  onNew,
}: {
  current: string | null;
  onNew: () => void;
}) {
  const [q, setQ] = useState("");
  const query = useDeferredValue(q.trim().length >= 2 ? q.trim() : "");
  const convs = useConversations(query);
  const groups = new Map<Group, Conversation[]>();
  for (const c of convs.data ?? []) {
    const g = dayGroup(c.updated_at);
    groups.set(g, [...(groups.get(g) ?? []), c]);
  }
  return (
    <nav aria-label={t("ask.conversations")} className="flex min-h-0 flex-col gap-3 border-r p-3">
      <Button variant="outline" size="sm" className="w-full" onClick={onNew}>
        <Plus />
        {t("ask.new")}
      </Button>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2 top-2 size-3.5 text-muted-foreground" />
        <Input
          type="search"
          aria-label={t("ask.searchHistory")}
          placeholder={t("ask.searchHistory")}
          className="h-8 pl-7 pr-7 text-sm"
          maxLength={100}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {q && (
          <button
            type="button"
            aria-label={t("common.clear")}
            className="absolute right-2 top-2 text-muted-foreground hover:text-foreground"
            onClick={() => setQ("")}
          >
            <X className="size-3.5" />
          </button>
        )}
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto">
        {query && convs.data?.length === 0 && (
          <p className="px-2 text-xs text-muted-foreground">{t("ask.noMatches")}</p>
        )}
        {GROUPS.map((g) =>
          groups.get(g)?.length ? (
            <section key={g}>
              <h2 className="px-2 text-[11px] font-medium uppercase text-muted-foreground">{t(`ask.group.${g}`)}</h2>
              <ul className="mt-1 space-y-0.5">
                {groups.get(g)!.map((c) => (
                  <li key={c.id}>
                    <Row c={c} current={c.id === current} onHidden={onNew} />
                  </li>
                ))}
              </ul>
            </section>
          ) : null,
        )}
      </div>
    </nav>
  );
}
