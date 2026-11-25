import { NavLink, Navigate, Outlet } from "react-router";
import { useMe } from "@/auth/hooks";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

const tab = ({ isActive }: { isActive: boolean }) =>
  cn(
    "border-b-2 px-1 pb-2 text-sm",
    isActive ? "border-primary font-medium" : "border-transparent text-muted-foreground",
  );

function useAdminTabs() {
  const me = useMe();
  const actions = me.data?.global_actions ?? [];
  return {
    manage: actions.includes("manage_users"),
    audit: actions.includes("view_audit"),
    spaces: actions.includes("manage_spaces"),
  };
}

/** Users and roles need manage_users; the audit log needs view_audit; departments
 * need manage_spaces (the backend checks all three). */
export default function AdminLayout() {
  const { manage, audit, spaces } = useAdminTabs();
  return (
    <section className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="text-xl font-semibold">{t("admin.title")}</h1>
      <nav className="mt-4 flex gap-6 border-b" aria-label={t("admin.title")}>
        {manage && (
          <>
            <NavLink to="/admin/users" className={tab}>{t("admin.users")}</NavLink>
            <NavLink to="/admin/roles" className={tab}>{t("admin.roles")}</NavLink>
          </>
        )}
        {spaces && <NavLink to="/admin/departments" className={tab}>{t("admin.departments")}</NavLink>}
        {audit && <NavLink to="/admin/audit" className={tab}>{t("admin.audit")}</NavLink>}
        {(manage || audit) && <NavLink to="/admin/usage" className={tab}>{t("admin.usage")}</NavLink>}
      </nav>
      <div className="mt-6">
        <Outlet />
      </div>
    </section>
  );
}

export function AdminIndex() {
  const { manage, audit } = useAdminTabs();
  return <Navigate to={manage ? "/admin/users" : audit ? "/admin/audit" : "/admin/departments"} replace />;
}
