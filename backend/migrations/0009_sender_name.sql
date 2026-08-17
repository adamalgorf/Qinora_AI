alter table public.email_inbound
  add column if not exists sender_name text;
