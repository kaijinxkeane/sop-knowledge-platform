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
import { useFileUrl, type Doc } from "./api";

// Keep our private schemes; everything else goes through react-markdown's
// default filter (which drops javascript: and other unsafe URLs).
const urlTransform = (url: string) =>
  [LINK, EMBED, TAG].some((p) => url.startsWith(p)) ? url : defaultUrlTransform(url);

const IMAGE = /\.(png|jpe?g)$/i;

/**
 * An image from the vault, fetched with the reader's token like any file (so
 * the backend checks access) and shown from a short-lived blob: URL.
 */
function NoteImage({ doc, alt }: { doc: Doc; alt?: string }) {
  const { url, failed } = useFileUrl(doc);
  const name = alt || doc.title;
  if (failed) return <span className="text-muted-foreground italic">{t("doc.notAvailable")}</span>;
  if (!url) return <span className="text-sm text-muted-foreground">{t("doc.imageLoading")}</span>;
  return (
    <Link to={`/library/${doc.id}`} className="my-2 inline-block" title={t("doc.image", { name })}>
      <img src={url} alt={name} className="max-h-[32rem] max-w-full rounded-md border" />
    </Link>
  );
}

const isImage = (doc: Doc | null): boolean => !!doc && (doc.doc_type === "image" || IMAGE.test(doc.vault_path));

function EmbedCard({ target, doc }: { target: string; doc: Doc | null }) {
  if (!doc) {
    return <span className="text-muted-foreground italic">{t("doc.notAvailable")}</span>;
  }
  if (isImage(doc)) return <NoteImage doc={doc} />;
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
          // ![alt](Attachments/pic.png): only vault images this reader can open.
          // Outside addresses are never fetched (the page's CSP refuses them too).
          img: ({ src, alt }) => {
            const raw = typeof src === "string" ? src : "";
            let target = "";
            if (raw && !/^[a-z][a-z0-9+.-]*:|^\/\//i.test(raw)) {
              try {
                target = decodeURIComponent(raw);
              } catch {
                target = raw;
              }
            }
            // A path from the vault root, else by file name as Obsidian does.
            const doc = target ? resolve(target.replace(/^(\.\.?\/)+/, "")) ?? resolve(target.split("/").pop()!) : null;
            if (isImage(doc as Doc | null)) return <NoteImage doc={doc as Doc} alt={alt} />;
            return <span className="text-muted-foreground italic">[{alt || t("doc.notAvailable")}]</span>;
          },
        }}
      >
        {toMarkdown(body)}
      </Markdown>
    </div>
  );
}
