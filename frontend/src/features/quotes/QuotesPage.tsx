import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { KpiCard, KpiGrid } from "@/components/patterns/KpiCard";
import { PageShell } from "@/components/patterns/PageShell";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { StatusChip } from "@/components/ui/status-chip";
import { DataTable } from "@/features/modules/DataTable";
import { apiGet, type CaseListItem, type QuoteListItem } from "@/shared/api/client";

export function QuotesPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const query = useQuery({
    queryKey: ["quotes"],
    queryFn: () => apiGet<QuoteListItem[]>("/quotes"),
  });
  const casesQuery = useQuery({
    queryKey: ["cases"],
    queryFn: () => apiGet<CaseListItem[]>("/cases"),
  });

  const caseByRequestId = useMemo(() => {
    const map = new Map<string, CaseListItem>();
    for (const c of casesQuery.data ?? []) map.set(c.id, c);
    return map;
  }, [casesQuery.data]);

  const rows = useMemo(() => {
    const quotes = query.data ?? [];
    const withCustomer = quotes.map((quote) => ({
      ...quote,
      customer: quote.request_id ? (caseByRequestId.get(quote.request_id)?.customer ?? "—") : "—",
      lane: quote.request_id ? (caseByRequestId.get(quote.request_id)?.lane ?? "—") : "—",
    }));
    if (!search.trim()) return withCustomer;
    const needle = search.trim().toLowerCase();
    return withCustomer.filter(
      (q) => q.customer.toLowerCase().includes(needle) || q.id.toLowerCase().includes(needle),
    );
  }, [query.data, caseByRequestId, search]);

  const today = rows.length;
  const converted = rows.filter((r) => r.status === "accepted" || r.status === "converted").length;
  const conversionRate = today > 0 ? Math.round((converted / today) * 100) : 0;
  const pendingReply = rows.filter((r) => r.status === "sent").length;

  return (
    <PageShell subtitle="Automatiserad Pipeline" title="Offerter">
      <KpiGrid>
        <KpiCard label="Genererade offerter" value={today} />
        <KpiCard label="Konverteringsgrad" trend={{ label: "Toppresultat" }} value={`${conversionRate}%`} />
        <KpiCard label="Väntar på svar" value={pendingReply} />
      </KpiGrid>

      <Card>
        <CardContent className="flex flex-col gap-4 p-5">
          <Input
            className="max-w-sm"
            placeholder="Sök efter kund eller offert-ID…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <DataTable
            columns={[
              { key: "id", label: "Offert-ID", mono: true },
              { key: "customer", label: "Kund" },
              { key: "lane", label: "Rutt" },
              {
                key: "customer_price",
                label: "Pris",
                align: "right",
                mono: true,
                render: (value, row) => `${value} ${row.currency}`,
              },
              { key: "version", label: "Version", align: "right" },
              {
                key: "status",
                label: "Status",
                render: (value) => <StatusChip status={String(value)} />,
              },
            ]}
            loading={query.isLoading}
            rows={rows}
            onRowClick={(row) =>
              row.request_id ? navigate(`/cases/${row.request_id}`) : undefined
            }
          />
        </CardContent>
      </Card>
    </PageShell>
  );
}
