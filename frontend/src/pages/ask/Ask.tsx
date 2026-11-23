import { useQueryClient } from "@tanstack/react-query";
import { Plus, Send, Square } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { messageOf, ServerError } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { Answer } from "./Answer";
import { CitationPanel } from "./CitationPanel";
import {
  createConversation,
  streamAnswer,
  useConversations,
  useMessages,
  useSpaces,
  type Citation,
  type Conversation,
  type Section,
  type StreamEvent,
} from "./api";

type Live = {
  question: string;
  base: number; // saved messages in this conversation when it was asked
  steps: string[];
  order: string[];
  sections: Record<string, Section & { done?: boolean }>;
  questionId: string | null;
  messageId: string | null;
  state: "working" | "done" | "stopped" | "failed";
  error?: string;
};

function dayGroup(iso: string): "today" | "yesterday" | "week" | "earlier" {
  const d = new Date(iso);
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const days = (start.getTime() - new Date(d).setHours(0, 0, 0, 0)) / 86_400_000;
  return days <= 0 ? "today" : days <= 1 ? "yesterday" : days <= 7 ? "week" : "earlier";
}

function ConversationList({ current, onNew }: { current: string | null; onNew: () => void }) {
  const convs = useConversations();
  const groups = new Map<string, Conversation[]>();
  for (const c of convs.data ?? []) {
    const g = dayGroup(c.updated_at);
    groups.set(g, [...(groups.get(g) ?? []), c]);
  }
  return (
    <nav aria-label={t("ask.conversations")} className="space-y-4 border-r p-3">
      <Button variant="outline" size="sm" className="w-full" onClick={onNew}>
        <Plus />
        {t("ask.new")}
      </Button>
      {(["today", "yesterday", "week", "earlier"] as const).map((g) =>
        groups.get(g)?.length ? (
          <section key={g}>
            <h2 className="px-2 text-[11px] font-medium uppercase text-muted-foreground">{t(`ask.group.${g}`)}</h2>
            <ul className="mt-1 space-y-0.5">
              {groups.get(g)!.map((c) => (
                <li key={c.id}>
                  <Link
                    to={`/ask?conversation=${c.id}`}
                    aria-current={c.id === current ? "page" : undefined}
                    className={cn("block truncate rounded px-2 py-1 text-sm hover:bg-accent", c.id === current && "bg-accent font-medium")}
                  >
                    {c.title || t("bookmark.untitled")}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ) : null,
      )}
    </nav>
  );
}

function apply(live: Live, e: StreamEvent, titles: Record<string, string>): Live {
  const next: Live = { ...live, sections: { ...live.sections } };
  // Copy the section before changing it (state updates stay immutable).
  const sec = (space: string) => {
    next.sections[space] = { ...(next.sections[space] ?? { space, text: "", citations: [] }) };
    if (!next.order.includes(space)) next.order = [...next.order, space];
  };
  switch (e.event) {
    case "routing":
      next.steps = [...live.steps, t("ask.step.routing")];
      break;
    case "agent_dispatched":
      next.steps = [...live.steps, t("ask.step.checking", { title: e.data.title || titles[e.data.space] || e.data.space })];
      sec(e.data.space);
      break;
    case "token":
      sec(e.data.space);
      next.sections[e.data.space]!.text += e.data.text;
      break;
    case "citation": {
      sec(e.data.space);
      const s = next.sections[e.data.space]!;
      s.citations = [...s.citations.filter((c) => c.n !== e.data.n), e.data];
      break;
    }
    case "section_done": {
      sec(e.data.space);
      Object.assign(next.sections[e.data.space]!, {
        done: true,
        no_answer: e.data.no_answer,
        unavailable: e.data.unavailable,
        contact: e.data.contact,
        confidence: e.data.confidence,
      });
      break;
    }
    case "done":
      next.state = "done";
      next.messageId = e.data.message_id;
      next.questionId = e.data.question_id;
      break;
  }
  return next;
}

/** Sections as they are shown: no-answer sections hidden once another department answered. */
function shownSections(live: Live): Section[] {
  const all = live.order.map((s) => live.sections[s]!).filter(Boolean);
  const answered = all.filter((s) => !s.no_answer);
  return live.state === "working" ? all.filter((s) => s.text || s.done) : answered.length ? answered : all;
}

export default function Ask() {
  const [params, setParams] = useSearchParams();
  const conversationId = params.get("conversation");
  const qc = useQueryClient();
  const spaces = useSpaces();
  const titles = useMemo(
    () => Object.fromEntries((spaces.data ?? []).map((s) => [s.name, s.title])),
    [spaces.data],
  );
  const messages = useMessages(conversationId);
  const [live, setLive] = useState<Live | null>(null);
  const [draft, setDraft] = useState("");
  const [cited, setCited] = useState<Citation | null>(null);
  const abort = useRef<AbortController | null>(null);
  const started = useRef<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const working = live?.state === "working";

  async function ask(question: string) {
    const q = question.trim();
    if (q.length < 2 || working) return;
    setDraft("");
    setCited(null);
    let id = conversationId;
    const controller = new AbortController();
    abort.current = controller;
    let current: Live = {
      question: q,
      base: id ? (messages.data?.length ?? 0) : 0,
      steps: [],
      order: [],
      sections: {},
      questionId: null,
      messageId: null,
      state: "working",
    };
    setLive(current);
    try {
      if (!id) {
        id = (await createConversation()).id;
        started.current = id;
        setParams({ conversation: id }, { replace: true });
      }
      await streamAnswer(
        id,
        q,
        (e) => {
          current = apply(current, e, titles);
          setLive(current);
        },
        controller.signal,
      );
      if (current.state === "working") current = { ...current, state: "failed", error: t("ask.unavailable") };
    } catch (err) {
      current = controller.signal.aborted
        ? { ...current, state: "stopped" }
        : {
            ...current,
            state: "failed",
            error: err instanceof ServerError && err.status === 429 ? messageOf(err) : t("ask.unavailable"),
          };
    }
    setLive(current);
    abort.current = null;
    void qc.invalidateQueries({ queryKey: ["conversations"] });
    if (!id) return;
    // The question is saved before the answer starts; the stored copy replaces the live one.
    await qc.refetchQueries({ queryKey: ["conversation", id, "messages"] }).catch(() => undefined);
    // Swap in the saved copy only once it holds this answer (question + answer);
    // if the refetch failed, the live copy stays on screen.
    const saved = qc.getQueryData<unknown[]>(["conversation", id, "messages"])?.length ?? 0;
    if (current.state === "done" && saved >= current.base + 2) setLive(null);
  }

  // Asked from Home (/ask?q=...): start a conversation with it.
  const initial = params.get("q");
  useEffect(() => {
    if (initial && !conversationId && started.current === null) {
      started.current = "pending";
      void ask(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  // Switching conversations drops anything live from the previous one.
  useEffect(() => {
    if (conversationId && started.current !== conversationId) {
      abort.current?.abort();
      setLive(null);
      setCited(null);
    }
  }, [conversationId]);

  useEffect(() => bottom.current?.scrollIntoView?.({ block: "end" }), [messages.data, live]);

  const stored = messages.data ?? [];
  function submit(e: FormEvent) {
    e.preventDefault();
    void ask(draft);
  }

  return (
    <div className={cn("grid h-[calc(100vh-3.5rem)]", cited ? "grid-cols-[15rem_1fr_24rem]" : "grid-cols-[15rem_1fr]")}>
      <ConversationList
        current={conversationId}
        onNew={() => {
          abort.current?.abort();
          started.current = null;
          setLive(null);
          setCited(null);
          setParams({});
        }}
      />
      <section className="flex min-h-0 flex-col">
        <div className="flex-1 space-y-6 overflow-y-auto px-8 py-6" aria-live="polite">
          {!conversationId && !live && (
            <div className="pt-16 text-center">
              <h1 className="text-2xl font-semibold">{t("home.title")}</h1>
              <p className="mt-2 text-sm text-muted-foreground">{t("ask.intro")}</p>
            </div>
          )}
          {stored.map((m, i) =>
            m.role === "user" ? (
              <p key={m.id} className="ml-auto max-w-[80%] rounded-lg bg-accent px-3 py-2 text-sm">{m.content}</p>
            ) : (
              <Answer
                key={m.id}
                sections={m.sections as Section[]}
                fallback={m.content}
                titles={titles}
                question={stored[i - 1]?.content ?? ""}
                questionId={stored[i - 1]?.role === "user" ? stored[i - 1]!.id : null}
                messageId={m.id}
                onCite={setCited}
              />
            ),
          )}
          {live && (
            <>
              {/* While streaming, the question isn't in the stored history yet. */}
              {stored.length <= live.base && (
                <p className="ml-auto max-w-[80%] rounded-lg bg-accent px-3 py-2 text-sm">{live.question}</p>
              )}
              {working && !shownSections(live).some((s) => s.text) && (
                <ul aria-label={t("ask.progress")} className="space-y-1 text-sm text-muted-foreground">
                  {(live.steps.length ? live.steps : [t("ask.step.start")]).map((s, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span className="size-2 animate-pulse rounded-full bg-primary/60" />
                      {s}
                    </li>
                  ))}
                </ul>
              )}
              <Answer
                sections={shownSections(live)}
                titles={titles}
                question={live.question}
                questionId={live.questionId}
                messageId={live.messageId}
                streaming={working}
                onCite={setCited}
              />
              {live.state === "stopped" && <p className="text-xs text-muted-foreground">{t("ask.stopped")}</p>}
              {live.state === "failed" && (
                <p role="alert" className="text-sm">
                  {live.error}{" "}
                  <Link className="underline" to={`/library?q=${encodeURIComponent(live.question)}`}>
                    {t("ask.searchLibrary")}
                  </Link>
                </p>
              )}
            </>
          )}
          <div ref={bottom} />
        </div>
        <form onSubmit={submit} className="flex items-end gap-2 border-t p-4">
          <textarea
            aria-label={conversationId ? t("ask.followUp") : t("home.askPlaceholder")}
            placeholder={conversationId ? t("ask.followUp") : t("home.askPlaceholder")}
            value={draft}
            maxLength={2000}
            rows={2}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void ask(draft);
              }
            }}
            className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          {working ? (
            <Button type="button" variant="outline" onClick={() => abort.current?.abort()}>
              <Square />
              {t("ask.stop")}
            </Button>
          ) : (
            <Button type="submit" disabled={draft.trim().length < 2}>
              <Send />
              {t("ask.send")}
            </Button>
          )}
        </form>
      </section>
      {cited && <CitationPanel key={`${cited.document_id}-${cited.n}`} citation={cited} onClose={() => setCited(null)} />}
    </div>
  );
}
