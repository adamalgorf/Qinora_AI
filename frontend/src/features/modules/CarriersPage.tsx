import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { apiGet, type CarrierListItem } from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function CarriersPage() {
  const [searchParams] = useSearchParams();
  const query = useQuery({
    queryKey: ["carriers"],
    queryFn: () => apiGet<CarrierListItem[]>("/carriers"),
  });

  return (
    <ModuleScaffold
      badge="Carrier Intelligence"
      description="Tenant carrier directory feeding eligibility, scoring and confidence ranking."
      title="Carriers"
    >
      <DataTable
        columns={[
          { key: "display_name", label: "Carrier" },
          { key: "modes", label: "Modes", render: (value) => (value as string[]).join(", ") },
          { key: "lane_score", label: "Lane score" },
          { key: "performance_score", label: "Performance" },
          { key: "preferred", label: "Preferred", render: (value) => (value ? "Yes" : "No") },
        ]}
        highlightId={searchParams.get("highlight") ?? undefined}
        loading={query.isLoading}
        rows={query.data}
      />
    </ModuleScaffold>
  );
}
