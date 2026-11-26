import { useState } from "react";
import { Loading } from "@/app/routes";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";
import { usd, useUsage } from "./usageApi";
import { TIME_ZONE, todayIso } from "@/lib/dates";

const num = (n: number) => n.toLocaleString();
const thisMonth = () => todayIso().slice(0, 7);

/** Admin → Cost and usage: totals only (tiers, models, tokens), never questions or people. */
export default function Usage() {
  const [month, setMonth] = useState(thisMonth());
  const usage = useUsage(month);
  const u = usage.data;
  const peak = Math.max(0.0001, ...(u?.days ?? []).map((d) => d.cost_usd));
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1">
          <Label htmlFor="usage-month">{t("usage.month")}</Label>
          <Input
            id="usage-month"
            type="month"
            value={month}
            max={thisMonth()}
            onChange={(e) => setMonth(e.target.value || thisMonth())}
          />
        </div>
        <p className="text-sm text-muted-foreground">{t("usage.explain")}</p>
      </div>
      {usage.isPending ? (
        <Loading />
      ) : usage.isError || !u ? (
        <p role="alert" className="text-sm">{t("error.generic")}</p>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[
              [t("usage.cost"), usd(u.total_cost_usd)],
              [t("usage.cloudCalls"), num(u.cloud_calls)],
              [t("usage.localCalls"), num(u.local_calls)],
              [t("usage.fallbacks"), num(u.fallbacks)],
            ].map(([k, v]) => (
              <div key={k} className="rounded-lg border p-4">
                <dt className="text-xs uppercase text-muted-foreground">{k}</dt>
                <dd className="mt-1 text-2xl font-semibold tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
          {!u.priced && <p className="text-sm text-amber-900">{t("usage.unpriced")}</p>}
          {u.fallbacks > 0 && <p className="text-sm text-muted-foreground">{t("usage.fallbackExplain")}</p>}
          {u.days.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("usage.empty")}</p>
          ) : (
            <>
              <section aria-label={t("usage.perDay")}>
                <h2 className="mb-2 text-sm font-medium">{t("usage.perDay")}</h2>
                <ul className="space-y-1">
                  {u.days.map((d) => (
                    <li key={d.day} className="grid grid-cols-[6rem_1fr_8rem] items-center gap-3 text-sm">
                      <span className="text-muted-foreground">
                        {new Date(d.day).toLocaleDateString([], { timeZone: TIME_ZONE, day: "numeric", month: "short" })}
                      </span>
                      <span className="h-2 rounded bg-muted" aria-hidden>
                        <span className="block h-2 rounded bg-primary" style={{ width: `${(d.cost_usd / peak) * 100}%` }} />
                      </span>
                      <span className="text-right tabular-nums">
                        {usd(d.cost_usd)} · {t("usage.callsN", { n: d.calls })}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
              <section aria-label={t("usage.perTier")}>
                <h2 className="mb-2 text-sm font-medium">{t("usage.perTier")}</h2>
                <div className="overflow-x-auto rounded-md border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/40 text-left text-xs text-muted-foreground">
                      <tr>
                        <th className="px-3 py-2">{t("usage.tier")}</th>
                        <th className="px-3 py-2">{t("usage.model")}</th>
                        <th className="px-3 py-2">{t("usage.where")}</th>
                        <th className="px-3 py-2 text-right">{t("usage.calls")}</th>
                        <th className="px-3 py-2 text-right">{t("usage.tokensIn")}</th>
                        <th className="px-3 py-2 text-right">{t("usage.tokensOut")}</th>
                        <th className="px-3 py-2 text-right">{t("usage.cost")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {u.tiers.map((r) => (
                        <tr key={`${r.tier}|${r.model}`} className="border-t">
                          <td className="px-3 py-2">{r.tier}</td>
                          <td className="px-3 py-2 font-mono text-xs">{r.model}</td>
                          <td className="px-3 py-2">{t(r.location === "local" ? "usage.local" : "usage.cloud")}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{num(r.calls)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{num(r.input_tokens + r.cache_read_tokens)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{num(r.output_tokens)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {r.location === "local" ? "—" : usd(r.cost_usd)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}
