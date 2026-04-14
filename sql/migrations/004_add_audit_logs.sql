create table if not exists public.audit_logs (
  id bigserial primary key,
  tenant_id uuid,
  event_type text not null,
  entity_type text not null,
  entity_id text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists audit_logs_tenant_created_idx
  on public.audit_logs (tenant_id, created_at desc);

create index if not exists audit_logs_event_type_idx
  on public.audit_logs (event_type);
