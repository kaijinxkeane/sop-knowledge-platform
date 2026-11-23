import type { ReactNode } from "react";
import Markdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link } from "react-router";
import { t } from "@/i18n";
import {
  EMBED,
  LINK,
  TAG,
  makeResolver,
  plainName,
  splitFrontmatter,
  toMarkdown,
} from "@/lib/obsidian";
import type { Doc } from "./api";

// Keep our private schemes; everything else goes through react-markdown's
// default filter (which drops javascript: and other unsafe URLs).
const urlTransform = (url: string) =>
  [LINK, EMBED, TAG].some((p) => url.startsWith(p)) ? url : defaultUrlTransform(url);

function EmbedCard({ target, doc }: { target: string; doc: Doc | null }) {
  if (!doc) {
    return <span className="text-muted-foreground italic">{t("doc.notAvailable")}</span>;
  }
  return (
    <Link
      to={`/library/${doc.id}`}
      className="my-2 flex items-center justify-between rounded-md border bg-muted/40 px-4 py-3 no-underline hover:bg-muted"
    >
      <span>
        <span className="font-medium">{doc.title}</span>
        <span className="ml-2 text-xs text-muted-foreground">{target.split(".").pop()}</span>
      </span>
      <span className="text-sm">{t("doc.embedOpen")} →</span>
    </Link>
  );
}

/** Renders a note's markdown with its Obsidian links resolved against what the user can see. */
export function NoteView({ text, docs }: { text: string; docs: Doc[] }) {
  const resolve = makeResolver(docs);
  // Programme names (from documents this reader can already see) link to the
  // programme's Library page, since a programme is a grouping, not a note.
  const programmes = new Map(
    docs
      .map((d) => plainName(d.programme))
      .filter((p): p is string => !!p)
      .map((p) => [p.toLowerCase(), p]),
  );
  const { body } = splitFrontmatter(text);
  return (
    <div className="prose-sop">
      <Markdown
        skipHtml
        remarkPlugins={[remarkGfm]}
        urlTransform={urlTransform}
        components={{
          a: ({ href = "", children }): ReactNode => {
            if (href.startsWith(EMBED)) {
              const target = decodeURIComponent(href.slice(EMBED.length));
              return <EmbedCard target={target} doc={resolve(target) as Doc | null} />;
            }
            if (href.startsWith(LINK)) {
              const target = decodeURIComponent(href.slice(LINK.length));
              const doc = resolve(target);
              const programme = programmes.get(target.split("#")[0]!.trim().toLowerCase());
              if (!doc && programme) {
                const to = `/library?view=programme&group=${encodeURIComponent(programme)}`;
                return <Link to={to}>{children}</Link>;
              }
              // Unknown and unreadable look the same: no title, no hint it exists.
              if (!doc) {
                return <span className="text-muted-foreground italic">{t("doc.notAvailable")}</span>;
              }
              return <Link to={`/library/${doc.id}`}>{children}</Link>;
            }
            if (href.startsWith(TAG)) {
              return <span className="rounded bg-muted px-1 text-sm text-muted-foreground">{children}</span>;
            }
            return (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            );
          },
          // Images in notes would need an authenticated fetch: not shown yet.
          img: ({ alt }) => <span className="text-muted-foreground italic">[{alt}]</span>,
        }}
      >
        {toMarkdown(body)}
      </Markdown>
    </div>
  );
}
