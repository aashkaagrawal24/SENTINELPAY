"""Isolated, feature-flagged advanced extension evidence."""

from alembic import op

revision = "0010_advanced_extensions"
down_revision = "0009_provenance_judge_mode"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    create table public.advanced_feature_runs (
      id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade,
      merchant_id uuid references public.merchants(id) on delete set null,
      feature_key varchar(48) not null, status varchar(20) not null check(status in ('SUCCESS','FALLBACK','FAILED','RESEARCH_ONLY')),
      input_safe jsonb not null default '{}'::jsonb, result_safe jsonb not null default '{}'::jsonb,
      metrics jsonb not null default '{}'::jsonb, baseline jsonb not null default '{}'::jsonb,
      provenance_id uuid references public.provenance_records(id), audit_event_id uuid references public.audit_events(id),
      created_at timestamptz not null default now()
    );
    create table public.external_offer_snapshots (
      id uuid primary key default gen_random_uuid(), run_id uuid not null references public.advanced_feature_runs(id) on delete cascade,
      connector varchar(80) not null, capability varchar(32) not null check(capability in ('PUBLIC_SCOUT','AUTHENTICATED_DISCOVERY','NEGOTIATION_ONLY','FULL_AGENTIC','HANDOFF')),
      external_offer_id varchar(160) not null, normalized_product_key varchar(240) not null, title varchar(300) not null,
      price_minor bigint not null check(price_minor>=0), currency char(3) not null, checkout_capability varchar(32) not null,
      source_url varchar(600), fetched_at timestamptz not null, freshness_seconds integer not null check(freshness_seconds>=0),
      provenance_id uuid not null references public.provenance_records(id), unique(connector,external_offer_id,fetched_at)
    );
    create table public.bandit_strategy_stats (
      id uuid primary key default gen_random_uuid(), merchant_id uuid not null references public.merchants(id) on delete cascade,
      context_key varchar(180) not null, action varchar(32) not null check(action in ('AGGRESSIVE','BALANCED','FAST_CLOSE','UPSELL_VALUE','UPSELL_PREMIUM')),
      pulls integer not null default 0 check(pulls>=0), cumulative_reward numeric(18,6) not null default 0,
      updated_at timestamptz not null default now(), unique(merchant_id,context_key,action)
    );
    create table public.zk_budget_proofs (
      id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade,
      mandate_id uuid references public.mandates(id) on delete set null, public_price_minor bigint not null check(public_price_minor>=0),
      budget_commitment text not null, proof jsonb not null, verified boolean not null, circuit_statement varchar(160) not null,
      generation_ms integer not null, verification_ms integer not null, created_at timestamptz not null default now()
    );
    create table public.multi_verifier_requests (
      id uuid primary key default gen_random_uuid(), transaction_id uuid not null references public.transactions(id),
      user_id uuid not null references public.profiles(id), required_k integer not null check(required_k>0), verifier_count integer not null check(verifier_count>=required_k),
      payload_hash char(64) not null, status varchar(20) not null check(status in ('PENDING','APPROVED','DENIED','TIMED_OUT')),
      expires_at timestamptz not null, created_at timestamptz not null default now(), unique(transaction_id,payload_hash)
    );
    create table public.verifier_attestations (
      id uuid primary key default gen_random_uuid(), request_id uuid not null references public.multi_verifier_requests(id) on delete cascade,
      verifier_id varchar(80) not null, decision varchar(12) not null check(decision in ('APPROVE','DENY')),
      payload_hash char(64) not null, public_key text not null, signature text not null, verified boolean not null,
      issued_at timestamptz not null, expires_at timestamptz not null, unique(request_id,verifier_id)
    );
    create table public.procurement_rfqs (
      id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade,
      product_query varchar(300) not null, required_quantity integer not null check(required_quantity>0),
      max_budget_minor bigint not null check(max_budget_minor>=0), currency char(3) not null,
      approved_vendor_ids jsonb not null, delivery_deadline timestamptz not null,
      lambda_delivery numeric(10,4) not null default 1, lambda_vendor_risk numeric(10,4) not null default 1,
      status varchar(20) not null default 'OPEN' check(status in ('OPEN','OPTIMIZED','CANCELLED','EXPIRED')),
      created_at timestamptz not null default now()
    );
    create table public.supplier_quotes (
      id uuid primary key default gen_random_uuid(), rfq_id uuid not null references public.procurement_rfqs(id) on delete cascade,
      merchant_id uuid not null references public.merchants(id), unit_price_minor bigint not null check(unit_price_minor>=0),
      available_quantity integer not null check(available_quantity>=0), delivery_at timestamptz not null,
      vendor_risk_basis_points integer not null check(vendor_risk_basis_points between 0 and 10000),
      merchant_minimum_quantity integer not null default 1 check(merchant_minimum_quantity>0), created_at timestamptz not null default now(),
      unique(rfq_id,merchant_id)
    );
    create table public.procurement_allocations (
      id uuid primary key default gen_random_uuid(), rfq_id uuid not null references public.procurement_rfqs(id) on delete cascade,
      quote_id uuid not null references public.supplier_quotes(id), allocated_quantity integer not null check(allocated_quantity>0),
      allocated_cost_minor bigint not null check(allocated_cost_minor>=0), objective_contribution numeric(20,4) not null,
      provenance_id uuid references public.provenance_records(id), created_at timestamptz not null default now(), unique(rfq_id,quote_id)
    );
    create table public.negotiation_simulation_runs (
      id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade,
      seed integer not null, episodes integer not null check(episodes>0), baseline_strategy varchar(32) not null,
      candidate_strategy varchar(32) not null, baseline_reward numeric(18,6) not null, candidate_reward numeric(18,6) not null,
      agreement_rate numeric(8,6) not null, average_rounds numeric(8,4) not null, result jsonb not null,
      provenance_id uuid references public.provenance_records(id), created_at timestamptz not null default now()
    );
    create index advanced_runs_user_idx on public.advanced_feature_runs(user_id,feature_key,created_at desc);
    create index external_offers_product_idx on public.external_offer_snapshots(normalized_product_key,fetched_at desc);
    create index zk_proofs_user_idx on public.zk_budget_proofs(user_id,created_at desc);
    create index rfqs_user_idx on public.procurement_rfqs(user_id,status,created_at desc);
    alter table public.advanced_feature_runs enable row level security; alter table public.external_offer_snapshots enable row level security;
    alter table public.bandit_strategy_stats enable row level security; alter table public.zk_budget_proofs enable row level security;
    alter table public.multi_verifier_requests enable row level security; alter table public.verifier_attestations enable row level security;
    alter table public.procurement_rfqs enable row level security; alter table public.supplier_quotes enable row level security;
    alter table public.procurement_allocations enable row level security; alter table public.negotiation_simulation_runs enable row level security;
    create policy advanced_runs_own on public.advanced_feature_runs for select to authenticated using(user_id=auth.uid());
    create policy external_offers_own on public.external_offer_snapshots for select to authenticated using(exists(select 1 from public.advanced_feature_runs r where r.id=external_offer_snapshots.run_id and r.user_id=auth.uid()));
    create policy bandit_stats_member on public.bandit_strategy_stats for select to authenticated using(exists(select 1 from public.merchant_users mu where mu.merchant_id=bandit_strategy_stats.merchant_id and mu.user_id=auth.uid()));
    create policy zk_proofs_own on public.zk_budget_proofs for select to authenticated using(user_id=auth.uid());
    create policy verifier_requests_own on public.multi_verifier_requests for select to authenticated using(user_id=auth.uid());
    create policy verifier_attestations_own on public.verifier_attestations for select to authenticated using(exists(select 1 from public.multi_verifier_requests r where r.id=verifier_attestations.request_id and r.user_id=auth.uid()));
    create policy rfqs_own on public.procurement_rfqs for select to authenticated using(user_id=auth.uid());
    create policy supplier_quotes_parties on public.supplier_quotes for select to authenticated using(exists(select 1 from public.procurement_rfqs r where r.id=supplier_quotes.rfq_id and r.user_id=auth.uid()) or exists(select 1 from public.merchant_users mu where mu.merchant_id=supplier_quotes.merchant_id and mu.user_id=auth.uid()));
    create policy allocations_own on public.procurement_allocations for select to authenticated using(exists(select 1 from public.procurement_rfqs r where r.id=procurement_allocations.rfq_id and r.user_id=auth.uid()));
    create policy simulation_runs_own on public.negotiation_simulation_runs for select to authenticated using(user_id=auth.uid());
    create trigger bandit_stats_updated before update on public.bandit_strategy_stats for each row execute function public.set_updated_at();
    """)


def downgrade():
    op.execute("""
    drop table if exists public.negotiation_simulation_runs,public.procurement_allocations,public.supplier_quotes,
      public.procurement_rfqs,public.verifier_attestations,public.multi_verifier_requests,public.zk_budget_proofs,
      public.bandit_strategy_stats,public.external_offer_snapshots,public.advanced_feature_runs cascade;
    """)
