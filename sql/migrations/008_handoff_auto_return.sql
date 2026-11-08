-- Migration 008: Add handoff auto-return configuration to tenant_bot_config

alter table public.tenant_bot_config
  add column if not exists handoff_auto_return_enabled boolean not null default true,
  add column if not exists handoff_timeout_minutes integer not null default 10;

comment on column public.tenant_bot_config.handoff_auto_return_enabled is 'Whether active handoffs automatically expire back to bot mode after inactivity';
comment on column public.tenant_bot_config.handoff_timeout_minutes is 'Inactivity duration in minutes before automatically returning to bot mode';
