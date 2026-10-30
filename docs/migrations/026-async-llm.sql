-- REVIEW REQUIRED: apply AFTER the reviewed #7 schema, never automatically at app startup.
-- Compatible with docs/7-db-design db-schema.sql blob 4e04ffaecb5c34306b886603e41855c049fc1345.
-- No table/data deletion. The owning DB reviewer must reconcile these additions into #7.
begin;

alter table public.finding drop constraint if exists finding_explain_status_check;
alter table public.finding add constraint finding_explain_status_check
  check (explain_status in ('none', 'pending', 'done', 'failed', 'skipped'));
-- Trusted scanner fields absent from #7: status, change, what, flags, fix_hint, context.
alter table public.finding add column if not exists llm_context jsonb not null default '{}'::jsonb;

-- Preserve historical B/C rows; new jobs always generate D (Red-Blue).
alter table public.explanation drop constraint if exists explanation_variant_check;
alter table public.explanation add constraint explanation_variant_check check (variant in ('B', 'C', 'D'));
alter table public.explanation add column if not exists attack_scenario text;
alter table public.explanation add column if not exists red_verdict text;
alter table public.explanation add column if not exists red_rounds jsonb not null default '[]'::jsonb;
alter table public.explanation add column if not exists needs_manual_review boolean not null default true;
alter table public.explanation add column if not exists completion_tokens integer;

create table if not exists public.llm_job (
  id uuid primary key,
  finding_id bigint not null unique references public.finding(id) on delete cascade,
  status text not null default 'queued' check (status in ('queued', 'running', 'done', 'failed', 'skipped')),
  attempts integer not null default 0 check (attempts between 0 and 3),
  lease_token uuid,
  lease_until timestamptz,
  result jsonb,
  error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((status = 'running') = (lease_token is not null and lease_until is not null))
);
create index if not exists llm_job_queue_idx on public.llm_job(created_at) where status = 'queued';
create index if not exists llm_job_lease_idx on public.llm_job(lease_until) where status = 'running';
alter table public.llm_job enable row level security;
-- Match #7: no anon/authenticated policies; access goes through FastAPI owner checks.
revoke all on public.llm_job from public;

commit;
