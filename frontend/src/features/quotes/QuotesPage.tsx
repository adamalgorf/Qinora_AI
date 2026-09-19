import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { KpiCard, KpiGrid } from "@/components/patterns/KpiCard";
import { PageShell } from "@/components/patterns/PageShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { StatusChip } from "@/components/ui/status-chip";
import { DataTable } from "@/features/modules/DataTable";
import { apiGet, type QuoteListItem } from "@/shared/api/client";

import { QuoteDetailSheet } from "./QuoteDetailSheet";

export function QuotesPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [openQuoteId, setOpenQuoteId] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["quotes"],
    queryFn: () => apiGet<QuoteListItem[]>("/quotes"),
  });

  const rows = useMemo(() => {
    const quotes = (query.data ?? []).map((quote) => ({
      ...quote,
      title: `${quote.customer ?? "Okänd kund"} → ${quote.carrier_name ?? "Transportör ej vald"}`,
      lane: quote.lane ?? "—",
    }));
    if (!search.trim()) return quotes;
    const needle = search.trim().toLowerCase();
    return quotes.filter(
      (q) => q.title.toLowerCase().includes(needle) || q.id.toLowerCase().includes(needle),
    );
  }, [query.data, search]);

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
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Input
              className="max-w-sm"
              placeholder="Sök efter kund eller transportör…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <Button variant="secondary" onClick={() => navigate("/cases")}>
              Skapa offert
            </Button>
          </div>
          <DataTable
            columns={[
              { key: "title", label: "Kund → Transportör" },
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
            onRowClick={(row) => setOpenQuoteId(row.id)}
          />
        </CardContent>
      </Card>

      <QuoteDetailSheet quoteId={openQuoteId} onClose={() => setOpenQuoteId(null)} />
    </PageShell>
  );
}
