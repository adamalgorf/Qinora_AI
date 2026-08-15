alter table public.email_inbound
  add column if not exists recipient text not null default '',
  add column if not exists message_id text,
  add column if not exists in_reply_to text,
  add column if not exists references_header text,
  add column if not exists request_id text,
  add column if not exists quote_id text;

create index if not exists email_inbound_message_id_idx
  on public.email_inbound (message_id)
  where message_id is not null;

create index if not exists email_inbound_sender_idx
  on public.email_inbound (lower(sender));
