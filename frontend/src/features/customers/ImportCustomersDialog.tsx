import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, Upload } from "lucide-react";
import { useRef } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  apiUpload,
  type ApiProblem,
  type ContactImportIssue,
  type ContactImportResponse,
} from "@/shared/api/client";

// Semicolon-separated + BOM so Swedish Excel opens it with columns and
// å/ä/ö intact. The backend accepts the same headers (and English aliases).
const TEMPLATE_CSV =
  "﻿Kundnamn;E-post;Domän;Påslag;Incoterms;Betalningsvillkor;Segment;Kund sedan;SLA;" +
  "Ansvarig;Hälsa;Årlig volym;Tullkontakt;Tullkontakt e-post;Avtalsnotering\n" +
  "Exempel AB;logistik@exempel.se;;12,5;DAP;30 dagar netto;Fordon;2024-01-15;48;" +
  "Anna Andersson;good;1500000;Erik Tull;tull@exempel.se;Ramavtal 2024\n";

export function ImportCustomersDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const importMutation = useMutation<ContactImportResponse, ApiProblem, File>({
    mutationFn: (file) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiUpload<ContactImportResponse>("/contacts/import", formData);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
  });

  function close() {
    importMutation.reset();
    onOpenChange(false);
  }

  function downloadTemplate() {
    const url = URL.createObjectURL(new Blob([TEMPLATE_CSV], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "kundmall.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  const result = importMutation.data;

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Importera kunder</DialogTitle>
          <DialogDescription>
            Ladda upp en CSV-fil (t.ex. från Excel via "Spara som → CSV"). Första raden ska vara
            rubriker; endast Kundnamn krävs. Kunder som redan finns (samma namn eller e-post)
            hoppas över.
          </DialogDescription>
        </DialogHeader>

        <input
          accept=".csv,text/csv"
          className="hidden"
          ref={fileInputRef}
          type="file"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) importMutation.mutate(file);
            event.target.value = "";
          }}
        />

        <div className="flex flex-wrap gap-3">
          <Button disabled={importMutation.isPending} onClick={() => fileInputRef.current?.click()}>
            <Upload aria-hidden="true" />
            {importMutation.isPending ? "Importerar…" : "Välj CSV-fil"}
          </Button>
          <Button variant="outline" onClick={downloadTemplate}>
            <Download aria-hidden="true" />
            Ladda ner mall
          </Button>
        </div>

        {importMutation.error ? (
          <p className="text-sm text-destructive">
            {typeof importMutation.error.detail === "string"
              ? importMutation.error.detail
              : "Importen misslyckades. Kontrollera filen och försök igen."}
          </p>
        ) : null}

        {result ? (
          <div className="flex flex-col gap-3 rounded-md border border-border p-4 text-sm">
            <p className="font-medium">
              {result.created.length} {result.created.length === 1 ? "kund" : "kunder"} importerade
              {result.skipped.length ? ` · ${result.skipped.length} hoppades över` : ""}
              {result.errors.length ? ` · ${result.errors.length} med fel` : ""}
            </p>
            <IssueList issues={result.skipped} title="Hoppades över" />
            <IssueList issues={result.errors} title="Fel" tone="destructive" />
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={close}>
            {result ? "Stäng" : "Avbryt"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function IssueList({
  issues,
  title,
  tone,
}: {
  issues: ContactImportIssue[];
  title: string;
  tone?: "destructive";
}) {
  if (!issues.length) return null;
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-semibold uppercase text-muted-foreground">{title}</p>
      <ul className="mt-1 max-h-40 overflow-y-auto">
        {issues.map((issue) => (
          <li
            key={`${issue.row}-${issue.reason}`}
            className={`break-words ${tone === "destructive" ? "text-destructive" : "text-muted-foreground"}`}
          >
            Rad {issue.row}
            {issue.display_name ? ` (${issue.display_name})` : ""}: {issue.reason}
          </li>
        ))}
      </ul>
    </div>
  );
}
