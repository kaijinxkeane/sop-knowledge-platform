import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { t } from "@/i18n";
import { useDocuments, type Doc } from "@/pages/library/api";

/** How Obsidian names a file in a link: notes without ".md", attachments with their extension. */
export function linkFor(doc: Doc): string {
  const base = doc.vault_path.split("/").pop() ?? doc.title;
  return doc.kind === "note" ? `[[${base.replace(/\.md$/i, "")}]]` : `![[${base}]]`;
}

/** Pick a note or file the writer can see; inserts an Obsidian link or embed. */
export function LinkDialog({ onPick, onClose }: { onPick: (markdown: string) => void; onClose: () => void }) {
  const docs = useDocuments();
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  const matches = (docs.data ?? [])
    .filter((d) => !needle || d.title.toLowerCase().includes(needle) || d.vault_path.toLowerCase().includes(needle))
    .slice(0, 12);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogTitle>{t("link.title")}</DialogTitle>
        <DialogDescription>{t("link.help")}</DialogDescription>
        <Input autoFocus aria-label={t("link.search")} placeholder={t("link.search")} value={q} onChange={(e) => setQ(e.target.value)} />
        <ul className="max-h-72 divide-y overflow-y-auto">
          {matches.map((d) => (
            <li key={d.id}>
              <button
                type="button"
                className="w-full px-2 py-2 text-left text-sm hover:bg-accent"
                onClick={() => onPick(linkFor(d))}
              >
                <span className="font-medium">{d.title}</span>
                <span className="ml-2 text-xs text-muted-foreground">
                  {d.kind === "note" ? t("link.note") : t("link.embed")}
                </span>
              </button>
            </li>
          ))}
          {docs.data && !matches.length && <li className="py-2 text-sm text-muted-foreground">{t("link.none")}</li>}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
