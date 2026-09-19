import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { KpiCard, KpiGrid } from "@/components/patterns/KpiCard";
import { PageShell } from "@/components/patterns/PageShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { StatusChip } from "@/components/ui/status-chip";
import { DataTable } from "@/features/modules/DataTable";
import {
  apiGet,
  apiPost,
  type ApiProblem,
  type CaseListItem,
  type QuoteListItem,
} from "@/shared/api/client";

import { QuoteDetailSheet } from "./QuoteDetailSheet";

export function QuotesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [requestId, setRequestId] = useState("");
  const [price, setPrice] = useState("");
  const [currency, setCurrency] = useState("SEK");
  const [openQuoteId, setOpenQuoteId] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["quotes"],
    queryFn: () => apiGet<QuoteListItem[]>("/quotes"),
  });

  const casesQuery = useQuery({
    queryKey: ["cases"],
    queryFn: () => apiGet<CaseListItem[]>("/cases"),
    enabled: createOpen,
  });
  const createMutation = useMutation<
    QuoteListItem,
    ApiProblem,
    { request_id: string; customer_price: number; currency: string }
  >({
    mutationFn: (payload) => apiPost<QuoteListItem, typeof payload>("/quotes", payload),
    onSuccess: async (quote) => {
      await queryClient.invalidateQueries({ queryKey: ["quotes"] });
      await queryClient.invalidateQueries({ queryKey: ["cases"] });
      setCreateOpen(false);
      setRequestId("");
      setPrice("");
      setOpenQuoteId(quote.id);
    },
  });
  const priceValue = Number(price.replace(",", "."));
  const canCreate = Boolean(requestId) && Number.isFinite(priceValue) && priceValue > 0;

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
            <Button
              onClick={() => {
                createMutation.reset();
                setCreateOpen(true);
              }}
            >
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

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Skapa offert</DialogTitle>
            <DialogDescription>
              Välj ärendet offerten gäller och ange kundpris. Offerten skapas som utkast.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label>Ärende</Label>
              <Select value={requestId} onValueChange={setRequestId}>
                <SelectTrigger>
                  <SelectValue
                    placeholder={casesQuery.isLoading ? "Laddar ärenden…" : "Välj ärende"}
                  />
                </SelectTrigger>
                <SelectContent>
                  {(casesQuery.data ?? []).map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.public_id} · {c.customer} · {c.lane}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-[minmax(0,1fr)_7rem] gap-3">
              <div className="flex flex-col gap-2">
                <Label htmlFor="quote-price">Kundpris</Label>
                <Input
                  id="quote-price"
                  inputMode="decimal"
                  placeholder="0"
                  value={price}
                  onChange={(event) => setPrice(event.target.value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label>Valuta</Label>
                <Select value={currency} onValueChange={setCurrency}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {["SEK", "EUR", "NOK", "DKK"].map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {createMutation.error ? (
              <p className="break-words text-sm text-destructive">
                {createMutation.error.detail ?? createMutation.error.title}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Avbryt
            </Button>
            <Button
              disabled={!canCreate || createMutation.isPending}
              onClick={() =>
                createMutation.mutate({
                  request_id: requestId,
                  customer_price: priceValue,
                  currency,
                })
              }
            >
              {createMutation.isPending ? "Skapar…" : "Skapa offert"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <QuoteDetailSheet quoteId={openQuoteId} onClose={() => setOpenQuoteId(null)} />
    </PageShell>
  );
}
