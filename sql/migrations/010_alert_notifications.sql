-- Migration 010: Add alert notification configuration to tenant_bot_config

alter table public.tenant_bot_config
  add column if not exists notify_email_enabled boolean not null default false,
  add column if not exists notify_email_recipient text,
  add column if not exists notify_whatsapp_enabled boolean not null default false,
  add column if not exists notify_whatsapp_recipient text,
  add column if not exists notify_conversion_alerts boolean not null default true,
  add column if not exists notify_handoff_alerts boolean not null default true;

comment on column public.tenant_bot_config.notify_email_enabled is 'Whether to send email alerts on events';
comment on column public.tenant_bot_config.notify_email_recipient is 'Destination email address for tenant alerts';
comment on column public.tenant_bot_config.notify_whatsapp_enabled is 'Whether to send WhatsApp alerts to admin';
comment on column public.tenant_bot_config.notify_whatsapp_recipient is 'Destination phone number for WhatsApp alerts';
comment on column public.tenant_bot_config.notify_conversion_alerts is 'Trigger alert on hot lead or purchase intent';
comment on column public.tenant_bot_config.notify_handoff_alerts is 'Trigger alert on human handoff or help request';
