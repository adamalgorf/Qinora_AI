create table if not exists public.rate_profiles (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  mode text not null check (mode in ('ftl', 'ltl', 'ocean', 'air', 'rail', 'intermodal')),
  origin text,
  destination text,
  base_price numeric(12, 2) not null default 0,
  price_per_kg numeric(12, 4) not null default 0,
  currency text not null default 'SEK',
  created_at timestamptz not null default now()
);

create index if not exists rate_profiles_tenant_mode_idx
  on public.rate_profiles (tenant_id, mode, origin, destination);

alter table public.rate_profiles enable row level security;
