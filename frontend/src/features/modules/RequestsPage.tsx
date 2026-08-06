import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  apiGet,
  apiPost,
  type ApiProblem,
  type CreateRequestPayload,
  type CreateRequestResponse,
  type RequestDetailResponse,
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
  const [searchParams] = useSearchParams();
  const query = useQuery({
    queryKey: ["requests"],
    queryFn: () => apiGet<RequestListItem[]>("/requests"),
  });
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const detailQuery = useQuery({
    queryKey: ["request-detail", selectedRequestId],
    queryFn: () => apiGet<RequestDetailResponse>(`/requests/${selectedRequestId}`),
    enabled: Boolean(selectedRequestId),
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
            <div className="grid gap-1.5">
              <Label htmlFor="request-customer">Customer</Label>
              <Input
                id="request-customer"
                value={form.customer}
                onChange={(event) => updateField("customer", event.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="request-origin">Origin</Label>
              <Input
                id="request-origin"
                value={form.origin}
                onChange={(event) => updateField("origin", event.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="request-destination">Destination</Label>
              <Input
                id="request-destination"
                value={form.destination}
                onChange={(event) => updateField("destination", event.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="request-mode">Mode</Label>
              <Select
                value={form.mode}
                onValueChange={(value) =>
                  updateField("mode", value as CreateRequestPayload["mode"])
                }
              >
                <SelectTrigger id="request-mode">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ltl">LTL</SelectItem>
                  <SelectItem value="ftl">FTL</SelectItem>
                  <SelectItem value="air">Air</SelectItem>
                  <SelectItem value="ocean">Ocean</SelectItem>
                  <SelectItem value="rail">Rail</SelectItem>
                  <SelectItem value="intermodal">Intermodal</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="request-loading-time">Loading time</Label>
              <Input
                id="request-loading-time"
                value={form.loadingTime}
                onChange={(event) => updateField("loadingTime", event.target.value)}
              />
            </div>
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
                <div className="cargo-description grid gap-1.5">
                  <Label htmlFor={`cargo-${line.id}-description`}>Description</Label>
                  <Input
                    id={`cargo-${line.id}-description`}
                    value={line.description}
                    onChange={(event) =>
                      updateCargoLine(line.id, "description", event.target.value)
                    }
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor={`cargo-${line.id}-quantity`}>Qty</Label>
                  <Input
                    id={`cargo-${line.id}-quantity`}
                    inputMode="numeric"
                    value={line.quantity}
                    onChange={(event) => updateCargoLine(line.id, "quantity", event.target.value)}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor={`cargo-${line.id}-weight`}>Kg</Label>
                  <Input
                    id={`cargo-${line.id}-weight`}
                    inputMode="decimal"
                    value={line.weightKg}
                    onChange={(event) => updateCargoLine(line.id, "weightKg", event.target.value)}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor={`cargo-${line.id}-length`}>L cm</Label>
                  <Input
                    id={`cargo-${line.id}-length`}
                    inputMode="decimal"
                    value={line.lengthCm}
                    onChange={(event) => updateCargoLine(line.id, "lengthCm", event.target.value)}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor={`cargo-${line.id}-width`}>W cm</Label>
                  <Input
                    id={`cargo-${line.id}-width`}
                    inputMode="decimal"
                    value={line.widthCm}
                    onChange={(event) => updateCargoLine(line.id, "widthCm", event.target.value)}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor={`cargo-${line.id}-height`}>H cm</Label>
                  <Input
                    id={`cargo-${line.id}-height`}
                    inputMode="decimal"
                    value={line.heightCm}
                    onChange={(event) => updateCargoLine(line.id, "heightCm", event.target.value)}
                  />
                </div>
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
        <Alert variant="destructive">
          <AlertDescription>{createMutation.data.review_reason}</AlertDescription>
        </Alert>
      ) : null}
      {createMutation.data?.complete ? (
        <Alert>
          <AlertDescription>Request parsed and ready for quoting.</AlertDescription>
        </Alert>
      ) : null}
      {createMutation.error ? (
        <Alert variant="destructive">
          <AlertDescription>
            {createMutation.error.detail ?? createMutation.error.title}
          </AlertDescription>
        </Alert>
      ) : null}
      <DataTable
        columns={[
          { key: "public_id", label: "ID", mono: true },
          { key: "customer", label: "Customer" },
          { key: "lane", label: "Lane" },
          { key: "mode", label: "Mode" },
          {
            key: "status",
            label: "Status",
            render: (value) => <StatusChip status={String(value)} />,
          },
          {
            key: "weight_kg",
            label: "Weight kg",
            align: "right",
            mono: true,
            render: (value) => `${value}`,
          },
        ]}
        highlightId={searchParams.get("highlight") ?? undefined}
        loading={query.isLoading}
        rows={query.data}
        onRowClick={(row) => setSelectedRequestId(row.id)}
      />
      <Sheet
        open={selectedRequestId !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedRequestId(null);
        }}
      >
        <SheetContent className="w-full overflow-y-auto sm:max-w-[480px]">
          <SheetHeader>
            <SheetTitle className="font-mono">
              {detailQuery.data?.request.public_id ?? "Request"}
            </SheetTitle>
            <SheetDescription>
              {detailQuery.data?.request.customer} · {detailQuery.data?.request.lane}
            </SheetDescription>
          </SheetHeader>
          {detailQuery.isLoading ? (
            <div className="grid gap-2 py-4">
              <Skeleton className="h-5 w-full" />
              <Skeleton className="h-5 w-full" />
              <Skeleton className="h-5 w-full" />
            </div>
          ) : detailQuery.data ? (
            <div className="grid gap-4 py-4 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs uppercase text-muted-foreground">Mode</div>
                  <div>{detailQuery.data.request.mode}</div>
                </div>
                <div>
                  <div className="mb-1 text-xs uppercase text-muted-foreground">Status</div>
                  <StatusChip status={detailQuery.data.request.status} />
                </div>
                <div>
                  <div className="text-xs uppercase text-muted-foreground">Weight</div>
                  <div className="font-mono tabular-nums">
                    {detailQuery.data.request.weight_kg} kg
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase text-muted-foreground">Created</div>
                  <div className="font-mono">{detailQuery.data.created_at}</div>
                </div>
              </div>
              {detailQuery.data.review_reason ? (
                <Alert variant="destructive">
                  <AlertDescription>{detailQuery.data.review_reason}</AlertDescription>
                </Alert>
              ) : null}
              <div>
                <div className="mb-2 text-xs uppercase text-muted-foreground">
                  Cargo ({detailQuery.data.cargo_lines.length})
                </div>
                {detailQuery.data.cargo_lines.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No cargo lines recorded.</p>
                ) : (
                  <div className="grid gap-2">
                    {detailQuery.data.cargo_lines.map((line) => (
                      <div className="agent-row" key={line.id}>
                        <div>
                          <strong>{line.description}</strong>
                          <span>
                            {[
                              line.quantity ? `${line.quantity} pcs` : null,
                              line.weight_kg ? `${line.weight_kg} kg` : null,
                              line.length_cm && line.width_cm && line.height_cm
                                ? `${line.length_cm}x${line.width_cm}x${line.height_cm} cm`
                                : null,
                              line.hazardous ? `ADR ${line.un_number ?? ""}`.trim() : null,
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </ModuleScaffold>
  );
}

function parseOptionalNumber(value: string): number | undefined {
  const trimmed = value.trim();
  return trimmed ? Number(trimmed) : undefined;
}
