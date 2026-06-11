import { useQuery } from "@tanstack/react-query";

import { apiGet, type RequestListItem } from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function RequestsPage() {
  const query = useQuery({
    queryKey: ["requests"],
    queryFn: () => apiGet<RequestListItem[]>("/requests"),
  });

  return (
    <ModuleScaffold
      badge="Nora + Parsek"
      description="Parsed customer transport requests with modes, lanes and validation states."
      title="Requests"
    >
      <DataTable
        columns={[
          { key: "public_id", label: "ID" },
          { key: "customer", label: "Customer" },
          { key: "lane", label: "Lane" },
          { key: "mode", label: "Mode" },
          { key: "status", label: "Status" },
          { key: "weight_kg", label: "Weight kg" },
        ]}
        loading={query.isLoading}
        rows={query.data}
      />
    </ModuleScaffold>
  );
}
