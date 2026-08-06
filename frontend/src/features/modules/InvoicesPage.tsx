import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { StatusChip } from "@/components/ui/status-chip";
import { apiGet, type InvoiceListItem } from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function InvoicesPage() {
  const [searchParams] = useSearchParams();
  const query = useQuery({
    queryKey: ["invoices"],
    queryFn: () => apiGet<InvoiceListItem[]>("/invoices"),
  });

  return (
    <ModuleScaffold
      badge="Auri Audit"
      description="Granskning av transportörsfakturor mot accepterat offertbelopp och avvikelseregler."
      title="Fakturor"
    >
      <DataTable
        columns={[
          { key: "public_id", label: "ID", mono: true },
          { key: "shipment_id", label: "Sändning", mono: true },
          {
            key: "status",
            label: "Status",
            render: (value) => <StatusChip status={String(value)} />,
          },
          {
            key: "invoice_amount",
            label: "Faktura",
            align: "right",
            mono: true,
            render: (value, row) => `${value} ${row.currency}`,
          },
          {
            key: "quote_amount",
            label: "Offert",
            align: "right",
            mono: true,
            render: (value, row) => `${value} ${row.currency}`,
          },
          {
            key: "discrepancy_amount",
            label: "Avvikelse",
            align: "right",
            mono: true,
          },
        ]}
        highlightId={searchParams.get("highlight") ?? undefined}
        loading={query.isLoading}
        rows={query.data}
      />
    </ModuleScaffold>
  );
}
