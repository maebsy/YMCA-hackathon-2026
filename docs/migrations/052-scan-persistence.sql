-- Apply after db-schema.sql (and 026 for the authenticated LLM worker).
-- Explicit migration: PostgreSQL startup never creates service tables.
begin;
create table if not exists public.scan_job (
  id varchar(32) primary key check (id ~ '^[0-9a-f]{32}$'),
  owner_id uuid references public.profile(id) on delete cascade,
  repo_url text not null,
  status varchar(10) not null check (status in ('queued','running','done','failed')),
  scan_id bigint unique references public.scan(id) on delete cascade,
  result jsonb,
  error jsonb,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  lease_until timestamptz not null
);
comment on table public.scan_job is 'Durable scan API response. Anonymous job ID is an unguessable read capability; authenticated rows require owner checks.';
alter table public.scan_job enable row level security;
revoke all on public.scan_job from public;
do $$
declare client text;
begin
  foreach client in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = client) then
      execute format('revoke all on public.scan_job from %I', client);
    end if;
  end loop;
end $$;
commit;
