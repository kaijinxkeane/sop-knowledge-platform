import { Link, useSearchParams } from "react-router";
import { useMe } from "@/auth/hooks";
import { t, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";
import { leadSpaces } from "./api";
import { ReadStatus } from "@/pages/reading/ReadStatus";
import { BusFactorReport, Conflicts, Coverage, Due, Gaps } from "./Reports";

type Tab = "gaps" | "coverage" | "due" | "reading" | "busFactor" | "conflicts";

/** Retain (frontend spec §8). Tabs only decide what to ask for; the backend checks each report. */
export default function Retain() {
  const me = useMe();
  const [params, setParams] = useSearchParams();
  const reviewer = leadSpaces(me.data?.space_actions).length > 0;
  const lead = leadSpaces(me.data?.space_actions, "approve").length > 0;
  const hr = !!me.data?.global_actions.includes("view_gap_reports");
  const tabs: Tab[] = [
    ...(reviewer || hr ? (["gaps"] as const) : []),
    ...(lead || hr ? (["coverage"] as const) : []),
    ...(reviewer ? (["due"] as const) : []),
    ...(lead ? (["reading", "busFactor"] as const) : []),
    ...(reviewer ? (["conflicts"] as const) : []),
  ];
  const asked = params.get("tab") as Tab | null;
  const tab = asked && tabs.includes(asked) ? asked : tabs[0];

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-6 py-6">
      <h1 className="text-2xl font-semibold">{t("retain.title")}</h1>
      <div className="flex items-center justify-between gap-4 border-b">
        <div role="tablist" aria-label={t("retain.tabs")} className="flex gap-1">
          {tabs.map((k) => (
            <button
              key={k}
              type="button"
              role="tab"
              aria-selected={tab === k}
              onClick={() => setParams({ tab: k }, { replace: true })}
              className={cn(
                "-mb-px border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground hover:text-foreground",
                tab === k && "border-primary font-medium text-foreground",
              )}
            >
              {t(`retain.tab.${k}` as MessageKey)}
            </button>
          ))}
        </div>
        <Link to="/paths" className="pb-2 text-sm text-muted-foreground hover:text-foreground">
          {t("paths.title")}
        </Link>
        <Link to="/handovers" className="pb-2 text-sm text-muted-foreground hover:text-foreground">
          {t("retain.tab.handovers")} →
        </Link>
      </div>
      <div role="tabpanel">
        {!tab && <p className="text-sm text-muted-foreground">{t("retain.noAccess")}</p>}
        {tab === "gaps" && <Gaps />}
        {tab === "coverage" && <Coverage />}
        {tab === "due" && <Due />}
        {tab === "reading" && <ReadStatus />}
        {tab === "busFactor" && <BusFactorReport />}
        {tab === "conflicts" && <Conflicts />}
      </div>
    </div>
  );
}
