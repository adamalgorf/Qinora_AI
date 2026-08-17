alter table public.outbound_reply_queue
  add column if not exists in_reply_to_message_id text;

alter table public.clarification_outbound
  add column if not exists in_reply_to_message_id text;
