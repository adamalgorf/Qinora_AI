alter table public.carriers
  add column if not exists email text;

create table if not exists public.carrier_rfqs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  request_id uuid not null references public.transport_requests(id) on delete cascade,
  carrier_id uuid not null references public.carriers(id),
  correlation_token text not null unique,
  status text not null default 'sent'
    check (status in ('sent', 'responded', 'expired', 'superseded')),
  sent_at timestamptz not null default now(),
  responded_at timestamptz,
  expires_at timestamptz not null
);

create index if not exists carrier_rfqs_tenant_request_idx
  on public.carrier_rfqs (tenant_id, request_id);

alter table public.carrier_rfqs enable row level security;

create table if not exists public.carrier_rfq_outbound (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  carrier_rfq_id uuid not null references public.carrier_rfqs(id) on delete cascade,
  recipient text not null,
  subject text not null,
  body_text text not null,
  status text not null default 'queued',
  created_at timestamptz not null default now(),
  sent_at timestamptz,
  error_message text
);

alter table public.carrier_rfq_outbound enable row level security;

alter table public.carrier_offers
  add column if not exists carrier_rfq_id uuid references public.carrier_rfqs(id);
