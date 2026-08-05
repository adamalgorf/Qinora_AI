create table if not exists public.carrier_offers (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  request_id uuid not null references public.transport_requests(id) on delete cascade,
  carrier_name text not null,
  price numeric(12, 2),
  currency text,
  transit_days integer,
  notes text,
  confidence numeric(5, 4) not null default 0,
  created_at timestamptz not null default now()
);

alter table public.carrier_offers enable row level security;

-- Agent config rows are re-seeded from DEFAULT_AGENT_CONFIGS on every startup
-- (see PostgresDatabase.initialize); drop any keys that are no longer in the
-- current set so trimming the agent list also cleans up existing databases.
delete from public.agent_configs
where agent_key not in ('request_parsing_agent', 'carrier_offer_agent', 'quote_response_agent');
