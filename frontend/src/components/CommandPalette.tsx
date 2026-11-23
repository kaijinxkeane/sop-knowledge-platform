import { Search } from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";
import type { Section } from "@/auth/permissions";
import { t } from "@/i18n";

// The dialog loads on first use, keeping it out of every page's initial JS.
const Palette = lazy(() => import("./PaletteDialog"));

/** Ctrl+K / ⌘K from any page (frontend spec §2). Titles only, filtered by the backend. */
export function CommandPalette({ sections }: { sections: Section[] }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex h-8 items-center gap-2 rounded-md border px-2 text-sm text-muted-foreground hover:bg-accent"
      >
        <Search className="size-4" />
        {t("palette.open")}
        <kbd className="rounded border bg-muted px-1 text-[10px]">⌘K</kbd>
      </button>
      {open && (
        <Suspense fallback={null}>
          <Palette sections={sections} onClose={() => setOpen(false)} />
        </Suspense>
      )}
    </>
  );
}

