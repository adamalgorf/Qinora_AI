import { useQuery } from "@tanstack/react-query";
import { BrainCircuit } from "lucide-react";

import { AiInsightBanner } from "@/components/patterns/AiInsightBanner";
import { KpiCard, KpiGrid } from "@/components/patterns/KpiCard";
import { PageShell } from "@/components/patterns/PageShell";
import { PriorityList, PriorityListItem } from "@/components/patterns/PriorityList";
import { TimelineFeed, type TimelineFeedItem } from "@/components/patterns/TimelineFeed";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiGet, type DashboardSummary, type OperationalTaskItem } from "@/shared/api/client";

export function OverviewPage() {
  const summaryQuery = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => apiGet<DashboardSummary>("/dashboard/summary"),
  });
  const tasksQuery = useQuery({
    queryKey: ["operational-tasks"],
    queryFn: () => apiGet<OperationalTaskItem[]>("/tasks"),
  });

  const summary = summaryQuery.data;
  const tasks = tasksQuery.data ?? [];

  const timelineItems: TimelineFeedItem[] = (summary?.agentActivity ?? []).map((activity, i) => ({
    id: `${activity.agent}-${i}`,
    timestamp: "",
    tag: activity.agent,
    description: activity.event,
  }));

  return (
    <PageShell subtitle="Logistikkommando" title="Översikt">
      <AiInsightBanner
        body={
          summaryQuery.isLoading
            ? "Hämtar dagens sammanfattning…"
            : "Qinora AI har hanterat inkommande förfrågningar och flaggat de ärenden som kräver manuell hantering nedan."
        }
        heading="Qinora AI-analys • Just nu i nätverket"
        icon={BrainCircuit}
      />

      <KpiGrid>
        {(summary?.kpis ?? []).map((kpi) => (
          <KpiCard key={kpi.label} label={kpi.label} trend={{ label: kpi.trend }} value={kpi.value} />
        ))}
      </KpiGrid>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
        <Card>
          <CardContent className="flex flex-col gap-4 p-6">
            <h2 className="text-base font-semibold">Högprioriterade åtgärder</h2>
            {tasksQuery.isLoading ? (
              <div className="grid gap-2">
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            ) : tasks.length === 0 ? (
              <p className="text-sm text-muted-foreground">Inga öppna driftuppgifter.</p>
            ) : (
              <PriorityList>
                {tasks.map((task) => (
                  <PriorityListItem
                    detail={task.reason}
                    eyebrow={task.entity_id}
                    key={task.id}
                    tag={
                      <Badge variant={task.priority === "high" ? "destructive" : "outline"}>
                        {task.priority}
                      </Badge>
                    }
                    title={task.entity_type}
                  />
                ))}
              </PriorityList>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-4 p-6">
            <h2 className="text-base font-semibold">Autonoma AI-beslut</h2>
            {summaryQuery.isLoading ? (
              <div className="grid gap-2">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : (
              <TimelineFeed items={timelineItems} />
            )}
          </CardContent>
        </Card>
      </div>
    </PageShell>
  );
}
