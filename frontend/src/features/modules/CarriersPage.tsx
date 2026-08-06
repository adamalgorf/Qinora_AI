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
      description="Transportörskatalog för denna klient som driver behörighet, poängsättning och tillförlitlighetsrankning."
      title="Transportörer"
    >
      <DataTable
        columns={[
          { key: "display_name", label: "Transportör" },
          { key: "modes", label: "Transportsätt", render: (value) => (value as string[]).join(", ") },
          { key: "lane_score", label: "Sträckpoäng", align: "right", mono: true },
          { key: "performance_score", label: "Prestanda", align: "right", mono: true },
          { key: "preferred", label: "Föredragen", render: (value) => (value ? "Ja" : "Nej") },
        ]}
        highlightId={searchParams.get("highlight") ?? undefined}
        loading={query.isLoading}
        rows={query.data}
      />
    </ModuleScaffold>
  );
}
