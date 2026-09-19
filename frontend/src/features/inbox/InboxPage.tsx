import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrainCircuit } from "lucide-react";
import { useEffect, useState } from "react";

import { AiInsightBanner } from "@/components/patterns/AiInsightBanner";
import { PageShell } from "@/components/patterns/PageShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusChip } from "@/components/ui/status-chip";
import {
  apiGet,
  apiPost,
  type ApiProblem,
  type InboxDetailResponse,
  type InboxListItem,
  type ParseFreeTextRequestPayload,
  type ParseFreeTextRequestResponse,
} from "@/shared/api/client";
import { cn } from "@/lib/utils";

type InboxTab = "alla" | "kritiska" | "ai" | "utkast";

const TABS: Array<{ value: InboxTab; label: string }> = [
  { value: "alla", label: "Alla" },
  { value: "kritiska", label: "Kritiska" },
  { value: "ai", label: "AI-Hanterade" },
  { value: "utkast", label: "Utkast" },
];

// Best-effort tab split over the free-form `classification` field: no dedicated
// "critical"/"draft" flag exists on email_inbound today.
// Generic navigational hint per classification — not a claim about what the
// AI has actually determined, just points the operator at the next step.
function suggestedAction(classification: string): string {
  const c = classification.toLowerCase();
  if (c === "invoice") return "Granska faktura";
  if (c === "customer_details") return "Kolla den nya kunden";
  if (c === "error") return "Automatisk hantering misslyckades - granska manuellt";
  if (c === "pending" || c === "unknown") return "Bearbeta";
  return "Öppna ärende";
}

function matchesTab(item: InboxListItem, tab: InboxTab): boolean {
  if (tab === "alla") return true;
  const classification = item.classification.toLowerCase();
  if (tab === "kritiska") {
    // "error" = automated processing crashed on this one (see
    // email_intake_orchestrator.py's top-level safety net) - always
    // urgent, not just a normal AI-behandlas-nu item.
    return ["urgent", "critical", "complaint", "tull", "customs", "error"].some((needle) =>
      classification.includes(needle),
    );
  }
  if (tab === "utkast") {
    return classification === "pending" || classification === "unknown";
  }
  return classification !== "pending" && classification !== "unknown";
}

export function InboxPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<InboxTab>("alla");
  const query = useQuery({
    queryKey: ["inbox"],
    queryFn: () => apiGet<InboxListItem[]>("/inbox/pending"),
  });
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const detailQuery = useQuery({
    queryKey: ["inbox-detail", selectedMessageId],
    queryFn: () => apiGet<InboxDetailResponse>(`/inbox/${selectedMessageId}`),
    enabled: Boolean(selectedMessageId),
  });

  const filtered = (query.data ?? []).filter((item) => matchesTab(item, tab));

  useEffect(() => {
    if (!selectedMessageId && filtered.length > 0) {
      setSelectedMessageId(filtered[0].id);
    }
  }, [filtered, selectedMessageId]);

  const approveMutation = useMutation<
    ParseFreeTextRequestResponse,
    ApiProblem,
    ParseFreeTextRequestPayload
  >({
    mutationFn: (payload) =>
      apiPost<ParseFreeTextRequestResponse, ParseFreeTextRequestPayload>(
        "/requests/parse",
        payload,
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["cases"] });
    },
  });

  const selected = detailQuery.data;

  return (
    <PageShell subtitle="Triagering och Kundförfrågningar" title="Inkorg">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <div className="flex flex-col gap-4 rounded-lg border border-border/40 bg-card p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Alla meddelanden</h2>
            {filtered.length > 0 ? (
              <Badge className="bg-destructive/10 text-destructive" variant="outline">
                {filtered.length} olästa
              </Badge>
            ) : null}
          </div>
          <div className="flex gap-1 rounded-lg bg-muted p-1 text-sm">
            {TABS.map((t) => (
              <button
                className={cn(
                  "flex-1 rounded-md px-2 py-1 font-medium transition-colors",
                  tab === t.value
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground",
                )}
                key={t.value}
                onClick={() => setTab(t.value)}
                type="button"
              >
                {t.label}
              </button>
            ))}
          </div>
          {query.isLoading ? (
            <div className="grid gap-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground">Inga meddelanden i denna vy.</p>
          ) : (
            <div className="flex flex-col gap-1">
              {filtered.map((item) => (
                <button
                  className={cn(
                    "flex flex-col gap-1 rounded-md border border-transparent px-3 py-3 text-left transition-colors",
                    item.id === selectedMessageId
                      ? "border-accent/30 bg-accent/10"
                      : "hover:bg-muted/60",
                  )}
                  key={item.id}
                  onClick={() => setSelectedMessageId(item.id)}
                  type="button"
                >
                  <div className="flex w-full items-center justify-between gap-2">
                    <span className="min-w-0 truncate font-semibold">{item.sender}</span>
                    <span className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">
                      {item.received_at}
                    </span>
                  </div>
                  <span className="w-full truncate text-sm">{item.subject}</span>
                  <div className="mt-1 flex w-full items-center justify-between gap-2">
                    <StatusChip className="shrink-0" status={item.classification} />
                    <span className="shrink-0 whitespace-nowrap text-xs font-medium text-accent">
                      {suggestedAction(item.classification)}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-lg border border-border/40 bg-card p-5">
          {detailQuery.isLoading ? (
            <div className="grid gap-3">
              <Skeleton className="h-5 w-1/2" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : selected ? (
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between gap-3">
                <StatusChip className="shrink-0" status={selected.message.classification} />
                <span className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">
                  {selected.message.received_at}
                </span>
              </div>
              <div className="min-w-0">
                <h2 className="break-words text-lg font-semibold">{selected.message.subject}</h2>
                <p className="break-words text-sm text-muted-foreground">
                  Från: {selected.message.sender}
                </p>
              </div>
              <div className="min-w-0 break-words border-t border-border/40 pt-4 text-sm leading-relaxed whitespace-pre-wrap text-foreground/90">
                {selected.body_text}
              </div>
              <AiInsightBanner
                action={
                  <>
                    <Button
                      disabled={approveMutation.isPending}
                      size="sm"
                      onClick={() =>
                        approveMutation.mutate({
                          customer: selected.message.sender,
                          raw_text: selected.body_text,
                        })
                      }
                    >
                      {approveMutation.isPending ? "Bearbetar…" : "Godkänn förslag"}
                    </Button>
                    <Button size="sm" variant="outline">
                      Redigera detaljer
                    </Button>
                  </>
                }
                body="AI-analys: meddelandet har lästs och kan omvandlas till ett ärende med ett klick, eller redigeras manuellt innan det skapas."
                heading="Qinora AI Smarta Åtgärder"
                icon={BrainCircuit}
              />
              {approveMutation.data ? (
                <p className="text-sm text-success">
                  {approveMutation.data.request
                    ? `Ärende ${approveMutation.data.request.public_id} skapat.`
                    : "Utkast skapat, väntar på manuell granskning."}
                </p>
              ) : null}
              {approveMutation.error ? (
                <p className="text-sm text-destructive">
                  {approveMutation.error.detail ?? approveMutation.error.title}
                </p>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Välj ett meddelande i listan.</p>
          )}
        </div>
      </div>
    </PageShell>
  );
}
