-- 006_instagram_channel.sql
-- Adds channel discriminator to conversations + handoffs,
-- and the tenant_instagram_credentials table.

alter table public.conversations
  add column if not exists channel text not null default 'whatsapp'
  check (channel in ('whatsapp', 'instagram'));

alter table public.handoffs
  add column if not exists channel text not null default 'whatsapp'
  check (channel in ('whatsapp', 'instagram'));

-- Rename user_number -> channel_user_id for semantic clarity.
-- This is a structural cleanup that does not change row data.
-- Guarded so re-runs are no-ops (RENAME itself is not idempotent).
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'conversations' and column_name = 'user_number'
  ) then
    alter table public.conversations rename column user_number to channel_user_id;
  end if;
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'handoffs' and column_name = 'user_number'
  ) then
    alter table public.handoffs rename column user_number to channel_user_id;
  end if;
end
$$;

create table if not exists public.tenant_instagram_credentials (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null unique references public.tenants(id) on delete cascade,
  ig_user_id text not null,
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

alter table public.tenant_instagram_credentials enable row level security;

create policy "Tenant admins see IG creds"
  on public.tenant_instagram_credentials for select
  using (tenant_id in (
    select tenant_id from public.tenant_users
    where user_id = auth.uid() and role in ('owner', 'admin')
  ));

create index if not exists idx_conversations_tenant_channel_recent
  on public.conversations (tenant_id, channel, created_at desc);

-- Code touch-ups landed alongside this migration (Task A.1 follow-ups):
--   * agents/handoff_agent.py — _notify_telegram now queries
--       .eq("channel_user_id", user_number).eq("channel", "whatsapp").
--   * api/handoffs.py — reply endpoint inserts conversation row with
--       "channel": "whatsapp" + "channel_user_id": <whatsapp_number>.
--   * api/webhooks.py — forward-to-agent path inserts conversation row
--       with the same two renamed/added keys.
--
-- All three call sites are WA-only paths, so explicit channel='whatsapp'
-- is set to avoid cross-channel bleed once IG handoffs land (Tasks B+).