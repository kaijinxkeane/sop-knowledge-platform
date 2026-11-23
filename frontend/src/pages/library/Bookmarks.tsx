import { Star } from "lucide-react";
import { Link } from "react-router";
import { t } from "@/i18n";
import { bookmarkHref, useBookmarks } from "./api";

/** ★ Bookmarks on Home and in the Library sidebar. The backend leaves out
 * anything the user can no longer open. */
export function BookmarkList({ limit = 10 }: { limit?: number }) {
  const marks = useBookmarks();
  return (
    <section aria-labelledby="bookmarks-heading" className="space-y-1">
      <h2 id="bookmarks-heading" className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
        <Star className="size-3.5" />
        {t("bookmark.heading")}
      </h2>
      {marks.data?.length ? (
        <ul className="space-y-0.5 text-sm">
          {marks.data.slice(0, limit).map((b) => (
            <li key={b.id}>
              <Link to={bookmarkHref(b)} className="block truncate rounded px-2 py-1 hover:bg-accent">
                {b.title || t("bookmark.untitled")}
                {b.part && (
                  <span className="ml-1 text-xs text-muted-foreground">· {t("bookmark.part", { n: b.part })}</span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        marks.data && <p className="px-2 text-xs text-muted-foreground">{t("bookmark.none")}</p>
      )}
    </section>
  );
}
