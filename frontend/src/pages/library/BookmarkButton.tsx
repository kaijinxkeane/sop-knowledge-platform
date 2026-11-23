import { Star } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { useBookmarks, useBookmarkToggle } from "./api";

/** ★ on a document, or on one slide or page of it (frontend spec §9.4). */
export function BookmarkButton({ docId, part, label }: { docId: string; part?: number; label?: string }) {
  const marks = useBookmarks();
  const toggle = useBookmarkToggle();
  const [busy, setBusy] = useState(false);
  const mark = marks.data?.find(
    (b) => b.target_type === "document" && b.target_id === docId && (b.part ?? null) === (part ?? null),
  );
  const on = !!mark;
  const name = label ?? (on ? t("bookmark.remove") : t("bookmark.add"));
  return (
    <Button
      variant="outline"
      size="sm"
      aria-pressed={on}
      aria-label={name}
      disabled={busy || marks.isPending}
      onClick={() => {
        setBusy(true);
        const done = on
          ? toggle.remove(mark.id)
          : toggle.add({ target_type: "document", target_id: docId, part: part ?? null });
        void done.finally(() => setBusy(false));
      }}
    >
      <Star className={cn(on && "fill-amber-400 text-amber-500")} />
      {label ?? (on ? t("bookmark.saved") : t("bookmark.save"))}
    </Button>
  );
}
