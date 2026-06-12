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
      description="CRM contacts used to match inbound senders, pricing defaults and customer terms."
      title="Contacts"
    >
      <DataTable
        columns={[
          { key: "public_id", label: "ID" },
          { key: "display_name", label: "Customer" },
          { key: "email", label: "Email" },
          { key: "domain", label: "Domain" },
          {
            key: "default_markup_percent",
            label: "Markup",
            render: (value) => `${Number(value).toFixed(1)}%`,
          },
          { key: "default_incoterms", label: "Incoterms" },
          { key: "payment_terms", label: "Terms" },
        ]}
        highlightId={searchParams.get("highlight") ?? undefined}
        loading={query.isLoading}
        rows={query.data}
      />
    </ModuleScaffold>
  );
}
