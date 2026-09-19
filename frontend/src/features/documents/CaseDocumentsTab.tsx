import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { useRef, useState } from "react";

import { KpiCard, KpiGrid } from "@/components/patterns/KpiCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfidenceBar } from "@/components/ui/confidence-bar";
import { Input } from "@/components/ui/input";
import { StatusChip } from "@/components/ui/status-chip";
import { DataTable } from "@/features/modules/DataTable";
import { apiGet, apiUpload, type ApiProblem, type DocumentListItem } from "@/shared/api/client";

export function CaseDocumentsTab() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const query = useQuery({
    queryKey: ["documents"],
    queryFn: () => apiGet<DocumentListItem[]>("/documents"),
  });

  const uploadMutation = useMutation<DocumentListItem, ApiProblem, File>({
    mutationFn: (file) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiUpload<DocumentListItem>("/documents", formData);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const rows = (query.data ?? []).filter((doc) =>
    search.trim() ? doc.filename.toLowerCase().includes(search.trim().toLowerCase()) : true,
  );
  const withConfidence = rows.filter((d) => d.ai_confidence !== null);
  const avgConfidence = withConfidence.length
    ? Math.round(
        (withConfidence.reduce((sum, d) => sum + (d.ai_confidence ?? 0), 0) /
          withConfidence.length) *
          1000,
      ) / 10
    : 0;
  const needsReview = rows.filter((d) => d.status === "manual_review" || d.status === "flagged").length;
  const autoMatched = rows.filter((d) => d.request_id || d.shipment_id || d.contact_id).length;
  const matchRate = rows.length ? Math.round((autoMatched / rows.length) * 1000) / 10 : 0;

  return (
    <div className="flex flex-col gap-6">
      <KpiGrid>
        <KpiCard label="Analyserade dokument" value={rows.length} />
        <KpiCard label="Extraktionsprecision" value={`${avgConfidence}%`} />
        <KpiCard label="Automatisk matchning" value={`${matchRate}%`} />
        <KpiCard label="Manuella tillsyner" trend={{ label: "Kräver granskning", tone: "neutral" }} value={needsReview} />
      </KpiGrid>

      <Card>
        <CardContent className="flex flex-col gap-4 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Input
              className="max-w-sm"
              placeholder="Sök efter dokumentnamn, typ eller kund…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <input
              accept=".pdf,.png,.jpg,.jpeg"
              className="hidden"
              ref={fileInputRef}
              type="file"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) uploadMutation.mutate(file);
                event.target.value = "";
              }}
            />
            <Button disabled={uploadMutation.isPending} onClick={() => fileInputRef.current?.click()}>
              <Upload aria-hidden="true" />
              {uploadMutation.isPending ? "Laddar upp…" : "Ladda upp dokument"}
            </Button>
          </div>
          {uploadMutation.error ? (
            <p className="text-sm text-destructive">
              {uploadMutation.error.detail ?? uploadMutation.error.title}
            </p>
          ) : null}
          <DataTable
            columns={[
              { key: "public_id", label: "Dokument-ID", mono: true },
              { key: "filename", label: "Dokumentnamn" },
              { key: "document_type", label: "Typ" },
              {
                key: "ai_confidence",
                label: "AI-konfidens",
                render: (value) => (value === null ? "—" : <ConfidenceBar value={Number(value)} />),
              },
              {
                key: "size_bytes",
                label: "Storlek",
                align: "right",
                render: (value) => `${(Number(value) / 1024).toFixed(0)} KB`,
              },
              {
                key: "status",
                label: "Status",
                render: (value) => <StatusChip status={String(value)} />,
              },
            ]}
            loading={query.isLoading}
            rows={rows}
          />
        </CardContent>
      </Card>
    </div>
  );
}
