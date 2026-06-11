import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  apiGet,
  apiPost,
  type ApiProblem,
  type CreateRequestPayload,
  type CreateRequestResponse,
  type RequestListItem,
} from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

type CargoLineForm = {
  id: string;
  description: string;
  quantity: string;
  weightKg: string;
  lengthCm: string;
  widthCm: string;
  heightCm: string;
};

function createCargoLine(overrides: Partial<CargoLineForm> = {}): CargoLineForm {
  return {
    id: crypto.randomUUID(),
    description: "",
    quantity: "1",
    weightKg: "",
    lengthCm: "",
    widthCm: "",
    heightCm: "",
    ...overrides,
  };
}

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
    mode: "ltl" as CreateRequestPayload["mode"],
    loadingTime: "2026-06-11T10:00:00Z",
  });
  const [cargoLines, setCargoLines] = useState<CargoLineForm[]>([
    createCargoLine({
      description: "Pallets",
      weightKg: "440",
      lengthCm: "120",
      widthCm: "80",
      heightCm: "150",
    }),
  ]);
  const createMutation = useMutation<CreateRequestResponse, ApiProblem, CreateRequestPayload>({
    mutationFn: (payload: CreateRequestPayload) =>
      apiPost<CreateRequestResponse, CreateRequestPayload>("/requests", payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["requests"] }),
      ]);
    },
  });

  function updateField(field: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function updateCargoLine(id: string, field: keyof Omit<CargoLineForm, "id">, value: string) {
    setCargoLines((current) =>
      current.map((line) => (line.id === id ? { ...line, [field]: value } : line)),
    );
  }

  function addCargoLine() {
    setCargoLines((current) => [...current, createCargoLine()]);
  }

  function removeCargoLine(id: string) {
    setCargoLines((current) => current.filter((line) => line.id !== id));
  }

  function submitRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    createMutation.mutate({
      customer: form.customer,
      origin: form.origin,
      destination: form.destination,
      mode: form.mode,
      loading_time: form.loadingTime,
      cargo: cargoLines.map((line) => ({
        description: line.description,
        quantity: parseOptionalNumber(line.quantity),
        weight_kg: parseOptionalNumber(line.weightKg),
        length_cm: parseOptionalNumber(line.lengthCm),
        width_cm: parseOptionalNumber(line.widthCm),
        height_cm: parseOptionalNumber(line.heightCm),
      })),
    });
  }

  return (
    <ModuleScaffold
      badge="Nora + Parsek"
      description="Parsed customer transport requests with modes, lanes and validation states."
      title="Requests"
    >
      <form className="request-form" onSubmit={submitRequest}>
        <div className="request-section">
          <div className="request-section-header">
            <div>
              <span>Transport order</span>
              <strong>Lane and service</strong>
            </div>
          </div>
          <div className="request-grid">
            <label>
              Customer
              <input
                aria-label="Customer"
                value={form.customer}
                onChange={(event) => updateField("customer", event.target.value)}
              />
            </label>
            <label>
              Origin
              <input
                aria-label="Origin"
                value={form.origin}
                onChange={(event) => updateField("origin", event.target.value)}
              />
            </label>
            <label>
              Destination
              <input
                aria-label="Destination"
                value={form.destination}
                onChange={(event) => updateField("destination", event.target.value)}
              />
            </label>
            <label>
              Mode
              <select
                aria-label="Mode"
                value={form.mode}
                onChange={(event) =>
                  updateField("mode", event.target.value as CreateRequestPayload["mode"])
                }
              >
                <option value="ltl">LTL</option>
                <option value="ftl">FTL</option>
                <option value="air">Air</option>
                <option value="ocean">Ocean</option>
                <option value="rail">Rail</option>
                <option value="intermodal">Intermodal</option>
              </select>
            </label>
            <label>
              Loading time
              <input
                aria-label="Loading time"
                value={form.loadingTime}
                onChange={(event) => updateField("loadingTime", event.target.value)}
              />
            </label>
          </div>
        </div>

        <div className="request-section">
          <div className="request-section-header">
            <div>
              <span>Cargo</span>
              <strong>{cargoLines.length} line{cargoLines.length === 1 ? "" : "s"}</strong>
            </div>
            <Button type="button" variant="secondary" onClick={addCargoLine}>
              <Plus aria-hidden="true" />
              Add line
            </Button>
          </div>
          <div className="cargo-lines">
            {cargoLines.map((line, index) => (
              <div className="cargo-line" key={line.id}>
                <label className="cargo-description">
                  Description
                  <input
                    aria-label={`Cargo ${index + 1} description`}
                    value={line.description}
                    onChange={(event) =>
                      updateCargoLine(line.id, "description", event.target.value)
                    }
                  />
                </label>
                <label>
                  Qty
                  <input
                    aria-label={`Cargo ${index + 1} quantity`}
                    inputMode="numeric"
                    value={line.quantity}
                    onChange={(event) => updateCargoLine(line.id, "quantity", event.target.value)}
                  />
                </label>
                <label>
                  Kg
                  <input
                    aria-label={`Cargo ${index + 1} weight`}
                    inputMode="decimal"
                    value={line.weightKg}
                    onChange={(event) => updateCargoLine(line.id, "weightKg", event.target.value)}
                  />
                </label>
                <label>
                  L cm
                  <input
                    aria-label={`Cargo ${index + 1} length`}
                    inputMode="decimal"
                    value={line.lengthCm}
                    onChange={(event) => updateCargoLine(line.id, "lengthCm", event.target.value)}
                  />
                </label>
                <label>
                  W cm
                  <input
                    aria-label={`Cargo ${index + 1} width`}
                    inputMode="decimal"
                    value={line.widthCm}
                    onChange={(event) => updateCargoLine(line.id, "widthCm", event.target.value)}
                  />
                </label>
                <label>
                  H cm
                  <input
                    aria-label={`Cargo ${index + 1} height`}
                    inputMode="decimal"
                    value={line.heightCm}
                    onChange={(event) => updateCargoLine(line.id, "heightCm", event.target.value)}
                  />
                </label>
                <Button
                  aria-label={`Remove cargo ${index + 1}`}
                  disabled={cargoLines.length === 1}
                  size="icon"
                  type="button"
                  variant="ghost"
                  onClick={() => removeCargoLine(line.id)}
                >
                  <Trash2 aria-hidden="true" />
                </Button>
              </div>
            ))}
          </div>
        </div>

        <div className="request-submit">
          <Button disabled={createMutation.isPending} type="submit">
            {createMutation.isPending ? "Creating..." : "Create request"}
          </Button>
        </div>
      </form>
      {createMutation.data?.review_reason ? (
        <p className="form-feedback">{createMutation.data.review_reason}</p>
      ) : null}
      {createMutation.data?.complete ? (
        <p className="form-success">Request parsed and ready for quoting.</p>
      ) : null}
      {createMutation.error ? (
        <p className="form-feedback">{createMutation.error.detail ?? createMutation.error.title}</p>
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

function parseOptionalNumber(value: string): number | undefined {
  const trimmed = value.trim();
  return trimmed ? Number(trimmed) : undefined;
}
