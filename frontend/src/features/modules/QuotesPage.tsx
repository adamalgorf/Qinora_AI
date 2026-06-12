import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
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
      setError(problem.detail ?? "Quote could not be sent");
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
      setError(problem.detail ?? "Quote could not be accepted");
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
      setError(problem.detail ?? "Quote reply could not be interpreted");
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
      setError(problem.detail ?? "Outbound queue could not be processed");
    },
  });

  useEffect(() => {
    if (form.requestId || !requestsQuery.data?.length) {
      return;
    }

    setForm((current) => ({ ...current, requestId: requestsQuery.data[0].id }));
  }, [form.requestId, requestsQuery.data]);

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
      setError("Create a transport request before quoting.");
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
      description="Versioned quote records with status, price and currency from the backend API."
      title="Quotes"
    >
      <form className="request-form" onSubmit={submitQuote}>
        <select
          aria-label="Request ID"
          disabled={requestsQuery.isLoading || !requestsQuery.data?.length}
          value={form.requestId}
          onChange={(event) => setForm((current) => ({ ...current, requestId: event.target.value }))}
        >
          {(requestsQuery.data ?? []).map((request) => (
            <option key={request.id} value={request.id}>
              {request.public_id} - {request.customer} - {request.lane}
            </option>
          ))}
        </select>
        <input
          aria-label="Customer price"
          inputMode="decimal"
          value={form.customerPrice}
          onChange={(event) =>
            setForm((current) => ({ ...current, customerPrice: event.target.value }))
          }
        />
        <input
          aria-label="Currency"
          value={form.currency}
          onChange={(event) => setForm((current) => ({ ...current, currency: event.target.value }))}
        />
        <Button disabled={createMutation.isPending} type="submit">
          {createMutation.isPending ? "Creating..." : "Create quote"}
        </Button>
      </form>
      {error ? <p className="form-feedback">{error}</p> : null}
      <DataTable
        columns={[
          { key: "id", label: "ID" },
          {
            key: "request_id",
            label: "Request",
            render: (value) => {
              const request = (requestsQuery.data ?? []).find((item) => item.id === value);
              return request?.public_id ?? String(value ?? "");
            },
          },
          { key: "status", label: "Status" },
          { key: "version", label: "Version" },
          {
            key: "customer_price",
            label: "Customer price",
            render: (value, row) => `${value} ${row.currency}`,
          },
          {
            key: "id",
            label: "Action",
            render: (value, row) =>
              row.status === "draft" || row.status === "revised"
                ? `Send via API: ${value}`
                : "No action",
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
            Details {quote.id}
          </Button>
        ))}
      </div>
      <section className="quote-detail-panel" aria-label="Quote detail">
        <div className="queue-panel-header">
          <h3>Commercial timeline</h3>
          <span className="muted">{detailQuery.data?.quote.status ?? "No quote selected"}</span>
        </div>
        <div className="quote-detail-grid">
          <div>
            <h4>Line items</h4>
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
                <p className="muted">No line items.</p>
              ) : null}
            </div>
          </div>
          <div>
            <h4>Events</h4>
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
                <p className="muted">No commercial events yet.</p>
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
              Send {quote.id}
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
                      body_text: "Accepted, please go ahead",
                      ...acceptancePayloadForQuote(quote),
                    },
                  })
                }
                type="button"
              >
                Rex accept {quote.id}
              </Button>
              <Button
                onClick={() =>
                  replyMutation.mutate({
                    quoteId: quote.id,
                    payload: {
                      body_text: "Please revise with a lower price",
                      revised_customer_price: Math.max(1, quote.customer_price - 500),
                    },
                  })
                }
                type="button"
                variant="secondary"
              >
                Revise
              </Button>
              <Button
                onClick={() =>
                  replyMutation.mutate({
                    quoteId: quote.id,
                    payload: { body_text: "No thanks, we reject this quote" },
                  })
                }
                type="button"
                variant="ghost"
              >
                Reject
              </Button>
              <Button
                onClick={() => acceptMutation.mutate(quote)}
                type="button"
                variant="secondary"
              >
                Direct accept
              </Button>
            </div>
          ))}
      </div>
      <section className="queue-panel" aria-label="Outbound reply queue">
        <div className="queue-panel-header">
          <h3>Outbound reply queue</h3>
          <Button
            disabled={processQueueMutation.isPending}
            onClick={() => processQueueMutation.mutate()}
            type="button"
            variant="secondary"
          >
            {processQueueMutation.isPending ? "Processing..." : "Process queue"}
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
            <p className="muted">No queued replies.</p>
          ) : null}
        </div>
      </section>
    </ModuleScaffold>
  );
}
