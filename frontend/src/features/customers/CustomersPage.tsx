import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { PageShell } from "@/components/patterns/PageShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusChip } from "@/components/ui/status-chip";
import { DataTable } from "@/features/modules/DataTable";
import { apiGet, type ContactListItem, type CustomerDetailResponse } from "@/shared/api/client";

export function CustomersPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["contacts"],
    queryFn: () => apiGet<ContactListItem[]>("/contacts"),
  });
  const detailQuery = useQuery({
    queryKey: ["contact-detail", selectedId],
    queryFn: () => apiGet<CustomerDetailResponse>(`/contacts/${selectedId}`),
    enabled: Boolean(selectedId),
  });

  useEffect(() => {
    if (!selectedId && query.data?.length) {
      setSelectedId(query.data[0].id);
    }
  }, [query.data, selectedId]);

  const detail = detailQuery.data;

  return (
    <PageShell subtitle="Logistikportfölj" title="Kunder">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardContent className="p-5">
            <h2 className="mb-4 text-base font-semibold">Aktiva kundkonton</h2>
            <DataTable
              columns={[
                { key: "display_name", label: "Kundnamn" },
                {
                  key: "health_status",
                  label: "Hälsa",
                  render: (value) => <StatusChip status={String(value)} />,
                },
                {
                  key: "annual_volume_estimate",
                  label: "Årlig volym",
                  align: "right",
                  render: (value) => (value ? `${value} SEK/år` : "—"),
                },
                {
                  key: "sla_tolerance_hours",
                  label: "SLA-tolerans",
                  align: "right",
                  render: (value) => (value ? `${value}h` : "—"),
                },
                { key: "account_owner", label: "Ansvarig", render: (value) => String(value ?? "—") },
              ]}
              loading={query.isLoading}
              rows={query.data}
              onRowClick={(row) => setSelectedId(row.id)}
            />
          </CardContent>
        </Card>

        <Card className="h-fit">
          <CardContent className="flex flex-col gap-4 p-5">
            {detailQuery.isLoading ? (
              <Skeleton className="h-40 w-full" />
            ) : detail ? (
              <>
                <div className="min-w-0">
                  <h2 className="break-words text-lg font-semibold">{detail.display_name}</h2>
                  <p className="break-words text-sm text-muted-foreground">
                    {detail.segment ?? "—"}
                    {detail.customer_since ? ` · Kund sedan ${detail.customer_since}` : ""}
                  </p>
                </div>
                <DetailField label="Aktiv ruttoptimering" value={detail.active_route ?? "—"} />
                <DetailField
                  label="Medelsvarstid AI"
                  value={
                    detail.avg_ai_response_minutes
                      ? `${detail.avg_ai_response_minutes.toFixed(1)} minuter`
                      : "—"
                  }
                />
                <DetailField label="Aktiva jobb" value={String(detail.active_jobs)} />
                <DetailField label="Tullkontakt" value={detail.customs_contact_name ?? "—"} />
                <DetailField
                  label="Senaste avtalsuppdatering"
                  value={detail.contract_note ?? "—"}
                />
                <Badge variant="outline">{detail.health_status}</Badge>
                <Button className="mt-2">Kontakta Account Owner</Button>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Välj en kund i listan.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </PageShell>
  );
}

function DetailField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-semibold uppercase text-muted-foreground">{label}</p>
      <p className="break-words text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}
