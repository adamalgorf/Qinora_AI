import { useState } from "react";

import { PageShell } from "@/components/patterns/PageShell";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CaseDocumentsTab } from "@/features/documents/CaseDocumentsTab";
import { KnowledgeBaseTab } from "@/features/documents/KnowledgeBaseTab";

export function DocumentsPage() {
  const [tab, setTab] = useState<"knowledge" | "case">("knowledge");

  return (
    <PageShell subtitle="Kunskapsbank för agenterna" title="Dokument">
      <Tabs value={tab} onValueChange={(value) => setTab(value as typeof tab)}>
        <TabsList>
          <TabsTrigger value="knowledge">Kunskapsbank</TabsTrigger>
          <TabsTrigger value="case">Ärendedokument</TabsTrigger>
        </TabsList>
      </Tabs>
      {tab === "knowledge" ? <KnowledgeBaseTab /> : <CaseDocumentsTab />}
    </PageShell>
  );
}
