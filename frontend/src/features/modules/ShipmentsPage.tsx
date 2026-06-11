import { useQuery } from "@tanstack/react-query";

import { apiGet, type ShipmentListItem } from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function ShipmentsPage() {
  const query = useQuery({
    queryKey: ["shipments"],
    queryFn: () => apiGet<ShipmentListItem[]>("/shipments"),
  });

  return (
    <ModuleScaffold
      badge="Bex + Trak"
      description="Booked and in-transit shipments with carrier assignment and ETA."
      title="Shipments"
    >
      <DataTable
        columns={[
          { key: "public_id", label: "ID" },
          { key: "lane", label: "Lane" },
          { key: "status", label: "Status" },
          { key: "carrier_id", label: "Carrier" },
          { key: "eta", label: "ETA" },
        ]}
        loading={query.isLoading}
        rows={query.data}
      />
    </ModuleScaffold>
  );
}
