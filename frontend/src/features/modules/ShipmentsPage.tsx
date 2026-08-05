import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  apiGet,
  apiPost,
  type CreateInvoicePayload,
  type CreateInvoiceResponse,
  type OverrideShipmentPayload,
  type QuoteListItem,
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
    shipmentId: "",
    status: "needs_review",
    reason: "Carrier confirmation requires operator review",
  });
  const [error, setError] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["shipments"],
    queryFn: () => apiGet<ShipmentListItem[]>("/shipments"),
  });
  const quotesQuery = useQuery({
    queryKey: ["quotes"],
    queryFn: () => apiGet<QuoteListItem[]>("/quotes"),
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
    mutationFn: ({
      shipment,
      invoiceAmount,
    }: {
      shipment: ShipmentListItem;
      invoiceAmount: number;
    }) =>
      apiPost<CreateInvoiceResponse, CreateInvoicePayload>(`/shipments/${shipment.id}/invoice`, {
        invoice_amount: invoiceAmount,
        max_discrepancy: 250,
      }),
    onSuccess: async () => {
      setError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["shipments"] }),
        queryClient.invalidateQueries({ queryKey: ["invoices"] }),
      ]);
    },
    onError: (problem: { detail?: string }) => {
      setError(problem.detail ?? "Invoice audit could not be completed");
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

  function auditInvoiceForShipment(shipment: ShipmentListItem) {
    const quote = (quotesQuery.data ?? []).find((item) => item.id === shipment.quote_id);
    if (!quote) {
      setError("Quote amount is required before invoice audit.");
      return;
    }

    invoiceMutation.mutate({ shipment, invoiceAmount: quote.customer_price });
  }

  useEffect(() => {
    if (overrideForm.shipmentId || !query.data?.length) {
      return;
    }

    setOverrideForm((current) => ({ ...current, shipmentId: query.data[0].id }));
  }, [overrideForm.shipmentId, query.data]);

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
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
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
              onClick={() => auditInvoiceForShipment(shipment)}
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
        <div className="grid gap-1.5">
          <Label htmlFor="override-shipment">Shipment</Label>
          <Select
            value={overrideForm.shipmentId}
            onValueChange={(value) =>
              setOverrideForm((current) => ({ ...current, shipmentId: value }))
            }
          >
            <SelectTrigger id="override-shipment">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(query.data ?? []).map((shipment) => (
                <SelectItem key={shipment.id} value={shipment.id}>
                  {shipment.public_id} - {shipment.status}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="override-status">Status</Label>
          <Select
            value={overrideForm.status}
            onValueChange={(value) => setOverrideForm((current) => ({ ...current, status: value }))}
          >
            <SelectTrigger id="override-status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="needs_review">Needs review</SelectItem>
              <SelectItem value="manual_review">Manual review</SelectItem>
              <SelectItem value="cancelled">Cancelled</SelectItem>
              <SelectItem value="booked">Booked</SelectItem>
              <SelectItem value="in_transit">In transit</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="override-reason grid gap-1.5">
          <Label htmlFor="override-reason">Reason</Label>
          <Input
            id="override-reason"
            value={overrideForm.reason}
            onChange={(event) =>
              setOverrideForm((current) => ({ ...current, reason: event.target.value }))
            }
          />
        </div>
        <Button disabled={overrideMutation.isPending} type="submit" variant="secondary">
          {overrideMutation.isPending ? "Recording..." : "Record override"}
        </Button>
      </form>
    </ModuleScaffold>
  );
}
