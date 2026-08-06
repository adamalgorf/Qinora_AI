import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
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
      badge="Email relay"
      description="Inbound messages ready for Nora Intake, invoice audit or operator review."
      title="Inbox"
    >
      <DataTable
        columns={[
          { key: "sender", label: "Sender" },
          { key: "subject", label: "Subject" },
          { key: "classification", label: "Classification" },
          { key: "received_at", label: "Received" },
        ]}
        loading={query.isLoading}
        rows={query.data}
        onRowClick={(row) => setSelectedMessageId(row.id)}
      />
      <Dialog
        open={selectedMessageId !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedMessageId(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{detailQuery.data?.message.subject ?? "Message"}</DialogTitle>
            <DialogDescription>
              {detailQuery.data?.message.sender} · {detailQuery.data?.message.received_at}
            </DialogDescription>
          </DialogHeader>
          {detailQuery.isLoading ? (
            <div className="grid gap-2">
              <Skeleton className="h-5 w-full" />
              <Skeleton className="h-5 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : detailQuery.data ? (
            <div className="grid gap-3 text-sm">
              <div>
                <div className="text-xs uppercase text-muted-foreground">Classification</div>
                <div>{detailQuery.data.message.classification}</div>
              </div>
              <div>
                <div className="mb-1 text-xs uppercase text-muted-foreground">Body</div>
                <p className="whitespace-pre-wrap rounded-md border border-border/40 bg-muted/40 p-3">
                  {detailQuery.data.body_text}
                </p>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </ModuleScaffold>
  );
}
