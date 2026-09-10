alter table public.transport_requests
  add column if not exists assignee text,
  add column if not exists sla_due_at timestamptz,
  add column if not exists priority text not null default 'normal'
    check (priority in ('low', 'normal', 'high', 'critical'));

create table if not exists public.case_notes (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  request_id uuid not null references public.transport_requests(id) on delete cascade,
  author text not null,
  body_text text not null,
  created_at timestamptz not null default now()
);

create index if not exists case_notes_request_idx on public.case_notes (request_id, created_at);

alter table public.case_notes enable row level security;
