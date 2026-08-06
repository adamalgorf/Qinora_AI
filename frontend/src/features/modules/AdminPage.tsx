import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  apiGet,
  apiPost,
  type AgentConfigItem,
  type AgentLogListItem,
  type UpdateAgentConfigPayload,
} from "@/shared/api/client";
import { getAgentColor } from "@/shared/agents/colors";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function AdminPage() {
  const queryClient = useQueryClient();
  const logsQuery = useQuery({
    queryKey: ["agent-logs"],
    queryFn: () => apiGet<AgentLogListItem[]>("/agents/logs"),
  });
  const configsQuery = useQuery({
    queryKey: ["agent-configs"],
    queryFn: () => apiGet<AgentConfigItem[]>("/agents/configs"),
  });
  const updateConfig = useMutation({
    mutationFn: ({
      agentKey,
      payload,
    }: {
      agentKey: string;
      payload: UpdateAgentConfigPayload;
    }) => apiPost<AgentConfigItem, UpdateAgentConfigPayload>(`/agents/${agentKey}/config`, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["agent-configs"] });
    },
  });

  function patchConfig(agent: AgentConfigItem, payload: Partial<UpdateAgentConfigPayload>) {
    updateConfig.mutate({
      agentKey: agent.agent_key,
      payload: {
        is_enabled: payload.is_enabled ?? agent.is_enabled,
        auto_mode: payload.auto_mode ?? agent.auto_mode,
        min_confidence: payload.min_confidence ?? agent.min_confidence,
      },
    });
  }

  return (
    <ModuleScaffold
      badge="Agent Ops"
      description="Agent audit trail and operational health signals for tower/admin roles."
      title="Admin"
    >
      <div className="agent-config-grid">
        {(configsQuery.data ?? []).map((agent) => {
          const color = getAgentColor(agent.agent_key);
          return (
          <section className="agent-config-card" key={agent.agent_key}>
            <div className="agent-config-head">
              <span aria-hidden="true" className={`size-2.5 rounded-full ${color.dot}`} />
              <div>
                <span>{agent.agent_key}</span>
                <strong>{agent.agent_name}</strong>
              </div>
              <Switch
                aria-label={`Enable ${agent.agent_name}`}
                checked={agent.is_enabled}
                onCheckedChange={(checked) => patchConfig(agent, { is_enabled: checked })}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`${agent.agent_key}-auto-mode`}>Auto Mode</Label>
              <Select
                value={agent.auto_mode}
                onValueChange={(value) =>
                  patchConfig(agent, { auto_mode: value as AgentConfigItem["auto_mode"] })
                }
              >
                <SelectTrigger id={`${agent.agent_key}-auto-mode`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">Manual</SelectItem>
                  <SelectItem value="assisted">Assisted</SelectItem>
                  <SelectItem value="guarded_auto">Guarded Auto</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`${agent.agent_key}-min-confidence`}>Min confidence</Label>
              <Input
                id={`${agent.agent_key}-min-confidence`}
                max="1"
                min="0"
                step="0.01"
                type="number"
                value={agent.min_confidence}
                onChange={(event) =>
                  patchConfig(agent, { min_confidence: Number(event.currentTarget.value) })
                }
              />
            </div>
          </section>
          );
        })}
      </div>
      {configsQuery.isLoading ? (
        <div className="grid gap-2">
          <Skeleton className="h-24 w-full" />
        </div>
      ) : null}
      {updateConfig.isError ? (
        <Alert variant="destructive">
          <AlertDescription>Agent config update failed.</AlertDescription>
        </Alert>
      ) : null}
      <div className="queue-panel">
        <div className="queue-panel-header">
          <h3>Agent audit trail</h3>
          <Button
            disabled={logsQuery.isFetching}
            type="button"
            variant="secondary"
            onClick={() => logsQuery.refetch()}
          >
            Refresh
          </Button>
        </div>
      <DataTable
        columns={[
          {
            key: "agent_name",
            label: "Agent",
            render: (value) => {
              const name = String(value ?? "");
              const color = getAgentColor(name);
              return (
                <span className="flex items-center gap-2">
                  <span aria-hidden="true" className={`size-2 rounded-full ${color.dot}`} />
                  {name}
                </span>
              );
            },
          },
          { key: "step", label: "Step" },
          { key: "entity_id", label: "Entity", mono: true },
          {
            key: "confidence",
            label: "Confidence",
            render: (value) => <ConfidenceBar value={Number(value)} />,
          },
        ]}
        loading={logsQuery.isLoading}
        rows={logsQuery.data}
      />
      </div>
    </ModuleScaffold>
  );
}
