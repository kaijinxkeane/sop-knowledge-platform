import { Navigate, Outlet, useLocation } from "react-router";
import { useSession } from "@/auth/hooks";
import { t } from "@/i18n";

export function RequireAuth() {
  const { status } = useSession();
  const location = useLocation();
  if (status === "unknown") {
    return <p className="p-6 text-sm text-muted-foreground">{t("app.loading")}</p>;
  }
  if (status === "signed-out") {
    return <Navigate to="/sign-in" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Outlet />;
}
