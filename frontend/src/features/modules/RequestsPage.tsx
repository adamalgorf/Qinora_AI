import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  apiGet,
  apiPost,
  type CreateRequestPayload,
  type CreateRequestResponse,
  type RequestListItem,
} from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function RequestsPage() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["requests"],
    queryFn: () => apiGet<RequestListItem[]>("/requests"),
  });
  const [form, setForm] = useState({
    customer: "Scania",
    origin: "Sodertalje",
    destination: "Berlin",
    mode: "ltl",
    loadingTime: "2026-06-11T10:00:00Z",
    description: "Pallets",
    weightKg: "440",
    lengthCm: "120",
    widthCm: "80",
    heightCm: "150",
  });
  const createMutation = useMutation({
    mutationFn: (payload: CreateRequestPayload) =>
      apiPost<CreateRequestResponse, CreateRequestPayload>("/requests", payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["requests"] });
    },
  });

  function updateField(field: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function submitRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    createMutation.mutate({
      customer: form.customer,
      origin: form.origin,
      destination: form.destination,
      mode: form.mode,
      loading_time: form.loadingTime,
      cargo: [
        {
          description: form.description,
          quantity: 1,
          weight_kg: Number(form.weightKg),
          length_cm: Number(form.lengthCm),
          width_cm: Number(form.widthCm),
          height_cm: Number(form.heightCm),
        },
      ],
    });
  }

  return (
    <ModuleScaffold
      badge="Nora + Parsek"
      description="Parsed customer transport requests with modes, lanes and validation states."
      title="Requests"
    >
      <form className="request-form" onSubmit={submitRequest}>
        <input
          aria-label="Customer"
          value={form.customer}
          onChange={(event) => updateField("customer", event.target.value)}
        />
        <input
          aria-label="Origin"
          value={form.origin}
          onChange={(event) => updateField("origin", event.target.value)}
        />
        <input
          aria-label="Destination"
          value={form.destination}
          onChange={(event) => updateField("destination", event.target.value)}
        />
        <select
          aria-label="Mode"
          value={form.mode}
          onChange={(event) => updateField("mode", event.target.value)}
        >
          <option value="ltl">LTL</option>
          <option value="ftl">FTL</option>
          <option value="air">Air</option>
          <option value="ocean">Ocean</option>
          <option value="rail">Rail</option>
          <option value="intermodal">Intermodal</option>
        </select>
        <input
          aria-label="Loading time"
          value={form.loadingTime}
          onChange={(event) => updateField("loadingTime", event.target.value)}
        />
        <input
          aria-label="Cargo description"
          value={form.description}
          onChange={(event) => updateField("description", event.target.value)}
        />
        <input
          aria-label="Weight"
          inputMode="decimal"
          value={form.weightKg}
          onChange={(event) => updateField("weightKg", event.target.value)}
        />
        <input
          aria-label="Length"
          inputMode="decimal"
          value={form.lengthCm}
          onChange={(event) => updateField("lengthCm", event.target.value)}
        />
        <input
          aria-label="Width"
          inputMode="decimal"
          value={form.widthCm}
          onChange={(event) => updateField("widthCm", event.target.value)}
        />
        <input
          aria-label="Height"
          inputMode="decimal"
          value={form.heightCm}
          onChange={(event) => updateField("heightCm", event.target.value)}
        />
        <Button disabled={createMutation.isPending} type="submit">
          {createMutation.isPending ? "Creating..." : "Create request"}
        </Button>
      </form>
      {createMutation.data?.review_reason ? (
        <p className="form-feedback">{createMutation.data.review_reason}</p>
      ) : null}
      <DataTable
        columns={[
          { key: "public_id", label: "ID" },
          { key: "customer", label: "Customer" },
          { key: "lane", label: "Lane" },
          { key: "mode", label: "Mode" },
          { key: "status", label: "Status" },
          { key: "weight_kg", label: "Weight kg" },
        ]}
        loading={query.isLoading}
        rows={query.data}
      />
    </ModuleScaffold>
  );
}
