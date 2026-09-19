import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Plus, Search, Trash2 } from "lucide-react";
import { useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { DataTable } from "@/features/modules/DataTable";
import {
  apiDelete,
  apiGet,
  apiPost,
  apiUpload,
  type ApiProblem,
  type KnowledgeDocumentDetail,
  type KnowledgeDocumentItem,
  type KnowledgeOverview,
  type KnowledgePreviewResponse,
} from "@/shared/api/client";

const ACCEPTED_FILES = ".txt,.md,.csv,.pdf";

const dateFormatter = new Intl.DateTimeFormat("sv-SE", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

export function KnowledgeBaseTab() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [domainFilter, setDomainFilter] = useState<string | null>(null);
  const [addDomain, setAddDomain] = useState<string | null>(null);
  const [openDocumentId, setOpenDocumentId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<KnowledgeDocumentItem | null>(null);

  const overview = useQuery({
    queryKey: ["knowledge", "overview"],
    queryFn: () => apiGet<KnowledgeOverview>("/knowledge/overview"),
  });
  const documents = useQuery({
    queryKey: ["knowledge", "documents"],
    queryFn: () => apiGet<KnowledgeDocumentItem[]>("/knowledge"),
  });

  const deleteMutation = useMutation<void, ApiProblem, string>({
    mutationFn: (id) => apiDelete(`/knowledge/${id}`),
    onSuccess: async () => {
      setPendingDelete(null);
      await queryClient.invalidateQueries({ queryKey: ["knowledge"] });
    },
  });

  const needle = search.trim().toLowerCase();
  const rows = (documents.data ?? []).filter(
    (doc) =>
      (!domainFilter || doc.domain === domainFilter) &&
      (!needle ||
        doc.title.toLowerCase().includes(needle) ||
        doc.domain_label.toLowerCase().includes(needle)),
  );

  return (
    <div className="flex flex-col gap-6">
      <p className="max-w-3xl text-sm text-muted-foreground">
        Kunskapsbanken är det agenterna läser innan de agerar. Lägg in kundprofiler, rutter,
        transportörer, villkor och rutiner i rätt område. Varje agent läser bara sina egna områden
        (och Allmänt), så rätt information hamnar hos rätt agent. Priser hör hemma i prisprofilerna,
        inte här.
      </p>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {(overview.data?.domains ?? []).map((domain) => {
          const active = domainFilter === domain.key;
          return (
            <Card
              key={domain.key}
              className={cn(
                "cursor-pointer rounded-lg transition-colors hover:border-primary/40",
                active && "border-primary",
              )}
              onClick={() => setDomainFilter(active ? null : domain.key)}
            >
              <CardContent className="flex h-full flex-col gap-3 p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-foreground">{domain.label}</p>
                    <p className="text-sm text-muted-foreground">
                      {domain.document_count} dokument
                    </p>
                  </div>
                  <Button
                    aria-label={`Lägg till i ${domain.label}`}
                    size="sm"
                    variant="outline"
                    onClick={(event) => {
                      event.stopPropagation();
                      setAddDomain(domain.key);
                    }}
                  >
                    <Plus aria-hidden="true" />
                    Lägg till
                  </Button>
                </div>
                <p className="text-sm text-muted-foreground">{domain.description}</p>
                <div className="mt-auto flex flex-wrap items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">Läses av</span>
                  {domain.agents.map((agent) => (
                    <Badge key={agent} variant="secondary">
                      {agent}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardContent className="flex flex-col gap-4 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Input
                className="max-w-sm"
                placeholder="Sök på titel eller område…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              {domainFilter ? (
                <Button size="sm" variant="ghost" onClick={() => setDomainFilter(null)}>
                  Visa alla områden
                </Button>
              ) : null}
            </div>
            <Button onClick={() => setAddDomain(domainFilter ?? "customers")}>
              <Plus aria-hidden="true" />
              Lägg till kunskap
            </Button>
          </div>
          {!documents.isLoading && (documents.data ?? []).length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <BookOpen aria-hidden="true" className="size-8 text-muted-foreground" />
              <p className="font-medium">Kunskapsbanken är tom</p>
              <p className="max-w-md text-sm text-muted-foreground">
                Börja med det agenterna oftast behöver: era största kunder och deras krav, och de
                rutter ni kör mest.
              </p>
            </div>
          ) : (
            <DataTable
              columns={[
                { key: "public_id", label: "ID", mono: true },
                { key: "title", label: "Titel" },
                { key: "domain_label", label: "Område" },
                {
                  key: "read_by",
                  label: "Läses av",
                  render: (value) => (value as string[]).join(" · "),
                },
                {
                  key: "char_count",
                  label: "Omfång",
                  align: "right",
                  render: (value, row) =>
                    `${Number(value).toLocaleString("sv-SE")} tecken · ${row.chunk_count} ${
                      row.chunk_count === 1 ? "del" : "delar"
                    }`,
                },
                {
                  key: "embedded",
                  label: "Sökning",
                  render: (value) => (value ? "Semantisk" : "Nyckelord"),
                },
                {
                  key: "created_at",
                  label: "Tillagd",
                  render: (value) => formatDate(String(value)),
                },
                {
                  key: "id",
                  id: "actions",
                  label: "",
                  align: "right",
                  render: (_, row) => (
                    <Button
                      aria-label={`Ta bort ${row.title}`}
                      size="icon"
                      variant="ghost"
                      onClick={(event) => {
                        event.stopPropagation();
                        setPendingDelete(row);
                      }}
                    >
                      <Trash2 aria-hidden="true" />
                    </Button>
                  ),
                },
              ]}
              loading={documents.isLoading}
              rows={rows}
              onRowClick={(row) => setOpenDocumentId(row.id)}
            />
          )}
        </CardContent>
      </Card>

      <AgentPreviewCard overview={overview.data} />

      <AddKnowledgeDialog
        domain={addDomain}
        overview={overview.data}
        onClose={() => setAddDomain(null)}
      />
      <KnowledgeDocumentDialog documentId={openDocumentId} onClose={() => setOpenDocumentId(null)} />

      <Dialog open={pendingDelete !== null} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Ta bort dokument?</DialogTitle>
            <DialogDescription>
              {pendingDelete ? (
                <>
                  &quot;{pendingDelete.title}&quot; tas bort ur kunskapsbanken.{" "}
                  {pendingDelete.read_by.join(", ")} slutar läsa det direkt.
                </>
              ) : null}
            </DialogDescription>
          </DialogHeader>
          {deleteMutation.error ? (
            <p className="text-sm text-destructive">
              {deleteMutation.error.detail ?? deleteMutation.error.title}
            </p>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingDelete(null)}>
              Avbryt
            </Button>
            <Button
              disabled={deleteMutation.isPending}
              variant="destructive"
              onClick={() => pendingDelete && deleteMutation.mutate(pendingDelete.id)}
            >
              {deleteMutation.isPending ? "Tar bort…" : "Ta bort"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AddKnowledgeDialog({
  domain,
  overview,
  onClose,
}: {
  domain: string | null;
  overview: KnowledgeOverview | undefined;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedDomain, setSelectedDomain] = useState("customers");
  const [title, setTitle] = useState("");
  const [source, setSource] = useState<"text" | "file">("text");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [openedFor, setOpenedFor] = useState<string | null>(null);

  // Reset the form each time the dialog opens, preselecting the domain the
  // user clicked "Lägg till" on.
  if (domain !== openedFor) {
    setOpenedFor(domain);
    if (domain) {
      setSelectedDomain(domain);
      setTitle("");
      setText("");
      setFile(null);
      setSource("text");
    }
  }

  const mutation = useMutation<KnowledgeDocumentItem, ApiProblem, void>({
    mutationFn: () => {
      const form = new FormData();
      form.append("domain", selectedDomain);
      if (title.trim()) form.append("title", title.trim());
      if (source === "file" && file) form.append("file", file);
      else form.append("text", text);
      return apiUpload<KnowledgeDocumentItem>("/knowledge", form);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["knowledge"] });
      mutation.reset();
      onClose();
    },
  });

  const domainInfo = overview?.domains.find((d) => d.key === selectedDomain);
  const canSubmit =
    source === "file" ? file !== null : title.trim().length > 0 && text.trim().length > 0;

  return (
    <Dialog
      open={domain !== null}
      onOpenChange={(open) => {
        if (!open) {
          mutation.reset();
          onClose();
        }
      }}
    >
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Lägg till kunskap</DialogTitle>
          <DialogDescription>
            Skriv som du skulle förklara för en ny kollega: vem, vad som gäller och när. Agenterna
            följer alltid kundens mejl om det säger något annat.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label>Område</Label>
              <Select value={selectedDomain} onValueChange={setSelectedDomain}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(overview?.domains ?? []).map((d) => (
                    <SelectItem key={d.key} value={d.key}>
                      {d.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {domainInfo ? (
                <p className="text-xs text-muted-foreground">
                  Läses av {domainInfo.agents.join(", ")}
                </p>
              ) : null}
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="knowledge-title">Titel</Label>
              <Input
                id="knowledge-title"
                placeholder={source === "file" ? "Filnamnet används om tomt" : "t.ex. Kund Volvo Cars"}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </div>
          </div>

          <Tabs value={source} onValueChange={(v) => setSource(v as typeof source)}>
            <TabsList>
              <TabsTrigger value="text">Skriv eller klistra in</TabsTrigger>
              <TabsTrigger value="file">Ladda upp fil</TabsTrigger>
            </TabsList>
          </Tabs>

          {source === "text" ? (
            <Textarea
              className="min-h-48"
              placeholder={
                "Volvo Cars (Torslanda)\n- Lastar alltid vid port 4, vardagar 06–14.\n- Kräver bakgavellyft och avisering dagen innan.\n- Kontakt: transport@volvocars.com"
              }
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          ) : (
            <div className="flex flex-col gap-2">
              <input
                accept={ACCEPTED_FILES}
                className="hidden"
                ref={fileInputRef}
                type="file"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <Button
                className="w-fit"
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
              >
                {file ? file.name : "Välj fil…"}
              </Button>
              <p className="text-xs text-muted-foreground">
                .txt, .md, .csv eller .pdf, högst 5 MB. Skannade PDF:er utan text kan inte läsas.
                Klistra då in texten istället.
              </p>
            </div>
          )}

          {mutation.error ? (
            <p className="break-words text-sm text-destructive">
              {mutation.error.detail ?? mutation.error.title}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Avbryt
          </Button>
          <Button disabled={!canSubmit || mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? "Sparar…" : "Spara"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function KnowledgeDocumentDialog({
  documentId,
  onClose,
}: {
  documentId: string | null;
  onClose: () => void;
}) {
  const detail = useQuery({
    queryKey: ["knowledge", "document", documentId],
    queryFn: () => apiGet<KnowledgeDocumentDetail>(`/knowledge/${documentId}`),
    enabled: documentId !== null,
  });
  const document = detail.data?.document;

  return (
    <Dialog open={documentId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{document?.title ?? "Laddar…"}</DialogTitle>
          <DialogDescription>
            {document
              ? `${document.public_id} · ${document.domain_label} · läses av ${document.read_by.join(", ")}`
              : null}
          </DialogDescription>
        </DialogHeader>
        <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-4 font-sans text-sm">
          {detail.data?.text ?? ""}
        </pre>
      </DialogContent>
    </Dialog>
  );
}

function AgentPreviewCard({ overview }: { overview: KnowledgeOverview | undefined }) {
  const [agentKey, setAgentKey] = useState("");
  const [text, setText] = useState("");
  const agents = overview?.agents ?? [];
  const selectedAgent = agentKey || agents[0]?.key || "";

  const preview = useMutation<KnowledgePreviewResponse, ApiProblem, void>({
    mutationFn: () =>
      apiPost<KnowledgePreviewResponse, { agent_key: string; text: string }>(
        "/knowledge/preview",
        { agent_key: selectedAgent, text },
      ),
  });

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-5">
        <div>
          <p className="font-semibold text-foreground">Testa vad agenten läser</p>
          <p className="text-sm text-muted-foreground">
            Klistra in ett mejl och se exakt vilka utdrag agenten får med sig innan den agerar,
            med samma sökning som i skarpt läge.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-[14rem_minmax(0,1fr)]">
          <div className="flex flex-col gap-2">
            <Label>Agent</Label>
            <Select value={selectedAgent} onValueChange={setAgentKey}>
              <SelectTrigger>
                <SelectValue placeholder="Välj agent" />
              </SelectTrigger>
              <SelectContent>
                {agents.map((agent) => (
                  <SelectItem key={agent.key} value={agent.key}>
                    {agent.name} · {agent.role}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="knowledge-preview-text">Exempelmejl</Label>
            <Textarea
              id="knowledge-preview-text"
              placeholder="Hej! Vi behöver en bil från Torslanda till Hamburg på tisdag, 12 pallar…"
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </div>
        </div>
        <Button
          className="w-fit"
          disabled={!selectedAgent || !text.trim() || preview.isPending}
          variant="outline"
          onClick={() => preview.mutate()}
        >
          <Search aria-hidden="true" />
          {preview.isPending ? "Söker…" : "Visa vad agenten läser"}
        </Button>

        {preview.error ? (
          <p className="text-sm text-destructive">{preview.error.detail ?? preview.error.title}</p>
        ) : null}
        {preview.data ? (
          preview.data.snippets.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {preview.data.agent.name} hittar inget i sina områden för det här mejlet.
            </p>
          ) : (
            <ol className="flex flex-col gap-3">
              {preview.data.snippets.map((snippet, index) => (
                <li key={`${snippet.document_id}-${index}`} className="rounded-md border p-3">
                  <p className="text-sm font-medium">
                    {snippet.title}{" "}
                    <span className="font-normal text-muted-foreground">
                      · {snippet.domain_label}
                    </span>
                  </p>
                  <p className="mt-1 line-clamp-4 whitespace-pre-wrap text-sm text-muted-foreground">
                    {snippet.text}
                  </p>
                </li>
              ))}
            </ol>
          )
        ) : null}
      </CardContent>
    </Card>
  );
}

function formatDate(value: string): string {
  const date = new Date(value.includes("T") || value.includes("+") ? value : `${value.replace(" ", "T")}Z`);
  return Number.isNaN(date.getTime()) ? value : dateFormatter.format(date);
}
