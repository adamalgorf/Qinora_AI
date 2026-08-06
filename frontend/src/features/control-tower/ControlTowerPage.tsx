import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bot, CheckCircle2, Clock3, Play, RadioTower } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  apiGet,
  apiPost,
  type DashboardSummary,
  type DemoFlowResponse,
  type OperationalTaskItem,
} from "@/shared/api/client";

const iconByMetric = [Clock3, CheckCircle2, AlertTriangle, Bot];
const accentByMetric = ["text-primary", "text-success", "text-warning", "text-info"];

export function ControlTowerPage() {
  const queryClient = useQueryClient();
  const summaryQuery = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => apiGet<DashboardSummary>("/dashboard/summary"),
  });
  const tasksQuery = useQuery({
    queryKey: ["operational-tasks"],
    queryFn: () => apiGet<OperationalTaskItem[]>("/tasks"),
  });
  const demoFlowMutation = useMutation({
    mutationFn: () => apiPost<DemoFlowResponse, Record<string, never>>("/demo/flow", {}),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] }),
        queryClient.invalidateQueries({ queryKey: ["operational-tasks"] }),
        queryClient.invalidateQueries({ queryKey: ["requests"] }),
        queryClient.invalidateQueries({ queryKey: ["quotes"] }),
        queryClient.invalidateQueries({ queryKey: ["shipments"] }),
        queryClient.invalidateQueries({ queryKey: ["invoices"] }),
        queryClient.invalidateQueries({ queryKey: ["outbound-replies"] }),
      ]);
    },
  });
  const summary = summaryQuery.data;
  const tasks = tasksQuery.data ?? [];
  const demoFlow = demoFlowMutation.data;

  return (
    <section className="tower-page">
      <header className="page-header">
        <div>
          <Badge className="mb-4 border-primary/30 bg-primary/10 text-primary" variant="outline">
            <RadioTower aria-hidden="true" className="size-3.5" />
            Control Tower
          </Badge>
          <h1>Freight operations from request to invoice in one command layer.</h1>
          <p className="page-lede">
            Intake, quotes, carrier matching, booking and invoice audit connected through one
            deterministic backend workflow.
          </p>
        </div>
        <Button
          disabled={summaryQuery.isLoading || demoFlowMutation.isPending}
          type="button"
          onClick={() => demoFlowMutation.mutate()}
        >
          <Play aria-hidden="true" />
          {demoFlowMutation.isPending ? "Running flow..." : "Run demo flow"}
        </Button>
      </header>
      {demoFlow ? (
        <section className="demo-flow-panel" aria-label="Demo flow result">
          <div>
            <Badge variant="secondary">{demoFlow.shipment_status}</Badge>
            <h2>{demoFlow.request.public_id} completed order-to-cash</h2>
            <p>
              {demoFlow.quote.id} accepted after outbound send, {demoFlow.shipment.public_id}{" "}
              finished as {demoFlow.shipment.status} and {demoFlow.invoice.public_id} approved.
            </p>
          </div>
          <ol>
            {demoFlow.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <div className="demo-flow-links" aria-label="Created flow records">
            <Button asChild size="sm" variant="secondary">
              <Link to={`/requests?highlight=${demoFlow.request.id}`}>
                Request {demoFlow.request.public_id}
              </Link>
            </Button>
            <Button asChild size="sm" variant="secondary">
              <Link to={`/quotes?highlight=${demoFlow.quote.id}`}>Quote</Link>
            </Button>
            <Button asChild size="sm" variant="secondary">
              <Link to={`/shipments?highlight=${demoFlow.shipment.id}`}>
                Shipment {demoFlow.shipment.public_id}
              </Link>
            </Button>
            <Button asChild size="sm" variant="secondary">
              <Link to={`/invoices?highlight=${demoFlow.invoice.id}`}>
                Invoice {demoFlow.invoice.public_id}
              </Link>
            </Button>
          </div>
        </section>
      ) : null}
      {demoFlowMutation.error ? (
        <p className="text-sm text-destructive">Demo flow could not be completed.</p>
      ) : null}

      <div className="kpi-grid">
        {(summary?.kpis ?? []).map((kpi, index) => {
          const Icon = iconByMetric[index] ?? Bot;
          const accent = accentByMetric[index] ?? "text-primary";

          return (
            <Card className="group transition-colors" key={kpi.label}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 p-4 pb-2">
                <CardTitle className="truncate text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  {kpi.label}
                </CardTitle>
                <Icon
                  aria-hidden="true"
                  className={`size-4 shrink-0 opacity-60 transition-opacity group-hover:opacity-100 ${accent}`}
                />
              </CardHeader>
              <CardContent className="p-4 pt-0">
                <div className={`text-2xl font-bold tracking-tight ${accent}`}>{kpi.value}</div>
                <p className="mt-1 text-xs text-muted-foreground">{kpi.trend}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="pipeline">
        {(summary?.pipeline ?? []).map((column) => (
          <Card className="pipeline-column" key={column.status}>
            <CardHeader>
              <CardDescription>{column.status}</CardDescription>
              <CardTitle>{column.count}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="column-glow" />
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="tower-split">
        <Card className="agent-card">
          <CardHeader>
            <CardDescription>Exception feed</CardDescription>
            <CardTitle>Open operational tasks</CardTitle>
          </CardHeader>
          <CardContent className="agent-list">
            {tasksQuery.isLoading ? (
              <div className="grid gap-2">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : (
              tasks.map((task) => (
                <div className="agent-row" key={task.id}>
                  <div>
                    <strong>{task.entity_id}</strong>
                    <span>{task.reason}</span>
                  </div>
                  <Badge variant={task.priority === "high" ? "destructive" : "outline"}>
                    {task.priority}
                  </Badge>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card className="agent-card">
          <CardHeader>
            <CardDescription>Workflow activity</CardDescription>
            <CardTitle>Latest automation decisions</CardTitle>
          </CardHeader>
          <CardContent className="agent-list">
            {summaryQuery.isLoading ? (
              <div className="grid gap-2">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : (
              (summary?.agentActivity ?? []).map((activity) => (
                <div className="agent-row" key={`${activity.agent}-${activity.event}`}>
                  <div>
                    <strong>{activity.agent}</strong>
                    <span>{activity.event}</span>
                  </div>
                  <Badge variant="outline">{Math.round(activity.confidence * 100)}%</Badge>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
