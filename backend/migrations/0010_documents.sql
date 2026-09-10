create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  public_id text not null,
  filename text not null,
  content_type text not null,
  size_bytes integer not null,
  content bytea not null,
  document_type text,
  status text not null default 'pending_review'
    check (status in ('pending_review', 'validated', 'manual_review', 'flagged')),
  ai_confidence numeric(5, 4),
  extracted_fields jsonb not null default '{}'::jsonb,
  request_id uuid references public.transport_requests(id),
  shipment_id uuid references public.shipments(id),
  contact_id uuid references public.contacts(id),
  uploaded_by text,
  created_at timestamptz not null default now()
);

create index if not exists documents_tenant_created_idx on public.documents (tenant_id, created_at desc);
create index if not exists documents_request_idx on public.documents (request_id);

alter table public.documents enable row level security;
