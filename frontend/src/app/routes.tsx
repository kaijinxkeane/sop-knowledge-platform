import { lazy, Suspense, type ReactNode } from "react";
import { Outlet, type RouteObject } from "react-router";
import type { Section } from "@/auth/permissions";
import { t, type MessageKey } from "@/i18n";
import { AppShell } from "@/layout/AppShell";
import { RequireAuth } from "@/layout/RequireAuth";
import { RequireSection } from "@/layout/RequireSection";
import { AcceptInvite } from "@/pages/AcceptInvite";
import { Account } from "@/pages/Account";
import { Home } from "@/pages/Home";
import { NotFound } from "@/pages/NotFound";
import { Placeholder } from "@/pages/Placeholder";
import { SignIn } from "@/pages/SignIn";

// Loaded only when opened, to keep the first download small (spec §10).
const Notice = lazy(() => import("@/pages/Notice"));
const AdminLayout = lazy(() => import("@/pages/admin/AdminLayout"));
const AdminIndex = lazy(() =>
  import("@/pages/admin/AdminLayout").then((m) => ({ default: m.AdminIndex })),
);
const Users = lazy(() => import("@/pages/admin/Users"));
const Roles = lazy(() => import("@/pages/admin/Roles"));
const Library = lazy(() => import("@/pages/library/Library"));
const Reader = lazy(() => import("@/pages/library/Reader"));
const Compare = lazy(() => import("@/pages/library/Compare"));
const Write = lazy(() => import("@/pages/write/Write"));
const NewNote = lazy(() => import("@/pages/write/NewNote"));
const EditNote = lazy(() => import("@/pages/write/EditNote"));

export function Loading() {
  return <p className="p-6 text-sm text-muted-foreground">{t("app.loading")}</p>;
}

const suspend = (node: ReactNode) => <Suspense fallback={<Loading />}>{node}</Suspense>;

const placeholder = (section: Section): RouteObject => ({
  path: section,
  element: (
    <RequireSection section={section}>
      <Placeholder title={`nav.${section}` as MessageKey} />
    </RequireSection>
  ),
});

export const routes: RouteObject[] = [
  { path: "/sign-in", element: <SignIn /> },
  { path: "/invite", element: <AcceptInvite /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <Home /> },
          ...(["ask", "review", "retain"] as const).map(placeholder),
          {
            path: "library",
            element: <RequireSection section="library"><Outlet /></RequireSection>,
            children: [
              { index: true, element: suspend(<Library />) },
              { path: ":id", element: suspend(<Reader />) },
              { path: ":id/compare", element: suspend(<Compare />) },
            ],
          },
          {
            path: "write",
            element: <RequireSection section="write"><Outlet /></RequireSection>,
            children: [
              { index: true, element: suspend(<Write />) },
              { path: "new", element: suspend(<NewNote />) },
              { path: ":id", element: suspend(<EditNote />) },
            ],
          },
          {
            path: "admin",
            element: <RequireSection section="admin">{suspend(<AdminLayout />)}</RequireSection>,
            children: [
              { index: true, element: suspend(<AdminIndex />) },
              { path: "users", element: suspend(<Users />) },
              { path: "roles", element: suspend(<Roles />) },
            ],
          },
          { path: "account", element: <Account /> },
          { path: "notice", element: suspend(<Notice />) },
          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
];
