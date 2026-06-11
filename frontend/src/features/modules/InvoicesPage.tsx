import { useQuery } from "@tanstack/react-query";

import { apiGet, type InvoiceListItem } from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function InvoicesPage() {
  const query = useQuery({
    queryKey: ["invoices"],
    queryFn: () => apiGet<InvoiceListItem[]>("/invoices"),
  });

  return (
    <ModuleScaffold
      badge="Auri Audit"
      description="Carrier invoice audit against accepted quote amount and discrepancy rules."
      title="Invoices"
    >
      <DataTable
        columns={[
          { key: "public_id", label: "ID" },
          { key: "shipment_id", label: "Shipment" },
          { key: "status", label: "Status" },
          {
            key: "invoice_amount",
            label: "Invoice",
            render: (value, row) => `${value} ${row.currency}`,
          },
          {
            key: "quote_amount",
            label: "Quote",
            render: (value, row) => `${value} ${row.currency}`,
          },
          { key: "discrepancy_amount", label: "Discrepancy" },
        ]}
        loading={query.isLoading}
        rows={query.data}
      />
    </ModuleScaffold>
  );
}
