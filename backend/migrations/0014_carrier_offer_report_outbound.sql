create table if not exists public.carrier_offer_report_outbound (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id),
  request_id uuid not null references public.transport_requests(id) on delete cascade,
  recipient text not null,
  subject text not null,
  body_text text not null,
  status text not null default 'queued',
  created_at timestamptz not null default now(),
  sent_at timestamptz,
  error_message text,
  sender_mailbox text
);

alter table public.carrier_offer_report_outbound enable row level security;
