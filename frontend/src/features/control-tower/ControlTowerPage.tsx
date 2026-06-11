import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Bot, CheckCircle2, Clock3, RadioTower, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiGet, type DashboardSummary } from "@/shared/api/client";

const iconByMetric = [Clock3, CheckCircle2, AlertTriangle, Bot];

export function ControlTowerPage() {
  const summaryQuery = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => apiGet<DashboardSummary>("/dashboard/summary"),
  });
  const summary = summaryQuery.data;

  return (
    <section className="tower-page">
      <header className="page-header">
        <div>
          <Badge className="mb-4 border-cyan-400/30 bg-cyan-400/10 text-cyan-200" variant="outline">
            <RadioTower aria-hidden="true" className="size-3.5" />
            Control Tower
          </Badge>
          <h1>AI-driven freight operations in one live command layer.</h1>
          <p className="page-lede">
            Email intake, quotes, carrier intelligence, booking and invoice audit connected through
            one backend API.
          </p>
        </div>
        <Button className="primary-action" type="button">
          <Sparkles aria-hidden="true" />
          Review queue
        </Button>
      </header>

      <div className="kpi-grid">
        {(summary?.kpis ?? []).map((kpi, index) => {
          const Icon = iconByMetric[index] ?? Bot;

          return (
            <Card className="metric-card" key={kpi.label}>
              <CardHeader>
                <div className="metric-topline">
                  <Icon aria-hidden="true" className="size-4 text-cyan-200" />
                  <Badge variant="secondary">{kpi.trend}</Badge>
                </div>
                <CardDescription>{kpi.label}</CardDescription>
                <CardTitle>{kpi.value}</CardTitle>
              </CardHeader>
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

      <Card className="agent-card">
        <CardHeader>
          <CardDescription>Agent activity</CardDescription>
          <CardTitle>Latest autonomous decisions</CardTitle>
        </CardHeader>
        <CardContent className="agent-list">
          {summaryQuery.isLoading ? (
            <p className="muted">Syncing with backend...</p>
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
    </section>
  );
}
