create table if not exists public.clarification_outbound (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  inbound_email_id uuid not null references public.email_inbound(id) on delete cascade,
  recipient text not null,
  subject text not null,
  body_text text not null,
  status text not null default 'queued',
  created_at timestamptz not null default now(),
  sent_at timestamptz,
  error_message text
);

alter table public.clarification_outbound enable row level security;
