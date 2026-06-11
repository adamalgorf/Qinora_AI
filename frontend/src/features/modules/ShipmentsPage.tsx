import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import {
  apiGet,
  apiPost,
  type ShipmentListItem,
  type UpdateShipmentStatusPayload,
} from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function ShipmentsPage() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["shipments"],
    queryFn: () => apiGet<ShipmentListItem[]>("/shipments"),
  });
  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      apiPost<ShipmentListItem, UpdateShipmentStatusPayload>(`/shipments/${id}/status`, {
        status,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["shipments"] });
    },
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
      <div className="quote-actions">
        {(query.data ?? []).map((shipment) => {
          const nextStatus =
            shipment.status === "booked"
              ? "in_transit"
              : shipment.status === "in_transit"
                ? "delivered"
                : null;

          if (!nextStatus) return null;

          return (
            <Button
              key={shipment.id}
              onClick={() => statusMutation.mutate({ id: shipment.id, status: nextStatus })}
              type="button"
              variant="secondary"
            >
              Move {shipment.public_id} to {nextStatus}
            </Button>
          );
        })}
      </div>
    </ModuleScaffold>
  );
}
