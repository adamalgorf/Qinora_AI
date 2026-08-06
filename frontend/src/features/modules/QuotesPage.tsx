import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { StatusChip } from "@/components/ui/status-chip";
import {
  apiGet,
  apiPost,
  type AcceptQuotePayload,
  type AcceptQuoteResponse,
  type CreateQuotePayload,
  type OutboundReplyItem,
  type ProcessOutboundQueueResponse,
  type QuoteDetailResponse,
  type QuoteReplyPayload,
  type QuoteReplyResponse,
  type QuoteListItem,
  type RequestListItem,
  type SendQuoteResponse,
} from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function QuotesPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const query = useQuery({
    queryKey: ["quotes"],
    queryFn: () => apiGet<QuoteListItem[]>("/quotes"),
  });
  const outboundQuery = useQuery({
    queryKey: ["outbound-replies"],
    queryFn: () => apiGet<OutboundReplyItem[]>("/emails/outbound"),
  });
  const requestsQuery = useQuery({
    queryKey: ["requests"],
    queryFn: () => apiGet<RequestListItem[]>("/requests"),
  });
  const [form, setForm] = useState({
    requestId: "",
    customerPrice: "12500",
    currency: "SEK",
  });
  const [selectedQuoteId, setSelectedQuoteId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const quotableRequests = useMemo(
    () =>
      (requestsQuery.data ?? []).filter((request) =>
        ["parsed", "quoted"].includes(request.status),
      ),
    [requestsQuery.data],
  );
  const detailQuery = useQuery({
    queryKey: ["quote-detail", selectedQuoteId],
    queryFn: () => apiGet<QuoteDetailResponse>(`/quotes/${selectedQuoteId}`),
    enabled: Boolean(selectedQuoteId),
  });
  const createMutation = useMutation({
    mutationFn: (payload: CreateQuotePayload) =>
      apiPost<QuoteListItem, CreateQuotePayload>("/quotes", payload),
    onSuccess: async (quote) => {
      setError(null);
      setSelectedQuoteId(quote.id);
      await queryClient.invalidateQueries({ queryKey: ["quotes"] });
    },
  });
  const sendMutation = useMutation({
    mutationFn: (quoteId: string) =>
      apiPost<SendQuoteResponse, Record<string, never>>(`/quotes/${quoteId}/send`, {}),
    onSuccess: async () => {
      setError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["quotes"] }),
        queryClient.invalidateQueries({ queryKey: ["outbound-replies"] }),
      ]);
    },
    onError: (problem: { detail?: string }) => {
      setError(problem.detail ?? "Offerten kunde inte skickas");
    },
  });
  const acceptMutation = useMutation({
    mutationFn: (quote: QuoteListItem) =>
      apiPost<AcceptQuoteResponse, AcceptQuotePayload>(
        `/quotes/${quote.id}/accept`,
        acceptancePayloadForQuote(quote),
      ),
    onSuccess: async () => {
      setError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["quotes"] }),
        queryClient.invalidateQueries({ queryKey: ["shipments"] }),
      ]);
    },
    onError: (problem: { detail?: string }) => {
      setError(problem.detail ?? "Offerten kunde inte accepteras");
    },
  });
  const replyMutation = useMutation({
    mutationFn: ({ quoteId, payload }: { quoteId: string; payload: QuoteReplyPayload }) =>
      apiPost<QuoteReplyResponse, QuoteReplyPayload>(`/quotes/${quoteId}/reply`, payload),
    onSuccess: async (result) => {
      setError(null);
      if (result.revised_quote) {
        setSelectedQuoteId(result.revised_quote.id);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["quotes"] }),
        queryClient.invalidateQueries({ queryKey: ["shipments"] }),
      ]);
    },
    onError: (problem: { detail?: string }) => {
      setError(problem.detail ?? "Svaret på offerten kunde inte tolkas");
    },
  });
  const processQueueMutation = useMutation({
    mutationFn: () =>
      apiPost<ProcessOutboundQueueResponse, { limit: number }>("/emails/outbound/process", {
        limit: 10,
      }),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["outbound-replies"] });
    },
    onError: (problem: { detail?: string }) => {
      setError(problem.detail ?? "Utgående kö kunde inte bearbetas");
    },
  });

  useEffect(() => {
    if (form.requestId || !quotableRequests.length) {
      return;
    }

    setForm((current) => ({ ...current, requestId: quotableRequests[0].id }));
  }, [form.requestId, quotableRequests]);

  useEffect(() => {
    if (selectedQuoteId || !query.data?.length) {
      return;
    }

    setSelectedQuoteId(query.data[0].id);
  }, [query.data, selectedQuoteId]);

  function requestForQuote(quote: QuoteListItem): RequestListItem | undefined {
    return (requestsQuery.data ?? []).find((request) => request.id === quote.request_id);
  }

  function acceptancePayloadForQuote(quote: QuoteListItem): AcceptQuotePayload {
    const request = requestForQuote(quote);

    return {
      mode: request?.mode ?? "ltl",
      total_weight_kg: request?.weight_kg ?? 1,
    };
  }

  function submitQuote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.requestId) {
      setError("Skapa en transportförfrågan innan du offererar.");
      return;
    }

    createMutation.mutate({
      request_id: form.requestId,
      customer_price: Number(form.customerPrice),
      currency: form.currency,
    });
  }

  return (
    <ModuleScaffold
      badge="Quinn Quote"
      description="Versionshanterade offerter med status, pris och valuta från backend-API:et."
      title="Offerter"
    >
      <form className="request-form" onSubmit={submitQuote}>
        <Select
          disabled={requestsQuery.isLoading || !quotableRequests.length}
          value={form.requestId}
          onValueChange={(value) => setForm((current) => ({ ...current, requestId: value }))}
        >
          <SelectTrigger aria-label="Förfrågan">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {quotableRequests.map((request) => (
              <SelectItem key={request.id} value={request.id}>
                {request.public_id} - {request.customer} - {request.lane}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          aria-label="Kundpris"
          inputMode="decimal"
          value={form.customerPrice}
          onChange={(event) =>
            setForm((current) => ({ ...current, customerPrice: event.target.value }))
          }
        />
        <Input
          aria-label="Valuta"
          value={form.currency}
          onChange={(event) => setForm((current) => ({ ...current, currency: event.target.value }))}
        />
        <Button disabled={createMutation.isPending} type="submit">
          {createMutation.isPending ? "Skapar…" : "Skapa offert"}
        </Button>
      </form>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <DataTable
        columns={[
          { key: "id", label: "ID", mono: true },
          {
            key: "request_id",
            label: "Förfrågan",
            mono: true,
            render: (value) => {
              const request = (requestsQuery.data ?? []).find((item) => item.id === value);
              return request?.public_id ?? String(value ?? "");
            },
          },
          {
            key: "status",
            label: "Status",
            render: (value) => <StatusChip status={String(value)} />,
          },
          { key: "version", label: "Version", align: "right" },
          {
            key: "customer_price",
            label: "Kundpris",
            align: "right",
            mono: true,
            render: (value, row) => `${value} ${row.currency}`,
          },
          {
            key: "id",
            id: "action",
            label: "Åtgärd",
            render: (value, row) =>
              row.status === "draft" || row.status === "revised"
                ? `Skicka via API: ${value}`
                : "Ingen åtgärd",
          },
        ]}
        highlightId={searchParams.get("highlight") ?? undefined}
        loading={query.isLoading}
        rows={query.data}
      />
      <div className="quote-actions">
        {(query.data ?? []).map((quote) => (
          <Button
            key={`detail-${quote.id}`}
            type="button"
            variant={quote.id === selectedQuoteId ? "default" : "secondary"}
            onClick={() => setSelectedQuoteId(quote.id)}
          >
            Detaljer {quote.id}
          </Button>
        ))}
      </div>
      <section className="quote-detail-panel" aria-label="Offertdetaljer">
        <div className="queue-panel-header">
          <h3>Kommersiell tidslinje</h3>
          <span className="text-sm text-muted-foreground">{detailQuery.data?.quote.status ?? "Ingen offert vald"}</span>
        </div>
        <div className="quote-detail-grid">
          <div>
            <h4>Radposter</h4>
            <div className="agent-list">
              {(detailQuery.data?.line_items ?? []).map((item) => (
                <div className="agent-row" key={item.id}>
                  <div>
                    <strong>{item.description}</strong>
                    <span>{item.quote_id}</span>
                  </div>
                  <span>
                    {item.amount} {item.currency}
                  </span>
                </div>
              ))}
              {!detailQuery.isLoading && (detailQuery.data?.line_items ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">Inga radposter.</p>
              ) : null}
            </div>
          </div>
          <div>
            <h4>Händelser</h4>
            <div className="timeline-list">
              {(detailQuery.data?.acceptance_events ?? []).map((event) => (
                <article className="timeline-item" key={event.id}>
                  <span>{event.event_type}</span>
                  <strong>{event.detail}</strong>
                  <small>{event.created_at}</small>
                </article>
              ))}
              {!detailQuery.isLoading &&
              (detailQuery.data?.acceptance_events ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">Inga kommersiella händelser än.</p>
              ) : null}
            </div>
          </div>
        </div>
      </section>
      <div className="quote-actions">
        {(query.data ?? [])
          .filter((quote) => quote.status === "draft" || quote.status === "revised")
          .map((quote) => (
            <Button
              key={quote.id}
              onClick={() => sendMutation.mutate(quote.id)}
              type="button"
              variant="secondary"
            >
              Skicka {quote.id}
            </Button>
          ))}
        {(query.data ?? [])
          .filter((quote) => quote.status === "sent")
          .map((quote) => (
            <div className="button-cluster" key={`reply-${quote.id}`}>
              <Button
                onClick={() =>
                  replyMutation.mutate({
                    quoteId: quote.id,
                    payload: {
                      body_text: "Accepterar, kör igång",
                      ...acceptancePayloadForQuote(quote),
                    },
                  })
                }
                type="button"
              >
                Rex accepterar {quote.id}
              </Button>
              <Button
                onClick={() =>
                  replyMutation.mutate({
                    quoteId: quote.id,
                    payload: {
                      body_text: "Vänligen revidera med lägre pris",
                      revised_customer_price: Math.max(1, quote.customer_price - 500),
                    },
                  })
                }
                type="button"
                variant="secondary"
              >
                Revidera
              </Button>
              <Button
                onClick={() =>
                  replyMutation.mutate({
                    quoteId: quote.id,
                    payload: { body_text: "Nej tack, vi avböjer offerten" },
                  })
                }
                type="button"
                variant="ghost"
              >
                Avböj
              </Button>
              <Button
                onClick={() => acceptMutation.mutate(quote)}
                type="button"
                variant="secondary"
              >
                Direktacceptera
              </Button>
            </div>
          ))}
      </div>
      <section className="queue-panel" aria-label="Utgående svarskö">
        <div className="queue-panel-header">
          <h3>Utgående svarskö</h3>
          <Button
            disabled={processQueueMutation.isPending}
            onClick={() => processQueueMutation.mutate()}
            type="button"
            variant="secondary"
          >
            {processQueueMutation.isPending ? "Bearbetar…" : "Bearbeta kö"}
          </Button>
        </div>
        <div className="agent-list">
          {(outboundQuery.data ?? []).map((reply) => (
            <div className="agent-row" key={reply.id}>
              <div>
                <strong>{reply.subject}</strong>
                <span>{reply.recipient}</span>
              </div>
              <span>{reply.status}</span>
            </div>
          ))}
          {!outboundQuery.isLoading && (outboundQuery.data ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">Inga köade svar.</p>
          ) : null}
        </div>
      </section>
    </ModuleScaffold>
  );
}
