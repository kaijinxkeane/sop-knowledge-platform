import { lazy, Suspense, type ReactNode } from "react";
import { Outlet, type RouteObject } from "react-router";
import { t } from "@/i18n";
import { AppShell } from "@/layout/AppShell";
import { RequireAuth } from "@/layout/RequireAuth";
import { RequireSection } from "@/layout/RequireSection";
import { AcceptInvite } from "@/pages/AcceptInvite";
import { Account } from "@/pages/Account";
import { Home } from "@/pages/Home";
import { NotFound } from "@/pages/NotFound";
import { SignIn } from "@/pages/SignIn";

// Loaded only when opened, to keep the first download small (spec §10).
const Notice = lazy(() => import("@/pages/Notice"));
const AdminLayout = lazy(() => import("@/pages/admin/AdminLayout"));
const AdminIndex = lazy(() =>
  import("@/pages/admin/AdminLayout").then((m) => ({ default: m.AdminIndex })),
);
const Users = lazy(() => import("@/pages/admin/Users"));
const Roles = lazy(() => import("@/pages/admin/Roles"));
const Audit = lazy(() => import("@/pages/admin/Audit"));
const Departments = lazy(() => import("@/pages/admin/Departments"));
const Usage = lazy(() => import("@/pages/admin/Usage"));
const Library = lazy(() => import("@/pages/library/Library"));
const Reader = lazy(() => import("@/pages/library/Reader"));
const Compare = lazy(() => import("@/pages/library/Compare"));
const Ask = lazy(() => import("@/pages/ask/Ask"));
const Write = lazy(() => import("@/pages/write/Write"));
const NewNote = lazy(() => import("@/pages/write/NewNote"));
const EditNote = lazy(() => import("@/pages/write/EditNote"));
const Review = lazy(() => import("@/pages/review/Review"));
const Retain = lazy(() => import("@/pages/retain/Retain"));
const HandoverList = lazy(() => import("@/pages/handovers/Handovers").then((m) => ({ default: m.HandoverList })));
const HandoverView = lazy(() => import("@/pages/handovers/Handovers").then((m) => ({ default: m.HandoverView })));
const NewHandover = lazy(() => import("@/pages/handovers/HandoverForm").then((m) => ({ default: m.NewHandover })));
const PathList = lazy(() => import("@/pages/paths/Paths").then((m) => ({ default: m.PathList })));
const PathView = lazy(() => import("@/pages/paths/Paths").then((m) => ({ default: m.PathView })));
const PathEditor = lazy(() => import("@/pages/paths/Paths").then((m) => ({ default: m.PathEditor })));
const ProjectList = lazy(() => import("@/pages/projects/Projects").then((m) => ({ default: m.ProjectList })));
const ProjectView = lazy(() => import("@/pages/projects/Projects").then((m) => ({ default: m.ProjectView })));
const EditHandover = lazy(() => import("@/pages/handovers/HandoverForm").then((m) => ({ default: m.EditHandover })));

export function Loading() {
  return <p className="p-6 text-sm text-muted-foreground">{t("app.loading")}</p>;
}

const suspend = (node: ReactNode) => <Suspense fallback={<Loading />}>{node}</Suspense>;

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
          {
            path: "retain",
            element: <RequireSection section="retain">{suspend(<Retain />)}</RequireSection>,
          },
          // Receivers may be anyone, so handovers aren't behind a section: the
          // backend answers 404 for handovers this person can't read.
          {
            path: "handovers",
            children: [
              { index: true, element: suspend(<HandoverList />) },
              { path: "new", element: suspend(<NewHandover />) },
              { path: ":id", element: suspend(<HandoverView />) },
              { path: ":id/edit", element: suspend(<EditHandover />) },
            ],
          },
          // Anyone can be assigned a path; managing them is checked by the backend.
          {
            path: "paths",
            children: [
              { index: true, element: suspend(<PathList />) },
              { path: "new", element: suspend(<PathEditor />) },
              { path: ":id", element: suspend(<PathView />) },
              { path: ":id/edit", element: suspend(<PathEditor />) },
            ],
          },
          // Members may be anyone; the backend answers 404 for other projects.
          {
            path: "projects",
            children: [
              { index: true, element: suspend(<ProjectList />) },
              { path: ":id", element: suspend(<ProjectView />) },
            ],
          },
          {
            path: "review",
            element: <RequireSection section="review">{suspend(<Review />)}</RequireSection>,
          },
          {
            path: "ask",
            element: <RequireSection section="ask">{suspend(<Ask />)}</RequireSection>,
          },
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
              { path: "departments", element: suspend(<Departments />) },
              { path: "audit", element: suspend(<Audit />) },
              { path: "usage", element: suspend(<Usage />) },
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
