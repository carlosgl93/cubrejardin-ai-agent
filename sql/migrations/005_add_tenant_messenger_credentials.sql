create extension if not exists pgcrypto;

create table if not exists public.tenant_messenger_credentials (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants(id) on delete cascade,
  page_id text not null,
  page_access_token text not null,
  status text not null default 'active',
  raw_oauth_response jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists tenant_messenger_credentials_tenant_id_uidx
  on public.tenant_messenger_credentials (tenant_id);

create unique index if not exists tenant_messenger_credentials_page_id_uidx
  on public.tenant_messenger_credentials (page_id);

create index if not exists tenant_messenger_credentials_active_lookup_idx
  on public.tenant_messenger_credentials (page_id, status);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'tenant_messenger_credentials_status_check'
      and conrelid = 'public.tenant_messenger_credentials'::regclass
  ) then
    alter table public.tenant_messenger_credentials
      add constraint tenant_messenger_credentials_status_check
      check (status in ('pending', 'active', 'inactive', 'error'));
  end if;
end;
$$;

alter table public.tenant_messenger_credentials enable row level security;

drop policy if exists tenant_messenger_credentials_no_authenticated_access on public.tenant_messenger_credentials;

create policy tenant_messenger_credentials_no_authenticated_access
on public.tenant_messenger_credentials
for all
to authenticated
using (false)
with check (false);

drop trigger if exists set_tenant_messenger_credentials_updated_at on public.tenant_messenger_credentials;
create trigger set_tenant_messenger_credentials_updated_at
before update on public.tenant_messenger_credentials
for each row
execute function public.set_updated_at();
