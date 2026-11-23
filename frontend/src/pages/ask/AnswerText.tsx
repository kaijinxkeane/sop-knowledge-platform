import { createContext, useContext, useMemo, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation } from "./api";

const CITE = "sop-cite:";

/** "[1]" markers become links to the citation (outside code spans and blocks). */
export function markCitations(text: string): string {
  return text
    .split(/(```[\s\S]*?```|`[^`\n]*`)/)
    .map((part, i) => (i % 2 ? part : part.replace(/\[(\d{1,2})\](?!\()/g, `[$1](${CITE}$1)`)))
    .join("");
}

type Ctx = { byN: Map<number, Citation>; onCite: (c: Citation) => void };
const CiteContext = createContext<Ctx>({ byN: new Map(), onCite: () => undefined });

/**
 * One stable component for every link in an answer. (A new function per
 * render would make React re-create each citation button on every streamed
 * word, losing focus and clicks.)
 */
function AnswerLink({ href, children }: { href?: string; children?: ReactNode }) {
  const { byN, onCite } = useContext(CiteContext);
  const n = href?.startsWith(CITE) ? Number(href.slice(CITE.length)) : NaN;
  const c = byN.get(n);
  if (!c) return <span>{children}</span>;
  const where = [c.title, c.heading, c.part_number && `${c.part} ${c.part_number}`].filter(Boolean).join(" · ");
  return (
    <button
      type="button"
      onClick={() => onCite(c)}
      title={where}
      aria-label={`Source ${n}: ${where}`}
      className="mx-0.5 rounded bg-accent px-1 align-baseline text-xs font-medium text-primary hover:underline"
    >
      {n}
    </button>
  );
}

const COMPONENTS = { a: AnswerLink, img: () => null };
const PLUGINS = [remarkGfm];
const keepCitations = (url: string) => (url.startsWith(CITE) ? url : "");

/**
 * An answer section: markdown (lists, steps, tables), no raw HTML, and no
 * links except citation markers. The backend's output guard already removes
 * links; anything that still looks like one is shown as plain text.
 */
export function AnswerText({
  text,
  citations,
  onCite,
}: {
  text: string;
  citations: Citation[];
  onCite: (c: Citation) => void;
}) {
  const ctx = useMemo(() => ({ byN: new Map(citations.map((c) => [c.n, c])), onCite }), [citations, onCite]);
  return (
    <CiteContext.Provider value={ctx}>
      <div className="prose-sop text-sm">
        <ReactMarkdown skipHtml remarkPlugins={PLUGINS} urlTransform={keepCitations} components={COMPONENTS}>
          {markCitations(text)}
        </ReactMarkdown>
      </div>
    </CiteContext.Provider>
  );
}
