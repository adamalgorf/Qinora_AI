alter table public.outbound_reply_queue
  add column if not exists sender_mailbox text;

alter table public.carrier_rfq_outbound
  add column if not exists sender_mailbox text;

alter table public.clarification_outbound
  add column if not exists sender_mailbox text;
