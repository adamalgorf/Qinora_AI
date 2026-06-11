import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  apiGet,
  apiPost,
  type CreateQuotePayload,
  type QuoteListItem,
} from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function QuotesPage() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["quotes"],
    queryFn: () => apiGet<QuoteListItem[]>("/quotes"),
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
    mutationFn: (quoteId: string) => apiPost<QuoteListItem, Record<string, never>>(`/quotes/${quoteId}/send`, {}),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["quotes"] });
    },
    onError: (problem: { detail?: string }) => {
      setError(problem.detail ?? "Quote could not be sent");
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
      </div>
    </ModuleScaffold>
  );
}
