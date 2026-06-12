import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Power } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  apiGet,
  apiPost,
  type AgentConfigItem,
  type AgentLogListItem,
  type UpdateAgentConfigPayload,
} from "@/shared/api/client";

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
        {(configsQuery.data ?? []).map((agent) => (
          <section className="agent-config-card" key={agent.agent_key}>
            <div className="agent-config-head">
              <Bot aria-hidden="true" />
              <div>
                <span>{agent.agent_key}</span>
                <strong>{agent.agent_name}</strong>
              </div>
              <label className="agent-toggle">
                <input
                  aria-label={`Enable ${agent.agent_name}`}
                  checked={agent.is_enabled}
                  type="checkbox"
                  onChange={(event) =>
                    patchConfig(agent, { is_enabled: event.currentTarget.checked })
                  }
                />
                <Power aria-hidden="true" />
              </label>
            </div>
            <label>
              Auto Mode
              <select
                aria-label={`${agent.agent_name} auto mode`}
                value={agent.auto_mode}
                onChange={(event) =>
                  patchConfig(agent, {
                    auto_mode: event.currentTarget.value as AgentConfigItem["auto_mode"],
                  })
                }
              >
                <option value="manual">Manual</option>
                <option value="assisted">Assisted</option>
                <option value="guarded_auto">Guarded Auto</option>
              </select>
            </label>
            <label>
              Min confidence
              <input
                aria-label={`${agent.agent_name} min confidence`}
                max="1"
                min="0"
                step="0.01"
                type="number"
                value={agent.min_confidence}
                onChange={(event) =>
                  patchConfig(agent, { min_confidence: Number(event.currentTarget.value) })
                }
              />
            </label>
          </section>
        ))}
      </div>
      {configsQuery.isLoading ? <p className="muted">Loading agent configs...</p> : null}
      {updateConfig.isError ? (
        <p className="form-feedback">Agent config update failed.</p>
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
          { key: "agent_name", label: "Agent" },
          { key: "step", label: "Step" },
          { key: "entity_id", label: "Entity" },
          {
            key: "confidence",
            label: "Confidence",
            render: (value) => `${Math.round(Number(value) * 100)}%`,
          },
        ]}
        loading={logsQuery.isLoading}
        rows={logsQuery.data}
      />
      </div>
    </ModuleScaffold>
  );
}
