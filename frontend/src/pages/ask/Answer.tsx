import { Check, Copy, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { messageOf } from "@/api/errors";
import { useMe } from "@/auth/hooks";
import { visibleSections } from "@/auth/permissions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { t, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";
import { AnswerText, plainWikiLinks } from "./AnswerText";
import { myGaps, requestSop, sendFeedback, type Citation, type Reason, type Section } from "./api";
import { spaceLabel } from "@/lib/spaceLabel";

const REASONS: Reason[] = ["wrong", "outdated", "missing_steps", "unclear", "other"];

function Sources({ citations, onCite }: { citations: Citation[]; onCite: (c: Citation) => void }) {
  if (!citations.length) return null;
  return (
    <ol className="mt-2 space-y-0.5 text-xs text-muted-foreground">
      {citations.map((c) => (
        <li key={c.n}>
          <button type="button" className="text-left hover:text-foreground hover:underline" onClick={() => onCite(c)}>
            [{c.n}] {c.title}
            {c.part === "slide" && c.part_number ? ` · ${t("library.slide", { n: c.part_number })}` : ""}
            {c.part === "page" && c.part_number ? ` · ${t("library.page", { n: c.part_number })}` : ""}
            {c.heading ? ` · ${c.heading}` : ""}
          </button>
        </li>
      ))}
    </ol>
  );
}

/** "No SOP you can access covers this", never dressed up as an answer, with three ways on. */
function NoAnswer({ question, questionId, space, contact }: { question: string; questionId: string | null; space: string | null; contact?: string | null }) {
  const me = useMe();
  const canWrite = me.data ? visibleSections(me.data).includes("write") : false;
  const [requested, setRequested] = useState<"idle" | "busy" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const [experts, setExperts] = useState<string[] | null>(null);
  return (
    <div className="space-y-2 rounded-md border border-dashed p-3 text-sm">
      <p className="font-medium">{t("ask.noAnswer")}</p>
      {contact && <p className="text-muted-foreground">{contact}</p>}
      <div className="flex flex-wrap gap-2">
        {questionId && space && (
          <Button
            variant="outline"
            size="sm"
            disabled={requested !== "idle"}
            onClick={() => {
              setRequested("busy");
              requestSop(questionId, space)
                .then(() => setRequested("done"))
                .catch((e) => {
                  setRequested("idle");
                  setError(messageOf(e));
                });
            }}
          >
            {requested === "done" ? t("ask.requested") : t("ask.requestSop")}
          </Button>
        )}
        {canWrite && (
          <Button asChild variant="outline" size="sm">
            <Link to={`/write/new?title=${encodeURIComponent(question.slice(0, 150))}`}>{t("ask.startDraft")}</Link>
          </Button>
        )}
        {questionId && (
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              myGaps()
                .then((gaps) => setExperts(gaps.find((g) => g.key.split(",").includes(questionId))?.experts ?? []))
                .catch(() => setExperts([]))
            }
          >
            {t("ask.suggestExpert")}
          </Button>
        )}
      </div>
      {experts && (
        <p role="status" className="text-muted-foreground">
          {experts.length ? t("ask.experts", { names: experts.join(", ") }) : t("ask.noExperts")}
        </p>
      )}
      {error && <p role="alert" className="text-destructive">{error}</p>}
    </div>
  );
}

function Feedback({ messageId }: { messageId: string }) {
  const [state, setState] = useState<"none" | "up" | "asking" | "down">("none");
  const [reason, setReason] = useState<Reason | null>(null);
  const [comment, setComment] = useState("");
  const send = (helpful: boolean, r?: Reason) =>
    sendFeedback(messageId, helpful, r, helpful ? "" : comment.trim()).catch(() => undefined);
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("ask.helpful")}
          aria-pressed={state === "up"}
          onClick={() => {
            setState("up");
            void send(true);
          }}
        >
          <ThumbsUp className={cn(state === "up" && "fill-current")} />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t("ask.notHelpful")}
          aria-pressed={state === "asking" || state === "down"}
          onClick={() => setState("asking")}
        >
          <ThumbsDown className={cn((state === "asking" || state === "down") && "fill-current")} />
        </Button>
        {state === "up" && <span className="text-xs text-muted-foreground">{t("library.thanks")}</span>}
        {state === "down" && <span className="text-xs text-muted-foreground">{t("ask.feedbackThanks")}</span>}
      </div>
      {state === "asking" && (
        <div className="space-y-2 rounded-md border p-2">
          <div role="radiogroup" aria-label={t("ask.whyNot")} className="flex flex-wrap gap-1">
            {REASONS.map((r) => (
              <button
                key={r}
                type="button"
                role="radio"
                aria-checked={reason === r}
                onClick={() => setReason(r)}
                className={cn("rounded-full border px-2 py-0.5 text-xs", reason === r && "border-primary bg-accent")}
              >
                {t(`ask.reason.${r}` as MessageKey)}
              </button>
            ))}
          </div>
          <Input
            aria-label={t("ask.comment")}
            placeholder={t("ask.comment")}
            maxLength={1000}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <Button
            size="sm"
            disabled={!reason}
            onClick={() => {
              setState("down");
              void send(false, reason!);
            }}
          >
            {t("ask.sendFeedback")}
          </Button>
        </div>
      )}
    </div>
  );
}

function copyText(sections: Section[]): string {
  const parts: string[] = [];
  for (const s of sections) {
    if (s.no_answer || s.unavailable || s.hidden) continue;
    parts.push(plainWikiLinks(s.text).trim());
    if (s.citations.length)
      parts.push(s.citations.map((c) => `[${c.n}] ${c.title}${c.heading ? ` — ${c.heading}` : ""}`).join("\n"));
  }
  return parts.join("\n\n");
}

export type AnswerProps = {
  sections: Section[];
  fallback?: string; // shown when there are no sections (e.g. no spaces yet)
  titles: Record<string, string>;
  question: string;
  questionId: string | null;
  messageId: string | null;
  streaming?: boolean;
  onCite: (c: Citation) => void;
};

/** One answer: a section per department (nothing merged by a model), with its own sources. */
export function Answer({ sections, fallback, titles, question, questionId, messageId, streaming, onCite }: AnswerProps) {
  const [copied, setCopied] = useState(false);
  const answered = sections.filter((s) => !s.no_answer && !s.unavailable && !s.hidden);
  const noAnswer = !streaming && sections.length > 0 && sections.every((s) => s.no_answer);
  const several = sections.length > 1;
  return (
    <div className="space-y-4">
      {!sections.length && fallback && <p className="text-sm">{fallback}</p>}
      {noAnswer ? (
        <NoAnswer
          question={question}
          questionId={questionId}
          space={sections[0]!.space}
          contact={sections.find((s) => s.contact)?.contact}
        />
      ) : (
        sections.map((s, i) => (
          <section key={`${s.space}-${i}`} aria-label={s.space ? titles[s.space] ?? s.space : undefined}>
            {several && s.space && <h3 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">{titles[s.space] ?? spaceLabel(s.space)}</h3>}
            {s.unavailable ? (
              <p className="text-sm">
                {t("ask.unavailable")}{" "}
                <Link className="underline" to={`/library?q=${encodeURIComponent(question)}`}>
                  {t("ask.searchLibrary")}
                </Link>
              </p>
            ) : s.hidden ? (
              <p className="text-sm italic text-muted-foreground">{s.text}</p>
            ) : s.no_answer ? null : (
              <>
                <AnswerText text={s.text} citations={s.citations} onCite={onCite} />
                <Sources citations={s.citations} onCite={onCite} />
              </>
            )}
          </section>
        ))
      )}
      {!streaming && messageId && answered.length > 0 && (
        <div className="flex flex-wrap items-start gap-2">
          <Feedback messageId={messageId} />
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              void navigator.clipboard?.writeText(copyText(sections)).then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              })
            }
          >
            {copied ? <Check /> : <Copy />}
            {copied ? t("common.copied") : t("common.copy")}
          </Button>
        </div>
      )}
    </div>
  );
}
