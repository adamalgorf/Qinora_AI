-- Knowledge base the agents read before acting (application/knowledge.py).
-- Reference material - customer profiles, routes, carrier notes, terms,
-- procedures - kept apart from public.documents, which is case paperwork
-- (CMR, POD, invoices) attached to requests and shipments.
create table if not exists public.knowledge_documents (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  public_id text not null,
  title text not null,
  domain text not null
    check (domain in ('customers', 'routes', 'carriers', 'terms', 'procedures', 'general')),
  source_filename text,
  body_text text not null,
  uploaded_by text,
  created_at timestamptz not null default now()
);

create index if not exists knowledge_documents_tenant_domain_idx
  on public.knowledge_documents (tenant_id, domain);

-- embedding is a 256-dim float4 array scored in Python (see
-- infrastructure/llm/embeddings.py) - null when embeddings were unavailable
-- at upload, in which case retrieval ranks that chunk by keywords.
create table if not exists public.knowledge_chunks (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  document_id uuid not null references public.knowledge_documents(id) on delete cascade,
  ordinal integer not null,
  body_text text not null,
  embedding real[],
  unique (document_id, ordinal)
);

create index if not exists knowledge_chunks_document_idx
  on public.knowledge_chunks (document_id);

alter table public.knowledge_documents enable row level security;
alter table public.knowledge_chunks enable row level security;
