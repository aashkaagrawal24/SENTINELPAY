"""Provenance, tamper-evident audit ledger, and red-team evidence."""

from alembic import op

revision = "0009_provenance_judge_mode"
down_revision = "0008_revenue_attribution"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    create table public.provenance_records (
      id uuid primary key default gen_random_uuid(), entity_type varchar(60) not null, entity_id uuid not null,
      field_name varchar(100) not null, value_snapshot jsonb not null, unit varchar(40),
      value_type varchar(24) not null check(value_type in ('REAL_DATA','DERIVED','ASSUMPTION','AI_EXTRACTED','SIMULATED','OPTIMIZED','MODEL_ESTIMATE')),
      trust_class varchar(24) not null check(trust_class in ('USER_SIGNED','MERCHANT_API','MERCHANT_SIGNED','RAZORPAY_VERIFIED','SYSTEM_DERIVED','MODEL_INFERRED','UNTRUSTED_EXTERNAL')),
      method varchar(240), model_name varchar(160), model_version varchar(80), source varchar(160) not null,
      source_reference varchar(300), source_date timestamptz, confidence numeric(5,4) check(confidence between 0 and 1),
      assumption boolean not null default false, financial_authority boolean not null default false,
      user_id uuid references public.profiles(id) on delete set null, merchant_id uuid references public.merchants(id) on delete cascade,
      created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
      check(not financial_authority or trust_class in ('USER_SIGNED','MERCHANT_SIGNED','RAZORPAY_VERIFIED'))
    );
    create table public.provenance_edges (
      parent_id uuid not null references public.provenance_records(id) on delete restrict,
      child_id uuid not null references public.provenance_records(id) on delete restrict,
      relationship varchar(40) not null default 'DERIVED_FROM', created_at timestamptz not null default now(),
      primary key(parent_id,child_id), check(parent_id<>child_id)
    );
    alter table public.audit_events add column transaction_id uuid references public.transactions(id) on delete set null,
      add column session_id uuid references public.agent_sessions(id) on delete set null,
      add column actor varchar(80) not null default 'SYSTEM', add column occurred_at timestamptz,
      add column canonical_payload jsonb not null default '{}'::jsonb, add column payload_hash char(64),
      add column previous_event_hash char(64), add column current_event_hash char(64),
      add column chain_scope varchar(160), add column chain_sequence bigint,
      add column metadata jsonb not null default '{}'::jsonb, add column provenance_ids jsonb not null default '[]'::jsonb;
    update public.audit_events set occurred_at=created_at, chain_scope='LEGACY:'||id::text, chain_sequence=1,
      previous_event_hash=repeat('0',64), payload_hash=encode(digest(canonical_payload::text,'sha256'),'hex'),
      current_event_hash=encode(digest(repeat('0',64)||canonical_payload::text,'sha256'),'hex');
    alter table public.audit_events alter column occurred_at set not null, alter column chain_scope set not null,
      alter column chain_sequence set not null, alter column payload_hash set not null,
      alter column previous_event_hash set not null, alter column current_event_hash set not null;
    create unique index audit_chain_sequence_uq on public.audit_events(chain_scope,chain_sequence);
    create index audit_transaction_chain_idx on public.audit_events(transaction_id,chain_sequence);
    create index provenance_entity_idx on public.provenance_records(entity_type,entity_id,field_name);
    create or replace function public.prevent_audit_mutation() returns trigger language plpgsql as $$
    begin raise exception 'audit_events is append-only'; end; $$;
    create trigger audit_events_append_only before update or delete on public.audit_events
      for each row execute function public.prevent_audit_mutation();
    create table public.red_team_runs (
      id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade,
      merchant_id uuid references public.merchants(id) on delete set null, status varchar(16) not null default 'RUNNING' check(status in ('RUNNING','COMPLETED','FAILED')),
      attacks_total integer not null default 0, attacks_blocked integer not null default 0,
      unsafe_executions integer not null default 0, false_blocks integer not null default 0,
      critical_bypass_rate numeric(8,6) not null default 0, started_at timestamptz not null default now(), completed_at timestamptz
    );
    create table public.red_team_attacks (
      id uuid primary key default gen_random_uuid(), run_id uuid not null references public.red_team_runs(id) on delete cascade,
      scenario_key varchar(64) not null, category varchar(24) not null, attack jsonb not null, ai_response varchar(240) not null,
      buyer_policy jsonb not null, merchant_policy jsonb not null, campaign_policy jsonb not null,
      z3_assertions jsonb not null, solver_result varchar(12) not null check(solver_result in ('SAT','UNSAT','NOT_RUN')),
      security_kernel_result varchar(24) not null, razorpay_called boolean not null default false,
      audit_event_id uuid references public.audit_events(id), expected_block boolean not null default true,
      blocked boolean not null, critical boolean not null default true, created_at timestamptz not null default now(),
      unique(run_id,scenario_key)
    );
    alter table public.provenance_records enable row level security; alter table public.provenance_edges enable row level security;
    alter table public.red_team_runs enable row level security; alter table public.red_team_attacks enable row level security;
    create policy provenance_parties on public.provenance_records for select to authenticated using(
      user_id=auth.uid() or exists(select 1 from public.merchant_users mu where mu.merchant_id=provenance_records.merchant_id and mu.user_id=auth.uid()));
    create policy provenance_edges_parties on public.provenance_edges for select to authenticated using(
      exists(select 1 from public.provenance_records p where p.id=provenance_edges.child_id and (p.user_id=auth.uid() or exists(select 1 from public.merchant_users mu where mu.merchant_id=p.merchant_id and mu.user_id=auth.uid()))));
    create policy red_team_runs_own on public.red_team_runs for select to authenticated using(user_id=auth.uid());
    create policy red_team_attacks_own on public.red_team_attacks for select to authenticated using(
      exists(select 1 from public.red_team_runs r where r.id=red_team_attacks.run_id and r.user_id=auth.uid()));
    create trigger provenance_updated before update on public.provenance_records for each row execute function public.set_updated_at();
    """)


def downgrade():
    op.execute("""
    drop table if exists public.red_team_attacks,public.red_team_runs,public.provenance_edges,public.provenance_records cascade;
    drop trigger if exists audit_events_append_only on public.audit_events;
    drop function if exists public.prevent_audit_mutation;
    alter table public.audit_events drop column if exists transaction_id,drop column if exists session_id,
      drop column if exists actor,drop column if exists occurred_at,drop column if exists canonical_payload,
      drop column if exists payload_hash,drop column if exists previous_event_hash,drop column if exists current_event_hash,
      drop column if exists chain_scope,drop column if exists chain_sequence,drop column if exists metadata,
      drop column if exists provenance_ids;
    """)
