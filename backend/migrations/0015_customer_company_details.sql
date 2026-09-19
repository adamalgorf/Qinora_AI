-- Company details collected when a not-yet-known sender confirms an order
-- (application/customer_onboarding.py): org number, address and the named
-- contact person. email/domain stay the sender identity used for inbound
-- matching; contact_* is the person to reach about the account.
alter table public.contacts
  add column if not exists org_number text,
  add column if not exists contact_person text,
  add column if not exists contact_email text,
  add column if not exists contact_phone text,
  add column if not exists address text;
