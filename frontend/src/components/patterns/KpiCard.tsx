import type { ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type KpiCardProps = {
  label: string;
  value: ReactNode;
  trend?: {
    label: string;
    tone?: "positive" | "neutral";
  };
};

export function KpiCard({ label, value, trend }: KpiCardProps) {
  return (
    <Card className="rounded-lg">
      <CardContent className="flex flex-col gap-2 p-5">
        <p className="kpi-card-label">{label}</p>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <p className="min-w-0 break-words text-[28px] font-bold leading-none text-foreground">
            {value}
          </p>
          {trend ? (
            <span
              className={cn(
                "shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold whitespace-nowrap",
                trend.tone === "neutral"
                  ? "bg-muted text-muted-foreground"
                  : "bg-success/10 text-success",
              )}
            >
              {trend.label}
            </span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

export function KpiGrid({ children }: { children: ReactNode }) {
  return <div className="kpi-grid">{children}</div>;
}
