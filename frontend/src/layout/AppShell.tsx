import { LogOut } from "lucide-react";
import { lazy, Suspense } from "react";
import { Link, NavLink, Outlet } from "react-router";
import { brand, Logo } from "@/app/theme/brand";
import { useMe, useSignOut } from "@/auth/hooks";
import { visibleSections, type Section } from "@/auth/permissions";
import { CommandPalette } from "@/components/CommandPalette";
import { NotificationBell } from "@/components/NotificationBell";
import { Button } from "@/components/ui/button";
import { t, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";

const Notice = lazy(() => import("@/pages/Notice"));

export const SECTION_PATHS: Record<Section, string> = {
  ask: "/ask",
  library: "/library",
  write: "/write",
  review: "/review",
  retain: "/retain",
  handovers: "/handovers",
  projects: "/projects",
  admin: "/admin",
};

export function AppShell() {
  const me = useMe();
  const signOut = useSignOut();

  if (me.isPending) {
    return <p className="p-6 text-sm text-muted-foreground">{t("app.loading")}</p>;
  }
  if (me.isError) {
    return (
      <p role="alert" className="p-6 text-sm">
        {t("error.generic")}
      </p>
    );
  }

  const sections = visibleSections(me.data);
  // Until the staff notice is acknowledged, nothing else opens (plan §11).
  const gated = !me.data.notice.acknowledged;

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b bg-background print:hidden">
        <div className="flex h-14 items-center gap-6 px-6">
          <NavLink to="/" className="flex items-center gap-2 font-semibold">
            <Logo className="size-5" />
            {brand.name}
          </NavLink>
          {!gated && (
          <nav aria-label={t("nav.label")} className="flex items-center gap-1">
            {sections.map((s) => (
              <NavLink
                key={s}
                to={SECTION_PATHS[s]}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-foreground",
                    isActive && "bg-accent font-medium text-foreground",
                  )
                }
              >
                {t(`nav.${s}` as MessageKey)}
              </NavLink>
            ))}
          </nav>
          )}
          <div className="ml-auto flex items-center gap-3">
            {!gated && <CommandPalette sections={sections} />}
            {!gated && <NotificationBell />}
            {gated ? (
              <span className="text-sm text-muted-foreground">{me.data.display_name}</span>
            ) : (
              <Link
                to="/account"
                className="text-sm text-muted-foreground hover:text-foreground"
                title={t("user.account")}
              >
                {me.data.display_name}
              </Link>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void signOut()}
              aria-label={t("user.signOut")}
            >
              <LogOut />
              {t("user.signOut")}
            </Button>
          </div>
        </div>
      </header>
      <main className="flex-1">
        {gated ? (
          <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">{t("app.loading")}</p>}>
            <Notice gate />
          </Suspense>
        ) : (
          <Outlet context={sections} />
        )}
      </main>
    </div>
  );
}
