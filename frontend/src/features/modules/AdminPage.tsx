import { useQuery } from "@tanstack/react-query";

import { apiGet, type AgentLogListItem } from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function AdminPage() {
  const query = useQuery({
    queryKey: ["agent-logs"],
    queryFn: () => apiGet<AgentLogListItem[]>("/agents/logs"),
  });

  return (
    <ModuleScaffold
      badge="Agent Ops"
      description="Agent audit trail and operational health signals for tower/admin roles."
      title="Admin"
    >
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
        loading={query.isLoading}
        rows={query.data}
      />
    </ModuleScaffold>
  );
}
