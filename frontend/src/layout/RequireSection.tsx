import type { ReactNode } from "react";
import { useOutletContext } from "react-router";
import type { Section } from "@/auth/permissions";
import { NotFound } from "@/pages/NotFound";

/** Hidden sections look exactly like missing pages (same as the API's 404s). */
export function RequireSection({ section, children }: { section: Section; children: ReactNode }) {
  const sections = useOutletContext<Section[]>();
  return sections.includes(section) ? children : <NotFound />;
}
