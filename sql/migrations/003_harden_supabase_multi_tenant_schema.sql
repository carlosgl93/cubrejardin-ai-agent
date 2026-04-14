create extension if not exists pgcrypto;
create extension if not exists vector;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create or replace function public.current_user_belongs_to_tenant(p_tenant_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.tenant_users tu
    where tu.tenant_id = p_tenant_id
      and tu.user_id = auth.uid()
  );
$$;

revoke all on function public.current_user_belongs_to_tenant(uuid) from public;
grant execute on function public.current_user_belongs_to_tenant(uuid) to authenticated, service_role;

-- ============================================================================
-- tenants
-- ============================================================================

update public.tenants
set settings = '{}'::jsonb
where settings is null;

update public.tenants
set created_at = now()
where created_at is null;

update public.tenants
set updated_at = now()
where updated_at is null;

alter table public.tenants
  alter column settings set default '{}'::jsonb,
  alter column settings set not null,
  alter column created_at set default now(),
  alter column created_at set not null,
  alter column updated_at set default now(),
  alter column updated_at set not null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'tenants_plan_check'
      and conrelid = 'public.tenants'::regclass
  ) then
    alter table public.tenants
      add constraint tenants_plan_check
      check (plan in ('free', 'pro', 'enterprise'));
  end if;
end;
$$;

drop trigger if exists set_tenants_updated_at on public.tenants;
create trigger set_tenants_updated_at
before update on public.tenants
for each row
execute function public.set_updated_at();

-- ============================================================================
-- tenant_users
-- ============================================================================

update public.tenant_users
set created_at = now()
where created_at is null;

alter table public.tenant_users
  alter column created_at set default now(),
  alter column created_at set not null;

create index if not exists tenant_users_tenant_id_idx
  on public.tenant_users (tenant_id);

create index if not exists tenant_users_user_id_idx
  on public.tenant_users (user_id);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'tenant_users_role_check'
      and conrelid = 'public.tenant_users'::regclass
  ) then
    alter table public.tenant_users
      add constraint tenant_users_role_check
      check (role in ('owner', 'admin', 'member'));
  end if;
end;
$$;

-- ============================================================================
-- tenant_whatsapp_credentials
-- Backend/service-role should be the only reader of access_token.
-- ============================================================================

update public.tenant_whatsapp_credentials
set raw_oauth_response = '{}'::jsonb
where raw_oauth_response is null;

update public.tenant_whatsapp_credentials
set created_at = now()
where created_at is null;

update public.tenant_whatsapp_credentials
set updated_at = now()
where updated_at is null;

alter table public.tenant_whatsapp_credentials
  alter column raw_oauth_response set default '{}'::jsonb,
  alter column raw_oauth_response set not null,
  alter column created_at set default now(),
  alter column created_at set not null,
  alter column updated_at set default now(),
  alter column updated_at set not null;

create unique index if not exists tenant_whatsapp_credentials_phone_number_id_uidx
  on public.tenant_whatsapp_credentials (phone_number_id);

create index if not exists tenant_whatsapp_credentials_active_lookup_idx
  on public.tenant_whatsapp_credentials (phone_number_id, status);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'tenant_whatsapp_credentials_status_check'
      and conrelid = 'public.tenant_whatsapp_credentials'::regclass
  ) then
    alter table public.tenant_whatsapp_credentials
      add constraint tenant_whatsapp_credentials_status_check
      check (status in ('pending', 'active', 'inactive', 'error'));
  end if;
end;
$$;

drop trigger if exists set_tenant_whatsapp_credentials_updated_at on public.tenant_whatsapp_credentials;
create trigger set_tenant_whatsapp_credentials_updated_at
before update on public.tenant_whatsapp_credentials
for each row
execute function public.set_updated_at();

-- ============================================================================
-- documents / RAG
-- ============================================================================

alter table public.documents
  alter column embedding type vector(1536)
  using embedding::vector(1536);

update public.documents
set metadata = '{}'::jsonb
where metadata is null;

update public.documents
set created_at = now()
where created_at is null;

update public.documents
set updated_at = now()
where updated_at is null;

alter table public.documents
  alter column metadata set default '{}'::jsonb,
  alter column metadata set not null,
  alter column embedding set not null,
  alter column created_at set default now(),
  alter column created_at set not null,
  alter column updated_at set default now(),
  alter column updated_at set not null;

create index if not exists documents_created_at_idx
  on public.documents (created_at desc);

create index if not exists documents_source_title_idx
  on public.documents ((metadata->>'source_title'));

drop trigger if exists set_documents_updated_at on public.documents;
create trigger set_documents_updated_at
before update on public.documents
for each row
execute function public.set_updated_at();

drop function if exists public.match_documents(vector, integer, uuid);
drop function if exists public.match_documents(vector, integer, uuid, double precision);

create or replace function public.match_documents(
  query_embedding vector(1536),
  match_count int,
  p_tenant_id uuid,
  min_similarity double precision default 0
)
returns table (
  id uuid,
  title text,
  content text,
  metadata jsonb,
  similarity double precision
)
language sql
stable
as $$
  select
    d.id,
    d.title,
    d.content,
    d.metadata,
    1 - (d.embedding <=> query_embedding) as similarity
  from public.documents d
  where d.tenant_id = p_tenant_id
    and 1 - (d.embedding <=> query_embedding) >= min_similarity
  order by d.embedding <=> query_embedding
  limit match_count;
$$;

-- ============================================================================
-- conversations
-- ============================================================================

alter table public.conversations
  add column if not exists message_id text;

update public.conversations
set metadata = '{}'::jsonb
where metadata is null;

update public.conversations
set created_at = now()
where created_at is null;

update public.conversations
set updated_at = now()
where updated_at is null;

alter table public.conversations
  alter column metadata set default '{}'::jsonb,
  alter column metadata set not null,
  alter column created_at set default now(),
  alter column created_at set not null,
  alter column updated_at set default now(),
  alter column updated_at set not null;

create index if not exists conversations_tenant_user_created_idx
  on public.conversations (tenant_id, user_number, created_at desc);

create index if not exists conversations_tenant_role_created_idx
  on public.conversations (tenant_id, role, created_at desc);

create unique index if not exists conversations_tenant_message_id_uidx
  on public.conversations (tenant_id, message_id)
  where message_id is not null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'conversations_role_check'
      and conrelid = 'public.conversations'::regclass
  ) then
    alter table public.conversations
      add constraint conversations_role_check
      check (role in ('user', 'assistant', 'system'));
  end if;
end;
$$;

drop trigger if exists set_conversations_updated_at on public.conversations;
create trigger set_conversations_updated_at
before update on public.conversations
for each row
execute function public.set_updated_at();

-- ============================================================================
-- escalations
-- ============================================================================

alter table public.escalations
  add column if not exists updated_at timestamptz default now();

update public.escalations
set metadata = '{}'::jsonb
where metadata is null;

update public.escalations
set created_at = now()
where created_at is null;

update public.escalations
set updated_at = now()
where updated_at is null;

alter table public.escalations
  alter column metadata set default '{}'::jsonb,
  alter column metadata set not null,
  alter column created_at set default now(),
  alter column created_at set not null,
  alter column updated_at set default now(),
  alter column updated_at set not null;

create index if not exists escalations_tenant_status_created_idx
  on public.escalations (tenant_id, status, created_at desc);

create index if not exists escalations_conversation_id_idx
  on public.escalations (conversation_id);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'escalations_status_check'
      and conrelid = 'public.escalations'::regclass
  ) then
    alter table public.escalations
      add constraint escalations_status_check
      check (status in ('pending', 'in_progress', 'resolved', 'cancelled'));
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'escalations_handoff_type_check'
      and conrelid = 'public.escalations'::regclass
  ) then
    alter table public.escalations
      add constraint escalations_handoff_type_check
      check (handoff_type in ('to_human', 'to_bot'));
  end if;
end;
$$;

drop trigger if exists set_escalations_updated_at on public.escalations;
create trigger set_escalations_updated_at
before update on public.escalations
for each row
execute function public.set_updated_at();

-- ============================================================================
-- learning_queue
-- ============================================================================

alter table public.learning_queue
  add column if not exists conversation_id bigint,
  add column if not exists source text,
  add column if not exists validated_at timestamptz,
  add column if not exists validated_by uuid,
  add column if not exists ingested_at timestamptz,
  add column if not exists updated_at timestamptz default now();

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'learning_queue_conversation_id_fkey'
      and conrelid = 'public.learning_queue'::regclass
  ) then
    alter table public.learning_queue
      add constraint learning_queue_conversation_id_fkey
      foreign key (conversation_id) references public.conversations(id) on delete set null;
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'learning_queue_validated_by_fkey'
      and conrelid = 'public.learning_queue'::regclass
  ) then
    alter table public.learning_queue
      add constraint learning_queue_validated_by_fkey
      foreign key (validated_by) references auth.users(id) on delete set null;
  end if;
end;
$$;

update public.learning_queue
set metadata = '{}'::jsonb
where metadata is null;

update public.learning_queue
set created_at = now()
where created_at is null;

update public.learning_queue
set updated_at = now()
where updated_at is null;

update public.learning_queue
set validated = false
where validated is null;

alter table public.learning_queue
  alter column metadata set default '{}'::jsonb,
  alter column metadata set not null,
  alter column validated set default false,
  alter column validated set not null,
  alter column created_at set default now(),
  alter column created_at set not null,
  alter column updated_at set default now(),
  alter column updated_at set not null;

create index if not exists learning_queue_tenant_validated_created_idx
  on public.learning_queue (tenant_id, validated, created_at desc);

create index if not exists learning_queue_conversation_id_idx
  on public.learning_queue (conversation_id);

create index if not exists learning_queue_ingested_at_idx
  on public.learning_queue (ingested_at);

drop trigger if exists set_learning_queue_updated_at on public.learning_queue;
create trigger set_learning_queue_updated_at
before update on public.learning_queue
for each row
execute function public.set_updated_at();

-- ============================================================================
-- RLS
-- Existing policies are dropped and replaced to avoid stacking permissive
-- policies with overlapping conditions.
-- ============================================================================

alter table public.tenants enable row level security;
alter table public.tenant_users enable row level security;
alter table public.documents enable row level security;
alter table public.conversations enable row level security;
alter table public.escalations enable row level security;
alter table public.learning_queue enable row level security;
alter table public.tenant_whatsapp_credentials enable row level security;

drop policy if exists "Users see own tenants" on public.tenants;
drop policy if exists tenants_select_member_tenant on public.tenants;

drop policy if exists "Users see own memberships" on public.tenant_users;
drop policy if exists "tenant_users_insert_self_membership" on public.tenant_users;
drop policy if exists tenant_users_select_own_membership on public.tenant_users;

drop policy if exists "Tenant members read documents" on public.documents;
drop policy if exists "Tenant members insert documents" on public.documents;
drop policy if exists "Tenant members update documents" on public.documents;
drop policy if exists "Tenant members delete documents" on public.documents;
drop policy if exists documents_member_select on public.documents;
drop policy if exists documents_member_insert on public.documents;
drop policy if exists documents_member_update on public.documents;
drop policy if exists documents_member_delete on public.documents;
drop policy if exists documents_member_access on public.documents;

drop policy if exists "Tenant members see conversations" on public.conversations;
drop policy if exists conversations_member_access on public.conversations;

drop policy if exists "Tenant members see escalations" on public.escalations;
drop policy if exists escalations_member_access on public.escalations;

drop policy if exists "Tenant members see learning queue" on public.learning_queue;
drop policy if exists learning_queue_member_access on public.learning_queue;

drop policy if exists "Tenant admins see credentials" on public.tenant_whatsapp_credentials;
drop policy if exists "Tenant admins insert credentials" on public.tenant_whatsapp_credentials;
drop policy if exists "Tenant admins update credentials" on public.tenant_whatsapp_credentials;

create policy tenants_select_member_tenant
on public.tenants
for select
to authenticated
using (public.current_user_belongs_to_tenant(id));

create policy tenant_users_select_own_membership
on public.tenant_users
for select
to authenticated
using (user_id = auth.uid());

create policy documents_member_select
on public.documents
for select
to authenticated
using (public.current_user_belongs_to_tenant(tenant_id));

create policy documents_member_insert
on public.documents
for insert
to authenticated
with check (public.current_user_belongs_to_tenant(tenant_id));

create policy documents_member_update
on public.documents
for update
to authenticated
using (public.current_user_belongs_to_tenant(tenant_id))
with check (public.current_user_belongs_to_tenant(tenant_id));

create policy documents_member_delete
on public.documents
for delete
to authenticated
using (public.current_user_belongs_to_tenant(tenant_id));

create policy conversations_member_select
on public.conversations
for select
to authenticated
using (public.current_user_belongs_to_tenant(tenant_id));

create policy escalations_member_select
on public.escalations
for select
to authenticated
using (public.current_user_belongs_to_tenant(tenant_id));

create policy learning_queue_member_select
on public.learning_queue
for select
to authenticated
using (public.current_user_belongs_to_tenant(tenant_id));
