import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
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
  apiGet,
  apiPost,
  type CarrierCreatePayload,
  type CarrierListItem,
} from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

const MODE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "ftl", label: "FTL" },
  { value: "ltl", label: "LTL" },
  { value: "ocean", label: "Sjöfrakt" },
  { value: "air", label: "Flygfrakt" },
  { value: "rail", label: "Järnväg" },
  { value: "intermodal", label: "Intermodal" },
];

const EMPTY_NEW_CARRIER = {
  displayName: "",
  email: "",
  modes: [] as string[],
  maxWeightKg: "",
  laneScore: "",
  preferred: false,
};

export function CarriersPage() {
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [newCarrier, setNewCarrier] = useState(EMPTY_NEW_CARRIER);

  const query = useQuery({
    queryKey: ["carriers"],
    queryFn: () => apiGet<CarrierListItem[]>("/carriers"),
  });

  const createCarrierMutation = useMutation({
    mutationFn: (payload: CarrierCreatePayload) =>
      apiPost<CarrierListItem, CarrierCreatePayload>("/carriers", payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["carriers"] });
      setAddOpen(false);
      setNewCarrier(EMPTY_NEW_CARRIER);
    },
  });

  function toggleMode(mode: string) {
    setNewCarrier((current) => ({
      ...current,
      modes: current.modes.includes(mode)
        ? current.modes.filter((m) => m !== mode)
        : [...current.modes, mode],
    }));
  }

  function submitNewCarrier() {
    const payload: CarrierCreatePayload = {
      display_name: newCarrier.displayName.trim(),
      modes: newCarrier.modes,
      email: newCarrier.email.trim() || undefined,
      max_weight_kg: newCarrier.maxWeightKg ? Number(newCarrier.maxWeightKg) : undefined,
      lane_score: newCarrier.laneScore ? Number(newCarrier.laneScore) : undefined,
      preferred: newCarrier.preferred,
    };
    createCarrierMutation.mutate(payload);
  }

  return (
    <ModuleScaffold
      badge="Carrier Intelligence"
      description="Transportörskatalog för denna klient som driver behörighet, poängsättning och tillförlitlighetsrankning."
      title="Transportörer"
    >
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setAddOpen(true)}>Lägg till transportör</Button>
      </div>
      <DataTable
        columns={[
          { key: "display_name", label: "Transportör" },
          { key: "modes", label: "Transportsätt", render: (value) => (value as string[]).join(", ") },
          { key: "lane_score", label: "Sträckpoäng", align: "right", mono: true },
          { key: "performance_score", label: "Prestanda", align: "right", mono: true },
          { key: "preferred", label: "Föredragen", render: (value) => (value ? "Ja" : "Nej") },
        ]}
        highlightId={searchParams.get("highlight") ?? undefined}
        loading={query.isLoading}
        rows={query.data}
      />

      <Dialog
        open={addOpen}
        onOpenChange={(open) => {
          setAddOpen(open);
          if (!open) setNewCarrier(EMPTY_NEW_CARRIER);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Lägg till transportör</DialogTitle>
            <DialogDescription>
              Skapa en ny transportör i katalogen. E-postadressen används för att skicka
              automatiska offertförfrågningar (RFQ) när inget avtalat pris finns.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="new-carrier-name">Namn</Label>
              <Input
                id="new-carrier-name"
                value={newCarrier.displayName}
                onChange={(e) =>
                  setNewCarrier((current) => ({ ...current, displayName: e.target.value }))
                }
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="new-carrier-email">E-postadress</Label>
              <Input
                id="new-carrier-email"
                type="email"
                value={newCarrier.email}
                onChange={(e) =>
                  setNewCarrier((current) => ({ ...current, email: e.target.value }))
                }
              />
            </div>
            <div className="grid gap-1.5">
              <Label>Transportsätt</Label>
              <div className="flex flex-wrap gap-3">
                {MODE_OPTIONS.map((option) => (
                  <label
                    key={option.value}
                    className="flex items-center gap-2 text-sm text-muted-foreground"
                  >
                    <input
                      checked={newCarrier.modes.includes(option.value)}
                      className="size-4 rounded border-border accent-primary"
                      onChange={() => toggleMode(option.value)}
                      type="checkbox"
                    />
                    {option.label}
                  </label>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-1.5">
                <Label htmlFor="new-carrier-max-weight">Maxvikt (kg)</Label>
                <Input
                  id="new-carrier-max-weight"
                  type="number"
                  placeholder="Ingen gräns"
                  value={newCarrier.maxWeightKg}
                  onChange={(e) =>
                    setNewCarrier((current) => ({ ...current, maxWeightKg: e.target.value }))
                  }
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="new-carrier-lane-score">Sträckpoäng</Label>
                <Input
                  id="new-carrier-lane-score"
                  type="number"
                  placeholder="50"
                  value={newCarrier.laneScore}
                  onChange={(e) =>
                    setNewCarrier((current) => ({ ...current, laneScore: e.target.value }))
                  }
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input
                checked={newCarrier.preferred}
                className="size-4 rounded border-border accent-primary"
                onChange={(e) =>
                  setNewCarrier((current) => ({ ...current, preferred: e.target.checked }))
                }
                type="checkbox"
              />
              Föredragen transportör
            </label>
            {createCarrierMutation.isError ? (
              <p className="text-[11px] text-destructive">
                Kunde inte skapa transportören. Kontrollera fälten och försök igen.
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>
              Avbryt
            </Button>
            <Button
              disabled={
                !newCarrier.displayName.trim() ||
                newCarrier.modes.length === 0 ||
                createCarrierMutation.isPending
              }
              onClick={submitNewCarrier}
            >
              {createCarrierMutation.isPending ? "Skapar…" : "Skapa transportör"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </ModuleScaffold>
  );
}
