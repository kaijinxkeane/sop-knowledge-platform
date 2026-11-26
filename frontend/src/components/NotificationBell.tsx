import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { api, type Schemas } from "@/api/client";
import { call } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { en } from "@/i18n/en";
import { t, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";
import { TIME_ZONE } from "@/lib/dates";

type Note = Schemas["NotificationOut"];

const useNotifications = () =>
  useQuery({
    queryKey: ["notifications"],
    queryFn: () => call(api.GET("/api/v1/notifications", { params: { query: { limit: 30 } } })),
    refetchInterval: 60_000,
  });

function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      call(api.POST("/api/v1/notifications/{notification_id}/read", { params: { path: { notification_id: id } } })),
    onSettled: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

/** The title only comes back while the reader can still open the document. */
export function notificationText(n: Note): string {
  const key = `notif.${n.kind}`;
  const title = n.title ?? t("notif.hidden");
  return key in en ? t(key as MessageKey, { title }) : t("notif.other", { title });
}

/** Where a notification opens; nothing for documents the reader can't open. */
export function notificationHref(n: Note): string | null {
  if (n.kind.startsWith("project_")) return "/projects";
  if (n.kind === "path_assigned" && n.ref_id) return `/paths/${encodeURIComponent(n.ref_id)}`;
  if (!n.document_id) return null;
  if (n.kind === "review_requested" && n.ref_id) return `/review?tab=changes&id=${encodeURIComponent(n.ref_id)}`;
  if (n.kind === "changes_requested") return `/write/${n.document_id}`;
  if (n.kind.startsWith("handover_") && n.ref_id) return `/handovers/${encodeURIComponent(n.ref_id)}`;
  return `/library/${n.document_id}`;
}

/** In-app notifications (plan §8.1: no email in v1). */
export function NotificationBell() {
  const list = useNotifications();
  const markRead = useMarkRead();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const unread = (list.data ?? []).filter((n) => !n.read).length;

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const choose = (n: Note) => {
    if (!n.read) markRead.mutate(n.id);
    const href = notificationHref(n);
    if (href) {
      setOpen(false);
      void navigate(href);
    }
  };

  return (
    <div ref={box} className="relative">
      <Button
        variant="ghost"
        size="sm"
        aria-label={unread ? `${t("notif.label")} (${t("notif.unread", { n: unread })})` : t("notif.label")}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <Bell />
        {unread > 0 && (
          <span aria-hidden className="rounded-full bg-primary px-1.5 text-xs text-primary-foreground">{unread}</span>
        )}
      </Button>
      {open && (
        <div className="absolute right-0 z-50 mt-1 w-96 rounded-md border bg-card p-1 text-card-foreground shadow-md">
          {list.isError ? (
            <p role="alert" className="p-3 text-sm">{t("error.generic")}</p>
          ) : !list.data?.length ? (
            <p className="p-3 text-sm text-muted-foreground">{t("notif.empty")}</p>
          ) : (
            <ul aria-label={t("notif.label")} className="max-h-96 overflow-y-auto">
              {list.data.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => choose(n)}
                    className={cn(
                      "flex w-full flex-col items-start rounded px-3 py-2 text-left text-sm hover:bg-accent",
                      !n.read && "font-medium",
                    )}
                  >
                    <span>{notificationText(n)}</span>
                    <span className="text-xs font-normal text-muted-foreground">
                      {new Date(n.created_at).toLocaleString([], { timeZone: TIME_ZONE, dateStyle: "medium", timeStyle: "short" })}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
