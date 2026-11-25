import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { call } from "@/api/errors";

export const usd = (n: number) => (n > 0 && n < 0.01 ? "< $0.01" : `$${n.toFixed(2)}`);

/** Cost and usage for a month (YYYY-MM; null = this month). Admins and auditors only. */
export const useUsage = (month: string | null, enabled = true) =>
  useQuery({
    queryKey: ["usage", month],
    queryFn: () => call(api.GET("/api/v1/reports/usage", { params: { query: month ? { month } : {} } })),
    enabled,
  });
