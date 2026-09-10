import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageShell } from "@/components/patterns/PageShell";
import { PriorityList, PriorityListItem } from "@/components/patterns/PriorityList";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiGet, type CaseListItem } from "@/shared/api/client";

type Queue = "critical" | "waiting" | "ai" | "closed";

const QUEUES: Array<{ value: Queue; label: string }> = [
  { value: "critical", label: "Kritiska avvikelser" },
  { value: "waiting", label: "Väntar på operatör" },
  { value: "ai", label: "AI-behandlas nu" },
  { value: "closed", label: "Stängda ärenden" },
];

function matchesQueue(item: CaseListItem, queue: Queue): boolean {
  if (queue === "critical") return item.priority === "critical" || item.status === "requires_review";
  if (queue === "closed") return item.status === "delivered" || item.status === "closed";
  if (queue === "waiting") return Boolean(item.assignee) && item.status !== "closed";
  return !item.assignee && item.status !== "closed";
}

function slaTone(slaDueAt: string | null): "destructive" | "secondary" | "outline" {
  if (!slaDueAt) return "outline";
  const minutesLeft = (new Date(slaDueAt).getTime() - Date.now()) / 60000;
  if (minutesLeft <= 30) return "destructive";
  if (minutesLeft <= 180) return "secondary";
  return "outline";
}

function formatSla(slaDueAt: string | null): string {
  if (!slaDueAt) return "—";
  const minutesLeft = Math.round((new Date(slaDueAt).getTime() - Date.now()) / 60000);
  if (minutesLeft <= 0) return "Försenad";
  if (minutesLeft < 60) return `${minutesLeft} minuter kvar`;
  return `${Math.round(minutesLeft / 60)} timmar kvar`;
}

export function CasesPage() {
  const navigate = useNavigate();
  const [queue, setQueue] = useState<Queue>("critical");
  const query = useQuery({
    queryKey: ["cases"],
    queryFn: () => apiGet<CaseListItem[]>("/cases"),
  });

  const cases = query.data ?? [];
  const counts = Object.fromEntries(
    QUEUES.map((q) => [q.value, cases.filter((c) => matchesQueue(c, q.value)).length]),
  ) as Record<Queue, number>;
  const filtered = cases.filter((c) => matchesQueue(c, queue));

  return (
    <PageShell subtitle="Operativ Hantering" title="Ärenden">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        <Card>
          <CardContent className="flex flex-col gap-4 p-5">
            <h2 className="text-base font-semibold">Köer och filter</h2>
            <PriorityList>
              {QUEUES.map((q) => (
                <PriorityListItem
                  key={q.value}
                  onClick={() => setQueue(q.value)}
                  tag={<Badge variant="outline">{counts[q.value] ?? 0}</Badge>}
                  title={q.label}
                />
              ))}
            </PriorityList>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-4 p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold">Aktiva ärenden</h2>
              <span className="text-sm text-muted-foreground">
                Visar {filtered.length} ärenden
              </span>
            </div>
            {query.isLoading ? (
              <div className="grid gap-2">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : filtered.length === 0 ? (
              <p className="text-sm text-muted-foreground">Inga ärenden i denna kö.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-border/60 text-left text-[11px] uppercase text-muted-foreground">
                      <th className="pb-2 font-semibold">Ärende-ID</th>
                      <th className="pb-2 font-semibold">Kund/Sändare</th>
                      <th className="pb-2 font-semibold">Kategori</th>
                      <th className="pb-2 font-semibold">SLA-tid</th>
                      <th className="pb-2 font-semibold">Ansvarig</th>
                      <th className="pb-2 font-semibold" />
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((item) => (
                      <tr className="border-b border-border/30" key={item.id}>
                        <td className="py-3 font-mono font-semibold">{item.public_id}</td>
                        <td className="py-3">{item.customer}</td>
                        <td className="py-3 text-muted-foreground">{item.category}</td>
                        <td className="py-3">
                          <Badge variant={slaTone(item.sla_due_at)}>
                            {formatSla(item.sla_due_at)}
                          </Badge>
                        </td>
                        <td className="py-3 text-muted-foreground">
                          {item.assignee ?? "AI-assistent"}
                        </td>
                        <td className="py-3 text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => navigate(`/cases/${item.id}`)}
                          >
                            Öppna
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </PageShell>
  );
}
