"""Complete advanced algorithms, privacy evidence, procurement, refunds and reconciliation."""

from alembic import op

revision = "0011_complete_advanced_stack"
down_revision = "0010_advanced_extensions"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        create table public.platform_connectors (
          platform_key varchar(48) primary key, display_name varchar(100) not null, platform_mode varchar(40) not null,
          search_supported boolean not null, negotiation_supported boolean not null, checkout_supported boolean not null,
          handoff_supported boolean not null, data_source varchar(100) not null, enabled boolean not null default true,
          updated_at timestamptz not null default now()
        );
        alter table public.transactions add column advanced_verification_required boolean not null default false;
        alter table public.transactions add column advanced_evidence jsonb;
        insert into public.platform_connectors(platform_key,display_name,platform_mode,search_supported,negotiation_supported,checkout_supported,handoff_supported,data_source) values
        ('OLX','OLX','NEGOTIATION_MARKETPLACE',true,true,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('QUIKR','Quikr','NEGOTIATION_MARKETPLACE',true,true,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('FACEBOOK_MARKETPLACE','Facebook Marketplace','NEGOTIATION_MARKETPLACE',true,true,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('INDIAMART','IndiaMART','NEGOTIATION_MARKETPLACE',true,true,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('TRADEINDIA','TradeIndia','NEGOTIATION_MARKETPLACE',true,true,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('LOCAL_CLASSIFIEDS','Local Classifieds','NEGOTIATION_MARKETPLACE',true,true,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('MEESHO','Meesho','SEMI_NEGOTIABLE',true,false,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('SHOPCLUES','ShopClues','SEMI_NEGOTIABLE',true,false,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('SNAPDEAL','Snapdeal','SEMI_NEGOTIABLE',true,false,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('JIOMART','JioMart','SEMI_NEGOTIABLE',true,false,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('AMAZON','Amazon','FIXED_SCOUT',true,false,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('FLIPKART','Flipkart','FIXED_SCOUT',true,false,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('MYNTRA','Myntra','FIXED_SCOUT',true,false,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('NYKAA','Nykaa','FIXED_SCOUT',true,false,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('TATA_CLIQ','Tata CLiQ','FIXED_SCOUT',true,false,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('CROMA','Croma','FIXED_SCOUT',true,false,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF'),
        ('RELIANCE_DIGITAL','Reliance Digital','FIXED_SCOUT',true,false,false,true,'CONTROLLED_SNAPSHOT_OR_USER_HANDOFF');

        create table public.negotiability_models (
          id uuid primary key default gen_random_uuid(), version varchar(40) not null unique, algorithm varchar(80) not null,
          feature_schema jsonb not null, metrics jsonb not null, training_provenance varchar(80) not null,
          artifact_sha256 char(64), active boolean not null default false, created_at timestamptz not null default now()
        );
        create unique index uq_active_negotiability_model on public.negotiability_models(active) where active;
        create table public.linucb_models (
          id uuid primary key default gen_random_uuid(), merchant_id uuid not null references public.merchants(id) on delete cascade,
          context_key varchar(180) not null, action varchar(32) not null, dimension integer not null check(dimension>0),
          alpha numeric(12,6) not null, a_matrix jsonb not null, b_vector jsonb not null, observations integer not null default 0,
          updated_at timestamptz not null default now(), unique(merchant_id,context_key,action)
        );
        create table public.linucb_outcomes (
          id uuid primary key default gen_random_uuid(), model_id uuid not null references public.linucb_models(id) on delete cascade,
          context_vector jsonb not null, reward numeric(18,6) not null, savings_minor bigint not null default 0,
          elapsed_ms integer not null default 0, failed boolean not null default false, created_at timestamptz not null default now()
        );
        create table public.causal_analysis_runs (
          id uuid primary key default gen_random_uuid(), merchant_id uuid references public.merchants(id) on delete cascade,
          campaign_id uuid references public.campaigns(id) on delete set null, method varchar(100) not null,
          common_causes jsonb not null, estimand text not null, estimate numeric(24,8) not null, simple_estimate numeric(24,8),
          refutations jsonb not null, assumptions jsonb not null, created_at timestamptz not null default now()
        );
        create table public.dp_aggregate_runs (
          id uuid primary key default gen_random_uuid(), merchant_id uuid references public.merchants(id) on delete cascade,
          statistic varchar(16) not null, epsilon numeric(12,6) not null check(epsilon>0), lower_bound numeric not null,
          upper_bound numeric not null, record_count integer not null check(record_count>0), private_value numeric not null,
          scope varchar(40) not null default 'AGGREGATE_ANALYTICS_ONLY', created_at timestamptz not null default now()
        );
        create table public.provenance_graph_runs (
          id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade,
          node_count integer not null, edge_count integer not null, query_safe jsonb not null, result_safe jsonb not null,
          created_at timestamptz not null default now()
        );
        create table public.he_aggregate_runs (
          id uuid primary key default gen_random_uuid(), merchant_id uuid references public.merchants(id) on delete cascade,
          scheme varchar(40) not null, operation varchar(40) not null, record_count integer not null,
          ciphertext_fingerprint char(64) not null, verified boolean not null, elapsed_ms integer not null,
          created_at timestamptz not null default now()
        );
        create table public.bls_approval_runs (
          id uuid primary key default gen_random_uuid(), transaction_id uuid references public.transactions(id) on delete cascade,
          payload_hash char(64) not null, required_k integer not null, verifier_roles jsonb not null,
          public_keys jsonb not null, aggregate_signature text not null, aggregate_valid boolean not null,
          created_at timestamptz not null default now(), unique(transaction_id,payload_hash)
        );
        create table public.vdf_runs (
          id uuid primary key default gen_random_uuid(), purpose varchar(80) not null, challenge_hash char(64) not null,
          iterations integer not null check(iterations>0), output text not null, proof text not null, verified boolean not null,
          evaluation_ms integer not null, created_at timestamptz not null default now()
        );
        create table public.sealed_bid_commits (
          id uuid primary key default gen_random_uuid(), rfq_id uuid not null references public.procurement_rfqs(id) on delete cascade,
          vendor_id uuid not null references public.merchants(id), commitment char(64) not null, status varchar(16) not null
          check(status in ('COMMITTED','REVEALED','INVALID','EXPIRED')), revealed_quote_id uuid references public.supplier_quotes(id),
          committed_at timestamptz not null default now(), revealed_at timestamptz, unique(rfq_id,vendor_id)
        );
        create table public.vcg_results (
          id uuid primary key default gen_random_uuid(), rfq_id uuid not null unique references public.procurement_rfqs(id) on delete cascade,
          social_welfare_minor bigint not null, reported_total_minor bigint not null, vcg_total_minor bigint not null,
          allocation jsonb not null, winner_payments jsonb not null, vdf_run_id uuid references public.vdf_runs(id),
          status varchar(24) not null check(status in ('ALLOCATED','REQUIRES_APPROVAL','DENIED')),
          created_at timestamptz not null default now()
        );
        create table public.procurement_settlement_simulations (
          id uuid primary key default gen_random_uuid(), vcg_result_id uuid not null references public.vcg_results(id) on delete cascade,
          status varchar(24) not null check(status in ('READY','BLOCKED','COMPLETED')),
          entries jsonb not null, total_minor bigint not null, razorpay_orders_created integer not null default 0,
          created_at timestamptz not null default now()
        );
        create table public.refunds (
          id uuid primary key default gen_random_uuid(), payment_attempt_id uuid not null references public.payment_attempts(id),
          user_id uuid not null references public.profiles(id), amount_minor bigint not null check(amount_minor>0), currency char(3) not null,
          reason varchar(200) not null, idempotency_key varchar(120) not null unique, provider_refund_id varchar(100) unique,
          status varchar(24) not null check(status in ('REQUESTED','PROCESSING','PROCESSED','FAILED','UNKNOWN')),
          provider_payload_safe jsonb not null default '{}'::jsonb, created_at timestamptz not null default now(),
          updated_at timestamptz not null default now()
        );
        create index ix_refunds_attempt_status on public.refunds(payment_attempt_id,status);
        create table public.payment_reconciliations (
          id uuid primary key default gen_random_uuid(), payment_attempt_id uuid not null references public.payment_attempts(id),
          observed_status varchar(24) not null, provider_status varchar(24), amount_matches boolean not null,
          currency_matches boolean not null, resolution varchar(40) not null, details_safe jsonb not null default '{}'::jsonb,
          created_at timestamptz not null default now()
        );
        create index ix_reconciliation_attempt_created on public.payment_reconciliations(payment_attempt_id,created_at desc);

        alter table public.platform_connectors enable row level security;
        create policy platform_registry_read on public.platform_connectors for select to authenticated using(true);
        """
    )
    owned_tables = (
        "linucb_models",
        "causal_analysis_runs",
        "dp_aggregate_runs",
        "he_aggregate_runs",
    )
    for table in owned_tables:
        op.execute(
            f"""alter table public.{table} enable row level security;
            create policy {table}_merchant_read on public.{table} for select to authenticated using(
              merchant_id is not null and exists(
                select 1 from public.merchant_users mu
                where mu.merchant_id={table}.merchant_id and mu.user_id=auth.uid()
              )
            );"""
        )
    for table in (
        "negotiability_models",
        "linucb_outcomes",
        "bls_approval_runs",
        "vdf_runs",
        "sealed_bid_commits",
        "vcg_results",
        "procurement_settlement_simulations",
        "payment_reconciliations",
    ):
        op.execute(f"alter table public.{table} enable row level security;")
    op.execute(
        """
        alter table public.provenance_graph_runs enable row level security;
        create policy provenance_graph_owner_read on public.provenance_graph_runs for select to authenticated using(user_id=auth.uid());
        alter table public.refunds enable row level security;
        create policy refund_owner_read on public.refunds for select to authenticated using(user_id=auth.uid());
        """
    )


def downgrade():
    op.execute("alter table public.transactions drop column if exists advanced_evidence")
    op.execute("alter table public.transactions drop column if exists advanced_verification_required")
    for table in (
        "payment_reconciliations",
        "refunds",
        "procurement_settlement_simulations",
        "vcg_results",
        "sealed_bid_commits",
        "vdf_runs",
        "bls_approval_runs",
        "he_aggregate_runs",
        "provenance_graph_runs",
        "dp_aggregate_runs",
        "causal_analysis_runs",
        "linucb_outcomes",
        "linucb_models",
        "negotiability_models",
        "platform_connectors",
    ):
        op.execute(f"drop table if exists public.{table} cascade")
