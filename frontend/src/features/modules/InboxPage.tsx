import { useQuery } from "@tanstack/react-query";

import { apiGet, type InboxListItem } from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function InboxPage() {
  const query = useQuery({
    queryKey: ["inbox"],
    queryFn: () => apiGet<InboxListItem[]>("/inbox/pending"),
  });

  return (
    <ModuleScaffold
      badge="Email relay"
      description="Inbound messages ready for Nora Intake, invoice audit or operator review."
      title="Inbox"
    >
      <DataTable
        columns={[
          { key: "sender", label: "Sender" },
          { key: "subject", label: "Subject" },
          { key: "classification", label: "Classification" },
          { key: "received_at", label: "Received" },
        ]}
        loading={query.isLoading}
        rows={query.data}
      />
    </ModuleScaffold>
  );
}
