import { FileText, Folder, Layers, MessageSquare, Play, Star } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import type { Section } from "@/auth/permissions";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { t } from "@/i18n";
import { plainName } from "@/lib/obsidian";
import { cn } from "@/lib/utils";
import { bookmarkHref, useBookmarks, useQuickSearch } from "@/pages/library/api";

type Item = { key: string; label: string; hint?: string; href: string; icon: ReactNode; group: string };

/** Actions, shown only where the menu would be (cosmetic; pages check again). */
const ACTIONS: { section: Section; label: "palette.newSop" | "palette.ask" | "palette.drafts" | "palette.reviews" | "palette.library"; href: string }[] = [
  { section: "write", label: "palette.newSop", href: "/write/new" },
  { section: "ask", label: "palette.ask", href: "/ask" },
  { section: "write", label: "palette.drafts", href: "/write" },
  { section: "review", label: "palette.reviews", href: "/review" },
  { section: "library", label: "palette.library", href: "/library" },
];

function useDebounced(value: string, ms = 150) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setV(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return v;
}

export default function Palette({ sections, onClose }: { sections: Section[]; onClose: () => void }) {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const q = useDebounced(text.trim());
  const quick = useQuickSearch(q);
  const marks = useBookmarks();
  const [active, setActive] = useState(0);

  const items = useMemo<Item[]>(() => {
    const needle = q.toLowerCase();
    const out: Item[] = [];
    // Bookmarks rank first (spec §9.4): all of them while the box is empty.
    const bms = q ? (quick.data?.bookmarks ?? []) : (marks.data ?? []).slice(0, 5);
    for (const b of bms)
      out.push({
        key: `b${b.id}`,
        label: b.title || t("bookmark.untitled"),
        hint: b.part ? t("bookmark.part", { n: b.part }) : undefined,
        href: bookmarkHref(b),
        icon: <Star />,
        group: t("palette.bookmarks"),
      });
    if (q && quick.data) {
      const marked = new Set(bms.filter((b) => !b.part).map((b) => b.target_id));
      for (const d of quick.data.documents.filter((d) => !marked.has(d.id)))
        out.push({
          key: `d${d.id}`,
          label: d.title,
          hint: [plainName(d.programme), d.stage].filter(Boolean).join(" · ") || d.doc_type,
          href: `/library/${d.id}`,
          icon: <FileText />,
          group: t("palette.documents"),
        });
      for (const p of quick.data.programmes)
        out.push({
          key: `p${p}`,
          label: p,
          href: `/library?view=programme&group=${encodeURIComponent(p)}`,
          icon: <Folder />,
          group: t("palette.programmes"),
        });
      for (const s of quick.data.stages)
        out.push({
          key: `s${s}`,
          label: s,
          href: `/library?view=stage&group=${encodeURIComponent(s)}`,
          icon: <Layers />,
          group: t("palette.stages"),
        });
      for (const c of quick.data.conversations)
        out.push({
          key: `c${c.id}`,
          label: c.title || t("bookmark.untitled"),
          href: `/ask?conversation=${c.id}`,
          icon: <MessageSquare />,
          group: t("palette.conversations"),
        });
    }
    for (const a of ACTIONS)
      if (sections.includes(a.section) && (!needle || t(a.label).toLowerCase().includes(needle)))
        out.push({ key: `a${a.href}`, label: t(a.label), href: a.href, icon: <Play />, group: t("palette.actions") });
    return out;
  }, [q, quick.data, marks.data, sections]);

  const index = Math.min(active, Math.max(items.length - 1, 0));
  const go = (item: Item | undefined) => {
    if (!item) return;
    onClose();
    navigate(item.href);
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="top-[20%] max-w-xl translate-y-0 gap-2 p-3">
        <DialogTitle className="sr-only">{t("palette.title")}</DialogTitle>
        <DialogDescription className="sr-only">{t("palette.help")}</DialogDescription>
        <input
          autoFocus
          role="combobox"
          aria-expanded
          aria-controls="palette-list"
          aria-activedescendant={items[index] ? `palette-${items[index].key}` : undefined}
          aria-label={t("palette.title")}
          placeholder={t("palette.placeholder")}
          value={text}
          maxLength={100}
          onChange={(e) => {
            setText(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (!["ArrowDown", "ArrowUp", "Enter"].includes(e.key)) return;
            e.preventDefault();
            if (e.key === "ArrowDown") setActive(Math.min(index + 1, items.length - 1));
            else if (e.key === "ArrowUp") setActive(Math.max(index - 1, 0));
            else go(items[index]);
          }}
          className="h-10 w-full rounded-md border px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <ul id="palette-list" role="listbox" aria-label={t("palette.results")} className="max-h-80 overflow-y-auto">
          {items.map((item, i) => (
            <li key={item.key}>
              {(i === 0 || items[i - 1]!.group !== item.group) && (
                <div className="px-2 pb-1 pt-2 text-[11px] font-medium uppercase text-muted-foreground">{item.group}</div>
              )}
              <div
                id={`palette-${item.key}`}
                role="option"
                aria-selected={i === index}
                onMouseEnter={() => setActive(i)}
                onClick={() => go(item)}
                className={cn(
                  "flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm [&_svg]:size-4 [&_svg]:text-muted-foreground",
                  i === index && "bg-accent",
                )}
              >
                {item.icon}
                <span className="truncate">{item.label}</span>
                {item.hint && <span className="ml-auto shrink-0 text-xs capitalize text-muted-foreground">{item.hint}</span>}
              </div>
            </li>
          ))}
          {q && quick.data && items.length === 0 && (
            <li className="px-2 py-3 text-sm text-muted-foreground">{t("palette.none")}</li>
          )}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
