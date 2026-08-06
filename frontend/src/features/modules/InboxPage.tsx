import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusChip } from "@/components/ui/status-chip";
import { apiGet, type InboxDetailResponse, type InboxListItem } from "@/shared/api/client";

import { DataTable } from "./DataTable";
import { ModuleScaffold } from "./ModuleScaffold";

export function InboxPage() {
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

  return (
    <ModuleScaffold
      badge="E-postrelä"
      description="Inkommande meddelanden redo för Nora Intake, fakturagranskning eller operatörsöversyn."
      title="Inkorg"
    >
      <DataTable
        columns={[
          { key: "sender", label: "Avsändare" },
          { key: "subject", label: "Ämne" },
          {
            key: "classification",
            label: "Klassificering",
            render: (value) => <StatusChip status={String(value)} />,
          },
          { key: "received_at", label: "Mottaget", mono: true },
        ]}
        loading={query.isLoading}
        rows={query.data}
        onRowClick={(row) => setSelectedMessageId(row.id)}
      />
      <Sheet
        open={selectedMessageId !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedMessageId(null);
        }}
      >
        <SheetContent className="w-full overflow-y-auto sm:max-w-[480px]">
          <SheetHeader>
            <SheetTitle>{detailQuery.data?.message.subject ?? "Meddelande"}</SheetTitle>
            <SheetDescription>
              {detailQuery.data?.message.sender} · {detailQuery.data?.message.received_at}
            </SheetDescription>
          </SheetHeader>
          {detailQuery.isLoading ? (
            <div className="grid gap-2 py-4">
              <Skeleton className="h-5 w-full" />
              <Skeleton className="h-5 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : detailQuery.data ? (
            <div className="grid gap-3 py-4 text-sm">
              <div>
                <div className="mb-1 text-xs uppercase text-muted-foreground">Klassificering</div>
                <StatusChip status={detailQuery.data.message.classification} />
              </div>
              <div>
                <div className="mb-1 text-xs uppercase text-muted-foreground">Meddelandetext</div>
                <p className="whitespace-pre-wrap rounded-md border border-border/40 bg-muted/40 p-3">
                  {detailQuery.data.body_text}
                </p>
              </div>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </ModuleScaffold>
  );
}
