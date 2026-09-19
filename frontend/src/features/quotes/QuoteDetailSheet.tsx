import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, ExternalLink } from "lucide-react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusChip } from "@/components/ui/status-chip";
import {
  apiDownload,
  apiGet,
  type ApiProblem,
  type QuoteDetailResponse,
} from "@/shared/api/client";

const LINE_ITEM_LABELS: Record<string, string> = { "freight charge": "Frakt" };

export function QuoteDetailSheet({
  quoteId,
  onClose,
}: {
  quoteId: string | null;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ["quote-detail", quoteId],
    queryFn: () => apiGet<QuoteDetailResponse>(`/quotes/${quoteId}`),
    enabled: Boolean(quoteId),
  });
  const downloadMutation = useMutation<void, ApiProblem, QuoteDetailResponse>({
    mutationFn: (detail) =>
      apiDownload(`/quotes/${detail.quote.id}/pdf`, `Offert-${detail.reference}.pdf`),
  });

  const detail = query.data;
  const quote = detail?.quote;
  const request = detail?.request?.request;
  const priceLines = detail ? priceLinesFor(detail) : [];

  return (
    <Sheet open={Boolean(quoteId)} onOpenChange={(open) => (open ? undefined : onClose())}>
      <SheetContent className="flex w-full flex-col gap-5 overflow-y-auto sm:max-w-xl">
        <SheetHeader className="pr-8">
          <SheetTitle className="break-words">
            {quote
              ? `${quote.customer ?? "Okänd kund"} → ${quote.carrier_name ?? "Transportör ej vald"}`
              : "Offert"}
          </SheetTitle>
          <SheetDescription>
            {detail ? `Offert ${detail.reference}` : "Laddar offert…"}
          </SheetDescription>
        </SheetHeader>

        {query.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : query.isError || !detail || !quote ? (
          <p className="text-sm text-destructive">Kunde inte ladda offerten.</p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <StatusChip status={quote.status} />
              <span className="text-sm text-muted-foreground">Version {quote.version}</span>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                disabled={downloadMutation.isPending}
                onClick={() => downloadMutation.mutate(detail)}
              >
                <Download aria-hidden="true" />
                {downloadMutation.isPending ? "Skapar PDF…" : "Ladda ner PDF"}
              </Button>
              {quote.request_id ? (
                <Button variant="outline" onClick={() => navigate(`/cases/${quote.request_id}`)}>
                  <ExternalLink aria-hidden="true" />
                  Öppna ärendet
                </Button>
              ) : null}
            </div>
            {downloadMutation.isError ? (
              <p className="text-sm text-destructive">Kunde inte ladda ner PDF:en.</p>
            ) : null}

            <Section title="Transportuppdrag">
              <Field label="Kund" value={quote.customer ?? "—"} />
              <Field label="Transportör" value={quote.carrier_name ?? "Ej vald"} />
              <Field label="Rutt" value={quote.lane ?? "—"} />
              {request ? (
                <>
                  <Field label="Transportläge" value={request.mode.toUpperCase()} />
                  <Field
                    label="Total vikt"
                    value={request.weight_kg ? `${formatNumber(request.weight_kg)} kg` : "—"}
                  />
                </>
              ) : null}
            </Section>

            {detail.request?.cargo_lines.length ? (
              <Section title="Gods">
                <ul className="col-span-full flex flex-col gap-2">
                  {detail.request.cargo_lines.map((line) => (
                    <li key={line.id} className="rounded-md border border-border p-3 text-sm">
                      <p className="break-words font-medium">{line.description}</p>
                      <p className="text-muted-foreground">
                        {[
                          line.quantity ? `${line.quantity} st` : null,
                          line.weight_kg ? `${formatNumber(line.weight_kg)} kg` : null,
                          line.length_cm || line.width_cm || line.height_cm
                            ? `${[line.length_cm, line.width_cm, line.height_cm]
                                .map((value) => value ?? "?")
                                .join(" × ")} cm`
                            : null,
                          line.hazardous
                            ? `Farligt gods${line.un_number ? ` (UN ${line.un_number})` : ""}`
                            : null,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "—"}
                      </p>
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}

            <Section title="Pris">
              <div className="col-span-full flex flex-col gap-1 text-sm">
                {priceLines.map((line, index) => (
                  <div key={`${index}-${line.label}`} className="flex justify-between gap-4">
                    <span className="min-w-0 break-words">{line.label}</span>
                    <span className="font-mono">{formatMoney(line.amount, quote.currency)}</span>
                  </div>
                ))}
                <div className="mt-1 flex justify-between gap-4 border-t border-border pt-2 font-semibold">
                  <span>Totalt</span>
                  <span className="font-mono">{formatMoney(quote.customer_price, quote.currency)}</span>
                </div>
              </div>
            </Section>

            <Section title="Skickat till kunden">
              {detail.sent_email ? (
                <div className="col-span-full flex min-w-0 flex-col gap-2 text-sm">
                  <p className="text-muted-foreground">
                    Till {detail.sent_email.recipient} ·{" "}
                    {formatDateTime(detail.sent_email.sent_at ?? detail.sent_email.created_at)} ·{" "}
                    {detail.sent_email.status}
                  </p>
                  <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-3 font-sans text-sm">
                    {detail.sent_email.body_text}
                  </pre>
                </div>
              ) : (
                <p className="col-span-full text-sm text-muted-foreground">
                  Offerten har inte skickats till kunden ännu.
                </p>
              )}
            </Section>

            {detail.acceptance_events.length ? (
              <Section title="Händelser">
                <ul className="col-span-full flex flex-col gap-2 text-sm">
                  {detail.acceptance_events.map((event) => (
                    <li key={event.id} className="min-w-0">
                      <p className="text-muted-foreground">
                        {formatDateTime(event.created_at)} · {event.event_type}
                      </p>
                      <p className="break-words">{event.detail}</p>
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h3 className="text-[11px] font-semibold uppercase text-muted-foreground">{title}</h3>
      <div className="grid grid-cols-2 gap-3">{children}</div>
    </section>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="break-words text-sm font-medium">{value}</p>
    </div>
  );
}

function priceLinesFor(detail: QuoteDetailResponse): Array<{ label: string; amount: number }> {
  const items = detail.line_items;
  const sum = items.reduce((total, item) => total + item.amount, 0);
  // Same rule as the PDF: only itemise when the items add up to the price.
  if (items.length && Math.abs(sum - detail.quote.customer_price) < 0.01) {
    return items.map((item) => ({
      label: LINE_ITEM_LABELS[item.description.toLowerCase()] ?? item.description,
      amount: item.amount,
    }));
  }
  return [{ label: "Transport enligt ovan", amount: detail.quote.customer_price }];
}

function formatMoney(amount: number, currency: string): string {
  return `${amount.toLocaleString("sv-SE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function formatNumber(value: number): string {
  return value.toLocaleString("sv-SE");
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("sv-SE", { dateStyle: "short", timeStyle: "short" });
}
