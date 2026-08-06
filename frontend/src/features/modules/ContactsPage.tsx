import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { apiGet, type ContactListItem } from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function ContactsPage() {
  const [searchParams] = useSearchParams();
  const query = useQuery({
    queryKey: ["contacts"],
    queryFn: () => apiGet<ContactListItem[]>("/contacts"),
  });

  return (
    <ModuleScaffold
      badge="Miles Match"
      description="CRM-kontakter som används för att matcha inkommande avsändare, standardpriser och kundvillkor."
      title="Kontakter"
    >
      <DataTable
        columns={[
          { key: "public_id", label: "ID", mono: true },
          { key: "display_name", label: "Kund" },
          { key: "email", label: "E-post" },
          { key: "domain", label: "Domän" },
          {
            key: "default_markup_percent",
            label: "Påslag",
            align: "right",
            mono: true,
            render: (value) => `${Number(value).toFixed(1)}%`,
          },
          { key: "default_incoterms", label: "Incoterms" },
          { key: "payment_terms", label: "Villkor" },
        ]}
        highlightId={searchParams.get("highlight") ?? undefined}
        loading={query.isLoading}
        rows={query.data}
      />
    </ModuleScaffold>
  );
}
