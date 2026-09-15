import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cpu } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useParams } from "react-router-dom";

import { AiInsightBanner } from "@/components/patterns/AiInsightBanner";
import { PageShell } from "@/components/patterns/PageShell";
import { TimelineFeed, type TimelineFeedItem } from "@/components/patterns/TimelineFeed";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  apiGet,
  apiPost,
  type AcceptQuotePayload,
  type AcceptQuoteResponse,
  type ApiProblem,
  type CaseDetailResponse,
  type CreateInternalNotePayload,
  type InternalNoteItem,
  type QuoteReplyPayload,
  type QuoteReplyResponse,
  type SendQuoteResponse,
} from "@/shared/api/client";

export function CaseDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [replyMode, setReplyMode] = useState<"external" | "internal">("external");
  const [message, setMessage] = useState("");

  const query = useQuery({
    queryKey: ["case-detail", id],
    queryFn: () => apiGet<CaseDetailResponse>(`/cases/${id}`),
    enabled: Boolean(id),
  });

  const data = query.data;
  const latestQuote = data?.quotes.at(-1) ?? null;

  const sendMutation = useMutation<SendQuoteResponse, ApiProblem, string>({
    mutationFn: (quoteId) =>
      apiPost<SendQuoteResponse, Record<string, never>>(`/quotes/${quoteId}/send`, {}),
    onSuccess: () => refreshCase(),
  });
  const replyMutation = useMutation<
    QuoteReplyResponse,
    ApiProblem,
    { quoteId: string; payload: QuoteReplyPayload }
  >({
    mutationFn: ({ quoteId, payload }) =>
      apiPost<QuoteReplyResponse, QuoteReplyPayload>(`/quotes/${quoteId}/reply`, payload),
    onSuccess: () => {
      setMessage("");
      refreshCase();
    },
  });
  const acceptMutation = useMutation<AcceptQuoteResponse, ApiProblem, void>({
    mutationFn: () => {
      if (!latestQuote) throw new Error("no quote");
      const payload: AcceptQuotePayload = {
        mode: data?.request_detail.request.mode ?? "ltl",
        total_weight_kg: data?.request_detail.request.weight_kg ?? 1,
      };
      return apiPost<AcceptQuoteResponse, AcceptQuotePayload>(
        `/quotes/${latestQuote.id}/accept`,
        payload,
      );
    },
    onSuccess: () => refreshCase(),
  });
  const noteMutation = useMutation<InternalNoteItem, ApiProblem, CreateInternalNotePayload>({
    mutationFn: (payload) =>
      apiPost<InternalNoteItem, CreateInternalNotePayload>(`/cases/${id}/notes`, payload),
    onSuccess: () => {
      setMessage("");
      refreshCase();
    },
  });

  function refreshCase() {
    void queryClient.invalidateQueries({ queryKey: ["case-detail", id] });
    void queryClient.invalidateQueries({ queryKey: ["cases"] });
  }

  function submitMessage() {
    if (!message.trim()) return;
    if (replyMode === "internal") {
      noteMutation.mutate({ author: "Marcus Lindqvist", body_text: message });
      return;
    }
    if (latestQuote) {
      replyMutation.mutate({ quoteId: latestQuote.id, payload: { body_text: message } });
    }
  }

  if (query.isLoading || !data) {
    return (
      <PageShell subtitle={`Ärende #${id}`} title="Ärendedetalj">
        <Skeleton className="h-40 w-full" />
      </PageShell>
    );
  }

  const activity: TimelineFeedItem[] = data.activity.map((item, i) => ({
    id: `${item.type}-${i}`,
    timestamp: item.timestamp,
    tag: item.tag,
    description: item.description,
  }));

  return (
    <PageShell subtitle={`Ärende #${data.case.public_id}`} title="Ärendedetalj">
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[280px_minmax(0,1fr)_280px]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardContent className="flex flex-col gap-3 p-5">
              <h2 className="text-sm font-semibold">AI-extraherade ruttfakta</h2>
              <Field label="Sändare" value={data.case.customer} />
              <Field label="Rutt" value={data.case.lane} />
              <Field label="Godstyp" value={data.request_detail.request.mode} />
              <Field
                label="Vikt"
                value={`${data.request_detail.request.weight_kg ?? "—"} kg`}
              />
            </CardContent>
          </Card>
          <Card>
            <CardContent className="flex flex-col gap-3 p-5">
              <h2 className="text-sm font-semibold">Dokument ({data.documents.length})</h2>
              {data.documents.length === 0 ? (
                <p className="text-sm text-muted-foreground">Inga dokument kopplade.</p>
              ) : (
                data.documents.map((doc) => (
                  <div className="rounded-md bg-muted/50 px-3 py-2 text-sm" key={doc.id}>
                    <p className="font-medium">{doc.filename}</p>
                    <p className="text-xs text-muted-foreground">
                      {(doc.size_bytes / 1024).toFixed(0)} KB
                    </p>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>

        <div className="flex flex-col gap-6">
          <AiInsightBanner
            body="AI-rekommendation baserad på tillgänglig data för detta ärende."
            heading="AI-Rekommendation"
            icon={Cpu}
          />
          <Card>
            <CardContent className="flex flex-col gap-4 p-5">
              <h2 className="text-sm font-semibold">Ärendehistorik och loggar</h2>
              <TimelineFeed items={activity} />
              <div className="border-t border-border/40 pt-4">
                <Tabs value={replyMode} onValueChange={(v) => setReplyMode(v as typeof replyMode)}>
                  <TabsList>
                    <TabsTrigger value="external">Externt svar</TabsTrigger>
                    <TabsTrigger value="internal">Intern anteckning</TabsTrigger>
                  </TabsList>
                </Tabs>
                <Textarea
                  className="mt-3"
                  placeholder={
                    replyMode === "external"
                      ? "Svara kunden eller lägg till interna anteckningar…"
                      : "Intern anteckning, synlig endast för teamet…"
                  }
                  rows={3}
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                />
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    disabled={
                      !message.trim() || replyMutation.isPending || noteMutation.isPending
                    }
                    onClick={submitMessage}
                  >
                    Skicka svar
                  </Button>
                  {replyMode === "external" && latestQuote?.status === "draft" ? (
                    <Button
                      disabled={sendMutation.isPending}
                      variant="secondary"
                      onClick={() => sendMutation.mutate(latestQuote.id)}
                    >
                      Skicka offert
                    </Button>
                  ) : null}
                  {replyMode === "external" && latestQuote?.status === "sent" ? (
                    <Button
                      disabled={acceptMutation.isPending}
                      variant="secondary"
                      onClick={() => acceptMutation.mutate()}
                    >
                      Direktacceptera
                    </Button>
                  ) : null}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <Card className="h-fit">
          <CardContent className="flex flex-col gap-3 p-5">
            <h2 className="break-words text-sm font-semibold">
              {data.contact?.display_name ?? data.case.customer}
            </h2>
            <Field
              label="SLA-tolerans"
              value={
                data.contact?.sla_tolerance_hours
                  ? `${data.contact.sla_tolerance_hours}h`
                  : "—"
              }
            />
            <Field
              label="Hälsa"
              value={<Badge variant="outline">{data.contact?.health_status ?? "—"}</Badge>}
            />
            <Field label="Avtalstyp" value={data.contact?.default_incoterms ?? "—"} />
          </CardContent>
        </Card>
      </div>
    </PageShell>
  );
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-semibold uppercase text-muted-foreground">{label}</p>
      <p className="break-words text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}
