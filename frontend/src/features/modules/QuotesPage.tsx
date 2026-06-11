import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  apiGet,
  apiPost,
  type AcceptQuotePayload,
  type AcceptQuoteResponse,
  type CreateQuotePayload,
  type OutboundReplyItem,
  type ProcessOutboundQueueResponse,
  type QuoteListItem,
  type SendQuoteResponse,
} from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function QuotesPage() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["quotes"],
    queryFn: () => apiGet<QuoteListItem[]>("/quotes"),
  });
  const outboundQuery = useQuery({
    queryKey: ["outbound-replies"],
    queryFn: () => apiGet<OutboundReplyItem[]>("/emails/outbound"),
  });
  const [form, setForm] = useState({
    requestId: "req-001",
    customerPrice: "12500",
    currency: "SEK",
  });
  const [error, setError] = useState<string | null>(null);
  const createMutation = useMutation({
    mutationFn: (payload: CreateQuotePayload) =>
      apiPost<QuoteListItem, CreateQuotePayload>("/quotes", payload),
    onSuccess: async () => {
      setError(null);
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
    mutationFn: (quoteId: string) =>
      apiPost<AcceptQuoteResponse, AcceptQuotePayload>(`/quotes/${quoteId}/accept`, {
        mode: "ltl",
        total_weight_kg: 820,
        requested_carrier_name: "Nordic",
      }),
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

  function submitQuote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
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
        <input
          aria-label="Request ID"
          value={form.requestId}
          onChange={(event) => setForm((current) => ({ ...current, requestId: event.target.value }))}
        />
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
        loading={query.isLoading}
        rows={query.data}
      />
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
            <Button
              key={`accept-${quote.id}`}
              onClick={() => acceptMutation.mutate(quote.id)}
              type="button"
            >
              Accept {quote.id}
            </Button>
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
