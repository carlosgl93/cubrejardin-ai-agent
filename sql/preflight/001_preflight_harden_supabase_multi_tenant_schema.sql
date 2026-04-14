-- Preflight checks before applying:
--   sql/migrations/003_harden_supabase_multi_tenant_schema.sql
--
-- This script is read-only. It reports conditions that may block or
-- complicate the migration: missing extensions, duplicate rows,
-- unexpected column types, nulls in columns that will become NOT NULL,
-- unexpected status/role values, and current RLS/index state.

-- ============================================================================
-- 1. Extension and object availability
-- ============================================================================

select
  'extension:vector' as check_name,
  exists(select 1 from pg_extension where extname = 'vector') as ok;

select
  'extension:pgcrypto' as check_name,
  exists(select 1 from pg_extension where extname = 'pgcrypto') as ok;

select
  n.nspname as schema_name,
  c.relname as table_name,
  c.relrowsecurity as rls_enabled
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind = 'r'
  and c.relname in (
    'tenants',
    'tenant_users',
    'tenant_whatsapp_credentials',
    'documents',
    'conversations',
    'escalations',
    'learning_queue'
  )
order by c.relname;

select
  proname as function_name,
  pg_get_function_identity_arguments(p.oid) as args
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public'
  and proname in (
    'match_documents',
    'set_updated_at',
    'current_user_belongs_to_tenant',
    'current_user_has_tenant_role'
  )
order by proname;

-- ============================================================================
-- 2. Column shape checks
-- ============================================================================

select
  table_name,
  column_name,
  data_type,
  udt_name,
  is_nullable,
  column_default
from information_schema.columns
where table_schema = 'public'
  and (
    (table_name = 'documents' and column_name in ('embedding', 'metadata', 'created_at', 'updated_at'))
    or (table_name = 'conversations' and column_name in ('message_id', 'metadata', 'created_at', 'updated_at'))
    or (table_name = 'learning_queue' and column_name in ('conversation_id', 'source', 'validated_at', 'validated_by', 'ingested_at', 'updated_at'))
    or (table_name = 'escalations' and column_name in ('updated_at', 'metadata'))
  )
order by table_name, column_name;

select
  c.relname as table_name,
  a.attname as column_name,
  format_type(a.atttypid, a.atttypmod) as formatted_type
from pg_attribute a
join pg_class c on c.oid = a.attrelid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname = 'documents'
  and a.attname = 'embedding'
  and a.attnum > 0
  and not a.attisdropped;

-- ============================================================================
-- 3. Duplicate checks that would block unique indexes
-- ============================================================================

select
  'tenant_users duplicate memberships' as check_name,
  user_id,
  tenant_id,
  count(*) as duplicate_count
from public.tenant_users
group by user_id, tenant_id
having count(*) > 1
order by duplicate_count desc, user_id, tenant_id;

select
  'tenant_whatsapp_credentials duplicate phone_number_id' as check_name,
  phone_number_id,
  count(*) as duplicate_count
from public.tenant_whatsapp_credentials
group by phone_number_id
having count(*) > 1
order by duplicate_count desc, phone_number_id;

select
  'conversations duplicate tenant_id/message_id' as check_name,
  tenant_id,
  message_id,
  count(*) as duplicate_count
from public.conversations
where message_id is not null
group by tenant_id, message_id
having count(*) > 1
order by duplicate_count desc, tenant_id, message_id;

-- ============================================================================
-- 4. Null checks for columns that 003 will harden
-- ============================================================================

select 'tenants.settings is null' as check_name, count(*) as affected_rows
from public.tenants
where settings is null;

select 'tenants.created_at is null' as check_name, count(*) as affected_rows
from public.tenants
where created_at is null;

select 'tenants.updated_at is null' as check_name, count(*) as affected_rows
from public.tenants
where updated_at is null;

select 'tenant_users.created_at is null' as check_name, count(*) as affected_rows
from public.tenant_users
where created_at is null;

select 'tenant_whatsapp_credentials.raw_oauth_response is null' as check_name, count(*) as affected_rows
from public.tenant_whatsapp_credentials
where raw_oauth_response is null;

select 'tenant_whatsapp_credentials.created_at is null' as check_name, count(*) as affected_rows
from public.tenant_whatsapp_credentials
where created_at is null;

select 'tenant_whatsapp_credentials.updated_at is null' as check_name, count(*) as affected_rows
from public.tenant_whatsapp_credentials
where updated_at is null;

select 'documents.metadata is null' as check_name, count(*) as affected_rows
from public.documents
where metadata is null;

select 'documents.embedding is null' as check_name, count(*) as affected_rows
from public.documents
where embedding is null;

select 'documents.created_at is null' as check_name, count(*) as affected_rows
from public.documents
where created_at is null;

select 'documents.updated_at is null' as check_name, count(*) as affected_rows
from public.documents
where updated_at is null;

select 'conversations.metadata is null' as check_name, count(*) as affected_rows
from public.conversations
where metadata is null;

select 'conversations.created_at is null' as check_name, count(*) as affected_rows
from public.conversations
where created_at is null;

select 'conversations.updated_at is null' as check_name, count(*) as affected_rows
from public.conversations
where updated_at is null;

select 'escalations.metadata is null' as check_name, count(*) as affected_rows
from public.escalations
where metadata is null;

select 'escalations.created_at is null' as check_name, count(*) as affected_rows
from public.escalations
where created_at is null;

select 'learning_queue.metadata is null' as check_name, count(*) as affected_rows
from public.learning_queue
where metadata is null;

select 'learning_queue.validated is null' as check_name, count(*) as affected_rows
from public.learning_queue
where validated is null;

select 'learning_queue.created_at is null' as check_name, count(*) as affected_rows
from public.learning_queue
where created_at is null;

-- ============================================================================
-- 5. Value checks for future CHECK constraints
-- ============================================================================

select
  'tenants.plan unexpected values' as check_name,
  plan,
  count(*) as affected_rows
from public.tenants
where plan is distinct from all (array['free', 'pro', 'enterprise'])
group by plan
order by affected_rows desc, plan;

select
  'tenant_users.role unexpected values' as check_name,
  role,
  count(*) as affected_rows
from public.tenant_users
where role is distinct from all (array['owner', 'admin', 'member'])
group by role
order by affected_rows desc, role;

select
  'tenant_whatsapp_credentials.status unexpected values' as check_name,
  status,
  count(*) as affected_rows
from public.tenant_whatsapp_credentials
where status is distinct from all (array['pending', 'active', 'inactive', 'error'])
group by status
order by affected_rows desc, status;

select
  'conversations.role unexpected values' as check_name,
  role,
  count(*) as affected_rows
from public.conversations
where role is distinct from all (array['user', 'assistant', 'system'])
group by role
order by affected_rows desc, role;

select
  'escalations.status unexpected values' as check_name,
  status,
  count(*) as affected_rows
from public.escalations
where status is distinct from all (array['pending', 'in_progress', 'resolved', 'cancelled'])
group by status
order by affected_rows desc, status;

select
  'escalations.handoff_type unexpected values' as check_name,
  handoff_type,
  count(*) as affected_rows
from public.escalations
where handoff_type is distinct from all (array['to_human', 'to_bot'])
group by handoff_type
order by affected_rows desc, handoff_type;

-- ============================================================================
-- 6. Documents/RAG readiness checks
-- ============================================================================

select
  'documents total rows' as check_name,
  count(*) as total_rows
from public.documents;

select
  'documents missing source_title in metadata' as check_name,
  count(*) as affected_rows
from public.documents
where coalesce(metadata->>'source_title', '') = '';

select
  tenant_id,
  count(*) as chunks,
  count(*) filter (where coalesce(metadata->>'source_title', '') = '') as chunks_without_source_title
from public.documents
group by tenant_id
order by chunks desc;

select
  indexname,
  indexdef
from pg_indexes
where schemaname = 'public'
  and tablename in (
    'documents',
    'conversations',
    'tenant_users',
    'tenant_whatsapp_credentials',
    'learning_queue',
    'escalations'
  )
order by tablename, indexname;

-- ============================================================================
-- 7. Existing policies (for review before replacing/enabling RLS)
-- ============================================================================

select
  schemaname,
  tablename,
  policyname,
  permissive,
  roles,
  cmd,
  qual,
  with_check
from pg_policies
where schemaname = 'public'
  and tablename in (
    'tenants',
    'tenant_users',
    'tenant_whatsapp_credentials',
    'documents',
    'conversations',
    'escalations',
    'learning_queue'
  )
order by tablename, policyname;

-- ============================================================================
-- 8. Quick summary counts
-- ============================================================================

select 'tenants' as table_name, count(*) as row_count from public.tenants
union all
select 'tenant_users', count(*) from public.tenant_users
union all
select 'tenant_whatsapp_credentials', count(*) from public.tenant_whatsapp_credentials
union all
select 'documents', count(*) from public.documents
union all
select 'conversations', count(*) from public.conversations
union all
select 'escalations', count(*) from public.escalations
union all
select 'learning_queue', count(*) from public.learning_queue
order by table_name;
