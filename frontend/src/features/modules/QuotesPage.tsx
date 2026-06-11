import { useQuery } from "@tanstack/react-query";

import { apiGet, type QuoteListItem } from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function QuotesPage() {
  const query = useQuery({
    queryKey: ["quotes"],
    queryFn: () => apiGet<QuoteListItem[]>("/quotes"),
  });

  return (
    <ModuleScaffold
      badge="Quinn Quote"
      description="Versioned quote records with status, price and currency from the backend API."
      title="Quotes"
    >
      <DataTable
        columns={[
          { key: "id", label: "ID" },
          { key: "status", label: "Status" },
          { key: "version", label: "Version" },
          {
            key: "customer_price",
            label: "Customer price",
            render: (value, row) => `${value} ${row.currency}`,
          },
        ]}
        loading={query.isLoading}
        rows={query.data}
      />
    </ModuleScaffold>
  );
}
