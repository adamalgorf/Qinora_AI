import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { KpiCard, KpiGrid } from "@/components/patterns/KpiCard";
import { PageShell } from "@/components/patterns/PageShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { DataTable } from "@/features/modules/DataTable";
import { StatusChip } from "@/components/ui/status-chip";
import {
  apiGet,
  apiPost,
  type AgentConfigItem,
  type AutomationListItem,
  type UpdateAgentConfigPayload,
} from "@/shared/api/client";

export function AutomationsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<AutomationListItem | null>(null);
  const [showCreateNotice, setShowCreateNotice] = useState(false);

  const query = useQuery({
    queryKey: ["automations"],
    queryFn: () => apiGet<AutomationListItem[]>("/automations"),
  });
  const configsQuery = useQuery({
    queryKey: ["agent-configs"],
    queryFn: () => apiGet<AgentConfigItem[]>("/agents/configs"),
    enabled: Boolean(selected),
  });
  const updateConfig = useMutation({
    mutationFn: ({ agentKey, payload }: { agentKey: string; payload: UpdateAgentConfigPayload }) =>
      apiPost<AgentConfigItem, UpdateAgentConfigPayload>(`/agents/${agentKey}/config`, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agent-configs"] }),
        queryClient.invalidateQueries({ queryKey: ["automations"] }),
      ]);
    },
  });

  const rows = (query.data ?? []).filter((item) =>
    search.trim() ? item.agent_name.toLowerCase().includes(search.trim().toLowerCase()) : true,
  );
  const activeCount = (query.data ?? []).filter((a) => a.status === "active").length;
  const avgSuccess = rows.length
    ? Math.round((rows.reduce((sum, a) => sum + a.success_rate, 0) / rows.length) * 1000) / 10
    : 0;
  const totalVolume = rows.reduce((sum, a) => sum + a.volume, 0);

  const config = configsQuery.data?.find((c) => c.agent_key === selected?.agent_key);

  function patchConfig(payload: Partial<UpdateAgentConfigPayload>) {
    if (!config) return;
    updateConfig.mutate({
      agentKey: config.agent_key,
      payload: {
        is_enabled: payload.is_enabled ?? config.is_enabled,
        auto_mode: payload.auto_mode ?? config.auto_mode,
        min_confidence: payload.min_confidence ?? config.min_confidence,
      },
    });
  }

  return (
    <PageShell subtitle="Workflow Command Center" title="Automatiseringar">
      <KpiGrid>
        <KpiCard label="Aktiva AI-workflows" value={activeCount} />
        <KpiCard label="Genomsnittlig framgång" value={`${avgSuccess}%`} />
        <KpiCard label="Automatiserad volym" value={totalVolume} />
      </KpiGrid>

      <Card>
        <CardContent className="flex flex-col gap-4 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Input
              className="max-w-sm"
              placeholder="Sök efter workflow eller trigger…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <Button onClick={() => setShowCreateNotice(true)}>Skapa nytt Workflow</Button>
          </div>
          <DataTable
            columns={[
              { key: "agent_name", label: "Agent" },
              { key: "trigger", label: "Trigger" },
              { key: "scope", label: "Område / Kanal" },
              {
                key: "success_rate",
                label: "Success rate",
                align: "right",
                render: (value) => `${Math.round(Number(value) * 1000) / 10}%`,
              },
              { key: "volume", label: "Volym", align: "right" },
              {
                key: "status",
                label: "Status",
                render: (value) => <StatusChip status={String(value)} />,
              },
            ]}
            loading={query.isLoading}
            rows={rows}
            onRowClick={(row) => setSelected(row)}
          />
        </CardContent>
      </Card>

      <Dialog open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{selected?.agent_name}</DialogTitle>
            <DialogDescription>Konfigurera automatikläge och tröskelvärden.</DialogDescription>
          </DialogHeader>
          {config ? (
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <Label htmlFor="automation-enabled">Aktiverad</Label>
                <Switch
                  checked={config.is_enabled}
                  id="automation-enabled"
                  onCheckedChange={(checked) => patchConfig({ is_enabled: checked })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="automation-mode">Automatikläge</Label>
                <Select
                  value={config.auto_mode}
                  onValueChange={(value) =>
                    patchConfig({ auto_mode: value as AgentConfigItem["auto_mode"] })
                  }
                >
                  <SelectTrigger id="automation-mode">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual">Manuell</SelectItem>
                    <SelectItem value="assisted">Assisterad</SelectItem>
                    <SelectItem value="guarded_auto">Bevakad automatik</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="automation-confidence">Min. tillförlitlighet</Label>
                <Input
                  id="automation-confidence"
                  max="1"
                  min="0"
                  step="0.01"
                  type="number"
                  value={config.min_confidence}
                  onChange={(event) =>
                    patchConfig({ min_confidence: Number(event.currentTarget.value) })
                  }
                />
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Laddar konfiguration…</p>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={showCreateNotice} onOpenChange={setShowCreateNotice}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Skapa nytt Workflow</DialogTitle>
            <DialogDescription>
              Den visuella workflow-byggaren är inte tillgänglig ännu — idag konfigureras
              varje agent individuellt genom att klicka på en rad i tabellen ovan.
            </DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    </PageShell>
  );
}
