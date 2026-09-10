alter table public.contacts
  add column if not exists segment text,
  add column if not exists customer_since date,
  add column if not exists sla_tolerance_hours numeric(6, 2),
  add column if not exists account_owner text,
  add column if not exists health_status text not null default 'good'
    check (health_status in ('good', 'watch', 'at_risk')),
  add column if not exists contract_note text,
  add column if not exists customs_contact_name text,
  add column if not exists customs_contact_email text,
  add column if not exists annual_volume_estimate numeric(14, 2);
