import { useQuery } from "@tanstack/react-query";

import { KpiCard, KpiGrid } from "@/components/patterns/KpiCard";
import { PageShell } from "@/components/patterns/PageShell";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiGet, type AnalyticsSummaryResponse } from "@/shared/api/client";

import { WorkloadBarChart } from "./WorkloadBarChart";

export function AnalyticsPage() {
  const query = useQuery({
    queryKey: ["analytics-summary"],
    queryFn: () => apiGet<AnalyticsSummaryResponse>("/analytics/summary"),
  });

  const data = query.data;

  return (
    <PageShell subtitle="Driftsintelligens & Statistik" title="Analys">
      <KpiGrid>
        {(data?.kpis ?? []).map((kpi) => (
          <KpiCard key={kpi.label} label={kpi.label} trend={{ label: kpi.trend }} value={kpi.value} />
        ))}
      </KpiGrid>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
        <Card>
          <CardContent className="flex flex-col gap-5 p-6">
            <div>
              <h2 className="text-[15px] font-semibold">Hanterad arbetsbörda (AI vs Manuell)</h2>
              <p className="text-xs text-muted-foreground">
                Mätt i antal hanterade förfrågningar per dag. Uppskattning baserad på tillgänglig
                aktivitetslogg, inte exakt AI/manuell-spårning.
              </p>
            </div>
            {query.isLoading ? (
              <Skeleton className="h-48 w-full" />
            ) : (
              <WorkloadBarChart rows={data?.workload_by_weekday ?? []} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-5 p-6">
            <div>
              <h2 className="text-[15px] font-semibold">Huvudsakliga felkällor</h2>
              <p className="text-xs text-muted-foreground">Bland de avvikande ärendena</p>
            </div>
            {query.isLoading ? (
              <Skeleton className="h-40 w-full" />
            ) : (
              <div className="flex flex-col gap-4">
                {(data?.top_exception_categories ?? []).map((item) => (
                  <div className="flex flex-col gap-1" key={item.category}>
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-semibold">{item.category}</span>
                      <span className="font-bold text-destructive">{item.percent}%</span>
                    </div>
                    {item.location ? (
                      <span className="text-[11px] text-muted-foreground">{item.location}</span>
                    ) : null}
                  </div>
                ))}
                {!query.isLoading && (data?.top_exception_categories ?? []).length === 0 ? (
                  <p className="text-sm text-muted-foreground">Inga avvikelser registrerade.</p>
                ) : null}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </PageShell>
  );
}
