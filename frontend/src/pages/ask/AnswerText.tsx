import { createContext, useContext, useMemo, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import { Link } from "react-router";
import remarkGfm from "remark-gfm";
import { makeResolver } from "@/lib/obsidian";
import { useDocuments } from "@/pages/library/api";
import type { Citation } from "./api";

const CITE = "sop-cite:";
const DOC = "sop-doc:";

type Resolve = (target: string) => { id: string } | null;

const CODE = /(```[\s\S]*?```|`[^`\n]*`)/;
const outsideCode = (text: string, fn: (part: string) => string) =>
  text
    .split(CODE)
    .map((part, i) => (i % 2 ? part : fn(part)))
    .join("");

/**
 * Obsidian links copied from a note (`[[Leave Policy]]`, `[[Leave Policy|the
 * leave rules]]`, `[[Rate Card#Rates]]`, `![[deck.pptx]]`) read as words in an
 * answer: the alias if there is one, otherwise the note's name. With `resolve`,
 * a document the asker can open becomes a link to it; any other name stays
 * plain text, so a link never reveals a document they can't read.
 */
export function plainWikiLinks(text: string, resolve?: Resolve): string {
  return outsideCode(text, (part) =>
    part.replace(/!?\[\[([^\]\n]+?)\]\]/g, (_, inner: string) => {
      const [target, alias] = inner.split("|", 2) as [string, string | undefined];
      const [note = "", heading] = target.split("#", 2);
      const name = (note.split("/").pop() ?? "").replace(/\.md$/i, "").trim();
      const label = alias?.trim() || name || heading?.trim() || target.trim();
      const doc = resolve?.(note.trim());
      return doc ? `[${label.replace(/[[\]\\]/g, "\\$&")}](${DOC}${doc.id})` : label;
    }),
  );
}

/** "[1]" markers become links to the citation (outside code spans and blocks). */
export function markCitations(text: string): string {
  return outsideCode(text, (part) => part.replace(/\[(\d{1,2})\](?!\()/g, `[$1](${CITE}$1)`));
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
  if (href?.startsWith(DOC)) {
    return (
      <Link to={`/library/${encodeURIComponent(href.slice(DOC.length))}`} className="text-primary underline underline-offset-2">
        {children}
      </Link>
    );
  }
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
const keepCitations = (url: string) => (url.startsWith(CITE) || url.startsWith(DOC) ? url : "");

/**
 * An answer section: markdown (lists, steps, tables), no raw HTML, and no
 * links except citation markers and documents the asker can open. The backend's output guard already removes
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
  const docs = useDocuments().data;
  const resolve = useMemo(() => makeResolver(docs ?? []), [docs]);
  const ctx = useMemo(() => ({ byN: new Map(citations.map((c) => [c.n, c])), onCite }), [citations, onCite]);
  return (
    <CiteContext.Provider value={ctx}>
      <div className="prose-sop text-sm">
        <ReactMarkdown skipHtml remarkPlugins={PLUGINS} urlTransform={keepCitations} components={COMPONENTS}>
          {markCitations(plainWikiLinks(text, resolve))}
        </ReactMarkdown>
      </div>
    </CiteContext.Provider>
  );
}
