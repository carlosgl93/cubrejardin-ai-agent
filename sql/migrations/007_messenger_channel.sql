-- 007_messenger_channel.sql
-- Adds 'messenger' to channel checks and creates tenant_messenger_credentials

alter table public.conversations drop constraint if exists conversations_channel_check;
alter table public.conversations
  add constraint conversations_channel_check
  check (channel in ('whatsapp', 'instagram', 'messenger'));

alter table public.handoffs drop constraint if exists handoffs_channel_check;
alter table public.handoffs
  add constraint handoffs_channel_check
  check (channel in ('whatsapp', 'instagram', 'messenger'));

create table if not exists public.tenant_messenger_credentials (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null unique references public.tenants(id) on delete cascade,
  page_id text not null,
  page_access_token text not null,
  app_secret text,
  webhook_verify_token text not null default encode(gen_random_bytes(32), 'hex'),
  status text not null default 'pending'
    check (status in ('pending', 'active', 'revoked')),
  token_expires_at timestamptz,
  raw_oauth_response jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.tenant_messenger_credentials enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where tablename = 'tenant_messenger_credentials'
      and policyname = 'Tenant admins see Messenger creds'
  ) then
    create policy "Tenant admins see Messenger creds"
      on public.tenant_messenger_credentials for select
      using (tenant_id in (
        select tenant_id from public.tenant_users
        where user_id = auth.uid() and role in ('owner', 'admin')
      ));
  end if;
end
$$;
