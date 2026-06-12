import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  apiGet,
  apiPost,
  type CreateInvoicePayload,
  type CreateInvoiceResponse,
  type OverrideShipmentPayload,
  type RunTrackingSimulatorResponse,
  type ShipmentListItem,
  type UpdateShipmentStatusPayload,
} from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function ShipmentsPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [overrideForm, setOverrideForm] = useState({
    shipmentId: "shp-001",
    status: "needs_review",
    reason: "Carrier confirmation requires operator review",
  });
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
  const invoiceMutation = useMutation({
    mutationFn: (shipment: ShipmentListItem) =>
      apiPost<CreateInvoiceResponse, CreateInvoicePayload>(`/shipments/${shipment.id}/invoice`, {
        invoice_amount: 7350,
        max_discrepancy: 250,
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["shipments"] }),
        queryClient.invalidateQueries({ queryKey: ["invoices"] }),
      ]);
    },
  });
  const overrideMutation = useMutation({
    mutationFn: (payload: OverrideShipmentPayload & { id: string }) =>
      apiPost<ShipmentListItem, OverrideShipmentPayload>(`/shipments/${payload.id}/override`, {
        status: payload.status,
        reason: payload.reason,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["shipments"] });
    },
  });
  const trackingMutation = useMutation({
    mutationFn: () =>
      apiPost<RunTrackingSimulatorResponse, { limit: number; max_discrepancy: number }>(
        "/shipments/tracking-simulator/run",
        {
          limit: 10,
          max_discrepancy: 250,
        },
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["shipments"] }),
        queryClient.invalidateQueries({ queryKey: ["invoices"] }),
      ]);
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
        highlightId={searchParams.get("highlight") ?? undefined}
        loading={query.isLoading}
        rows={query.data}
      />
      <div className="quote-actions">
        <Button
          disabled={trackingMutation.isPending}
          onClick={() => trackingMutation.mutate()}
          type="button"
        >
          {trackingMutation.isPending ? "Running Trak Flow..." : "Run tracking simulator"}
        </Button>
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
        {(query.data ?? [])
          .filter((shipment) => shipment.status === "delivered")
          .map((shipment) => (
            <Button
              key={`invoice-${shipment.id}`}
              onClick={() => invoiceMutation.mutate(shipment)}
              type="button"
            >
              Audit invoice for {shipment.public_id}
            </Button>
          ))}
      </div>
      <form
        className="override-panel"
        onSubmit={(event) => {
          event.preventDefault();
          overrideMutation.mutate({
            id: overrideForm.shipmentId,
            status: overrideForm.status,
            reason: overrideForm.reason,
          });
        }}
      >
        <div className="override-heading">
          <ShieldAlert aria-hidden="true" />
          <div>
            <span>Manual override</span>
            <strong>Record an audited shipment exception</strong>
          </div>
        </div>
        <label>
          Shipment
          <select
            aria-label="Override shipment"
            value={overrideForm.shipmentId}
            onChange={(event) =>
              setOverrideForm((current) => ({ ...current, shipmentId: event.target.value }))
            }
          >
            {(query.data ?? []).map((shipment) => (
              <option key={shipment.id} value={shipment.id}>
                {shipment.public_id} - {shipment.status}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select
            aria-label="Override status"
            value={overrideForm.status}
            onChange={(event) =>
              setOverrideForm((current) => ({ ...current, status: event.target.value }))
            }
          >
            <option value="needs_review">Needs review</option>
            <option value="manual_review">Manual review</option>
            <option value="cancelled">Cancelled</option>
            <option value="booked">Booked</option>
            <option value="in_transit">In transit</option>
          </select>
        </label>
        <label className="override-reason">
          Reason
          <input
            aria-label="Override reason"
            value={overrideForm.reason}
            onChange={(event) =>
              setOverrideForm((current) => ({ ...current, reason: event.target.value }))
            }
          />
        </label>
        <Button disabled={overrideMutation.isPending} type="submit" variant="secondary">
          {overrideMutation.isPending ? "Recording..." : "Record override"}
        </Button>
      </form>
    </ModuleScaffold>
  );
}
