create extension if not exists pgcrypto;

create table if not exists public.tenants (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  locale text not null default 'en',
  created_at timestamptz not null default now()
);

create table if not exists public.users (
  id uuid primary key,
  tenant_id uuid not null references public.tenants(id),
  email text not null unique,
  full_name text,
  created_at timestamptz not null default now()
);

create table if not exists public.user_roles (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  user_id uuid not null references public.users(id) on delete cascade,
  role text not null check (role in ('shipper', 'carrier', '4pl_tower', 'admin', 'superadmin')),
  created_at timestamptz not null default now(),
  unique (user_id, role)
);

create table if not exists public.contacts (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  public_id text not null,
  name text not null,
  email text,
  domain text,
  default_markup_percent numeric(6, 2) not null default 0,
  created_at timestamptz not null default now(),
  is_active boolean not null default true
);

create table if not exists public.transport_requests (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  public_id text not null,
  contact_id uuid references public.contacts(id),
  mode text not null check (mode in ('ftl', 'ltl', 'ocean', 'air', 'rail', 'intermodal')),
  status text not null default 'new',
  origin text,
  destination text,
  loading_time timestamptz,
  unloading_time timestamptz,
  review_reason text,
  created_at timestamptz not null default now()
);

create table if not exists public.request_cargo (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  request_id uuid not null references public.transport_requests(id) on delete cascade,
  description text not null,
  quantity integer,
  weight_kg numeric(12, 3),
  length_cm numeric(12, 3),
  width_cm numeric(12, 3),
  height_cm numeric(12, 3),
  hazardous boolean not null default false,
  un_number text,
  created_at timestamptz not null default now()
);

create table if not exists public.quotes (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  public_id text not null,
  request_id uuid references public.transport_requests(id),
  parent_quote_id uuid references public.quotes(id),
  version integer not null default 1,
  status text not null default 'draft',
  customer_price numeric(12, 2) not null default 0,
  currency text not null default 'SEK',
  pricing_status text not null default 'pending',
  created_at timestamptz not null default now()
);

create table if not exists public.carriers (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  public_id text not null,
  name text not null,
  is_preferred boolean not null default false,
  created_at timestamptz not null default now(),
  is_active boolean not null default true
);

create table if not exists public.carrier_aliases (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  carrier_id uuid not null references public.carriers(id) on delete cascade,
  alias text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.shipments (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  public_id text not null,
  quote_id uuid references public.quotes(id),
  carrier_id uuid references public.carriers(id),
  carrier text,
  status text not null default 'draft',
  eta timestamptz,
  requires_manual_review boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists public.shipment_events (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  shipment_id uuid not null references public.shipments(id) on delete cascade,
  from_status text,
  to_status text not null,
  reason text,
  created_at timestamptz not null default now()
);

create table if not exists public.shipment_carrier_evaluations (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  shipment_id uuid references public.shipments(id) on delete cascade,
  carrier_id uuid references public.carriers(id),
  rank integer not null,
  score_total numeric(8, 2) not null,
  status text not null,
  confidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.agent_configs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  agent_key text not null,
  is_enabled boolean not null default true,
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (tenant_id, agent_key)
);

create table if not exists public.agent_logs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  agent_key text not null,
  step text not null,
  entity_id text,
  decision jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.operational_tasks (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  entity_type text not null,
  entity_id text not null,
  priority text not null default 'normal',
  reason text not null,
  status text not null default 'open',
  created_at timestamptz not null default now()
);

create table if not exists public.email_inbound (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references public.tenants(id),
  sender text not null,
  subject text not null,
  body_text text not null,
  classification text,
  parsed_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.outbound_reply_queue (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  quote_id uuid references public.quotes(id),
  recipient text not null,
  subject text not null,
  body_text text not null,
  status text not null default 'queued',
  created_at timestamptz not null default now()
);

create table if not exists public.invoices (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  public_id text not null,
  shipment_id uuid references public.shipments(id),
  quote_id uuid references public.quotes(id),
  invoice_amount numeric(12, 2) not null,
  currency text not null default 'SEK',
  status text not null default 'created',
  discrepancy_amount numeric(12, 2),
  created_at timestamptz not null default now()
);

create table if not exists public.webhook_events (
  id uuid primary key default gen_random_uuid(),
  idempotency_key text not null unique,
  event_type text not null,
  created_at timestamptz not null default now()
);

create index if not exists transport_requests_tenant_status_idx
  on public.transport_requests (tenant_id, status);
create index if not exists transport_requests_tenant_created_idx
  on public.transport_requests (tenant_id, created_at desc);
create index if not exists quotes_tenant_status_idx on public.quotes (tenant_id, status);
create index if not exists shipments_tenant_status_idx on public.shipments (tenant_id, status);
create index if not exists shipments_tenant_created_idx
  on public.shipments (tenant_id, created_at desc);
create index if not exists agent_logs_tenant_created_idx
  on public.agent_logs (tenant_id, created_at desc);
create index if not exists email_inbound_created_idx on public.email_inbound (created_at desc);

create or replace function public.validate_shipment_status_transition()
returns trigger
language plpgsql
as $$
begin
  if old.status = new.status then
    return new;
  end if;

  if old.status = 'draft' and new.status in ('quote_sent', 'booked', 'needs_review', 'cancelled') then
    return new;
  elsif old.status = 'quote_sent' and new.status in ('booked', 'needs_review', 'cancelled') then
    return new;
  elsif old.status = 'booked' and new.status in ('in_transit', 'needs_review', 'cancelled') then
    return new;
  elsif old.status = 'in_transit' and new.status in ('delivered', 'needs_review', 'cancelled') then
    return new;
  elsif old.status = 'delivered' and new.status in ('invoice_approved', 'invoice_disputed', 'needs_review') then
    return new;
  elsif old.status = 'needs_review' and new.status in ('draft', 'booked', 'in_transit', 'manual_review', 'cancelled') then
    return new;
  elsif old.status = 'manual_review' and new.status in ('draft', 'booked', 'needs_review', 'cancelled') then
    return new;
  elsif old.status = 'invoice_disputed' and new.status in ('invoice_approved', 'needs_review') then
    return new;
  end if;

  raise exception 'invalid shipment status transition from % to %', old.status, new.status;
end;
$$;

drop trigger if exists shipments_status_transition on public.shipments;
create trigger shipments_status_transition
before update of status on public.shipments
for each row execute function public.validate_shipment_status_transition();

alter table public.tenants enable row level security;
alter table public.users enable row level security;
alter table public.user_roles enable row level security;
alter table public.contacts enable row level security;
alter table public.transport_requests enable row level security;
alter table public.request_cargo enable row level security;
alter table public.quotes enable row level security;
alter table public.carriers enable row level security;
alter table public.carrier_aliases enable row level security;
alter table public.shipments enable row level security;
alter table public.shipment_events enable row level security;
alter table public.shipment_carrier_evaluations enable row level security;
alter table public.agent_configs enable row level security;
alter table public.agent_logs enable row level security;
alter table public.operational_tasks enable row level security;
alter table public.email_inbound enable row level security;
alter table public.outbound_reply_queue enable row level security;
alter table public.invoices enable row level security;
alter table public.webhook_events enable row level security;
