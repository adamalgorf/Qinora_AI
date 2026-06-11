alter table public.transport_requests
  add column if not exists customer text,
  add column if not exists lane text,
  add column if not exists weight_kg numeric(12, 3) not null default 0;

alter table public.email_inbound
  add column if not exists idempotency_key text;

create unique index if not exists email_inbound_idempotency_key_idx
  on public.email_inbound (idempotency_key)
  where idempotency_key is not null;

alter table public.quotes
  add column if not exists request_id_text text;

alter table public.shipments
  add column if not exists lane text,
  add column if not exists eta_label text;

alter table public.carriers
  add column if not exists aliases text[] not null default '{}',
  add column if not exists modes text[] not null default '{}',
  add column if not exists lane_score numeric(8, 2) not null default 0,
  add column if not exists max_weight_kg numeric(12, 3),
  add column if not exists performance_score numeric(8, 2),
  add column if not exists sample_size integer not null default 0;

alter table public.agent_logs
  add column if not exists agent_name text,
  add column if not exists confidence numeric(5, 4) not null default 0;

alter table public.invoices
  add column if not exists quote_amount numeric(12, 2) not null default 0;

alter table public.outbound_reply_queue
  add column if not exists sent_at timestamptz,
  add column if not exists error_message text;

create table if not exists public.quote_response_events (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  quote_id uuid references public.quotes(id),
  intent text not null,
  body_text text not null,
  created_at timestamptz not null default now()
);

alter table public.quote_response_events enable row level security;
