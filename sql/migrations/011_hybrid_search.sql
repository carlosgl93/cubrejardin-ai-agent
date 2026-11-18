alter table public.documents
  add column if not exists fts tsvector
  generated always as (
    to_tsvector('spanish', coalesce(title, '') || ' ' || coalesce(content, ''))
  ) stored;

set maintenance_work_mem = '128MB';

create index if not exists documents_fts_gin_idx
  on public.documents
  using gin (fts);

reset maintenance_work_mem;

create or replace function public.match_documents_hybrid(
  query_embedding vector(1536),
  query_text text,
  match_count int default 12,
  p_tenant_id uuid default null,
  rrf_k int default 60
)
returns table (
  id uuid,
  title text,
  content text,
  metadata jsonb,
  similarity double precision,
  fts_rank double precision,
  rrf_score double precision
)
language sql
stable
as $$
  with dense as (
    select
      d.id,
      (1 - (d.embedding <=> query_embedding))::double precision as similarity,
      row_number() over (order by d.embedding <=> query_embedding) as rank_ix
    from public.documents d
    where (p_tenant_id is null or d.tenant_id = p_tenant_id)
    order by d.embedding <=> query_embedding
    limit greatest(match_count * 3, 20)
  ),
  ts_query as (
    select websearch_to_tsquery('spanish', coalesce(trim(query_text), '')) as q
  ),
  sparse as (
    select
      d.id,
      ts_rank_cd(d.fts, tq.q)::double precision as fts_rank,
      row_number() over (order by ts_rank_cd(d.fts, tq.q) desc) as rank_ix
    from public.documents d
    cross join ts_query tq
    where (p_tenant_id is null or d.tenant_id = p_tenant_id)
      and tq.q <> ''::tsquery
      and d.fts @@ tq.q
    order by ts_rank_cd(d.fts, tq.q) desc
    limit greatest(match_count * 3, 20)
  ),
  fused as (
    select
      coalesce(dense.id, sparse.id) as id,
      dense.similarity as dense_similarity,
      coalesce(sparse.fts_rank, 0.0)::double precision as fts_rank,
      (
        coalesce(1.0 / (rrf_k + dense.rank_ix), 0.0) +
        coalesce(1.0 / (rrf_k + sparse.rank_ix), 0.0)
      )::double precision as rrf_score
    from dense
    full outer join sparse on dense.id = sparse.id
  )
  select
    d.id,
    d.title,
    d.content,
    d.metadata,
    coalesce(f.dense_similarity, (1 - (d.embedding <=> query_embedding))::double precision) as similarity,
    f.fts_rank,
    f.rrf_score
  from fused f
  join public.documents d on d.id = f.id
  order by f.rrf_score desc, similarity desc
  limit match_count;
$$;
