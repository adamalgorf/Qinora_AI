alter table public.users add column if not exists password_hash text;
alter table public.users add column if not exists is_active boolean not null default true;
