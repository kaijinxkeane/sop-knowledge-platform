import { NavLink, Navigate, Outlet } from "react-router";
import { useMe } from "@/auth/hooks";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

const tab = ({ isActive }: { isActive: boolean }) =>
  cn(
    "border-b-2 px-1 pb-2 text-sm",
    isActive ? "border-primary font-medium" : "border-transparent text-muted-foreground",
  );

/** Users and roles need manage_users; an auditor-only account sees the audit note. */
export default function AdminLayout() {
  const me = useMe();
  const canManage = me.data?.global_actions.includes("manage_users") ?? false;
  return (
    <section className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="text-xl font-semibold">{t("admin.title")}</h1>
      {canManage ? (
        <>
          <nav className="mt-4 flex gap-6 border-b" aria-label={t("admin.title")}>
            <NavLink to="/admin/users" className={tab}>
              {t("admin.users")}
            </NavLink>
            <NavLink to="/admin/roles" className={tab}>
              {t("admin.roles")}
            </NavLink>
          </nav>
          <div className="mt-6">
            <Outlet />
          </div>
        </>
      ) : (
        <p className="mt-4 text-sm text-muted-foreground">{t("admin.auditSoon")}</p>
      )}
    </section>
  );
}

export function AdminIndex() {
  return <Navigate to="/admin/users" replace />;
}
