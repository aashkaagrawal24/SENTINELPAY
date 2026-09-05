"""Stable campaign experiments and honest merchant revenue analytics."""

from alembic import op

revision = "0008_revenue_attribution"
down_revision = "0007_campaign_mvp"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    alter table public.campaigns add column experiment_enabled boolean not null default true,
      add column control_percentage integer not null default 20 check(control_percentage between 0 and 100);
    alter table public.transactions add column data_scope varchar(12) not null default 'REAL' check(data_scope in ('REAL','SIMULATED'));
    create table public.campaign_assignments (
      id uuid primary key default gen_random_uuid(), campaign_id uuid not null references public.campaigns(id) on delete cascade,
      mandate_id uuid not null references public.mandates(id), agent_session_id uuid references public.agent_sessions(id),
      bucket_value integer not null check(bucket_value between 0 and 99), assignment_group varchar(12) not null check(assignment_group in ('CONTROL','TREATMENT')),
      assigned_at timestamptz not null default now(), converted boolean not null default false,
      transaction_id uuid references public.transactions(id), data_scope varchar(12) not null default 'REAL' check(data_scope in ('REAL','SIMULATED')),
      unique(campaign_id,mandate_id), unique(campaign_id,agent_session_id)
    );
    alter table public.campaign_offers add column assignment_id uuid references public.campaign_assignments(id);
    create table public.simulated_commerce_sessions (
      id uuid primary key, merchant_id uuid not null references public.merchants(id) on delete cascade,
      campaign_id uuid references public.campaigns(id) on delete cascade, bucket_value integer not null check(bucket_value between 0 and 99),
      assignment_group varchar(12) not null check(assignment_group in ('CONTROL','TREATMENT')), converted boolean not null,
      gross_revenue_minor bigint not null default 0, attributed_revenue_minor bigint not null default 0,
      discount_cost_minor bigint not null default 0, upsell_revenue_minor bigint not null default 0,
      cross_sell_revenue_minor bigint not null default 0, provenance varchar(16) not null default 'SIMULATED' check(provenance='SIMULATED'),
      generator_seed integer not null, metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
    );
    create table public.campaign_metrics (
      id uuid primary key default gen_random_uuid(), campaign_id uuid not null references public.campaigns(id) on delete cascade,
      window_start timestamptz not null, window_end timestamptz not null, data_scope varchar(12) not null check(data_scope in ('REAL','SIMULATED')),
      eligible_sessions integer not null default 0, control_sessions integer not null default 0, treatment_sessions integer not null default 0,
      offers_served integer not null default 0, control_conversions integer not null default 0, treatment_conversions integer not null default 0,
      gross_revenue_minor bigint not null default 0, attributed_revenue_minor bigint not null default 0, discount_cost_minor bigint not null default 0,
      control_revenue_minor bigint not null default 0, treatment_revenue_minor bigint not null default 0,
      incremental_revenue_estimate_minor bigint, upsell_revenue_minor bigint not null default 0, cross_sell_revenue_minor bigint not null default 0,
      control_conversion_rate numeric(10,6) not null default 0, treatment_conversion_rate numeric(10,6) not null default 0,
      conversion_rate_lift numeric(10,6), control_aov_minor bigint not null default 0, treatment_aov_minor bigint not null default 0,
      aov_lift_minor bigint, revenue_per_discount_rupee numeric(14,6), attribution_label varchar(48) not null,
      updated_at timestamptz not null default now(), unique(campaign_id,window_start,window_end,data_scope)
    );
    create table public.merchant_metrics (
      id uuid primary key default gen_random_uuid(), merchant_id uuid not null references public.merchants(id) on delete cascade,
      period_start timestamptz not null, period_end timestamptz not null, data_scope varchar(12) not null check(data_scope in ('REAL','SIMULATED')),
      ai_sessions integer not null default 0, agent_carts integer not null default 0, checkout_attempts integer not null default 0,
      successful_orders integer not null default 0, gross_ai_revenue_minor bigint not null default 0,
      conversion_rate numeric(10,6) not null default 0, average_order_value_minor bigint not null default 0,
      negotiation_sessions integer not null default 0, negotiation_conversions integer not null default 0, negotiation_revenue_minor bigint not null default 0,
      negotiation_discount_cost_minor bigint not null default 0, upsell_offers integer not null default 0, upsell_acceptances integer not null default 0,
      upsell_revenue_minor bigint not null default 0, cross_sell_offers integer not null default 0, cross_sell_acceptances integer not null default 0,
      cross_sell_revenue_minor bigint not null default 0, campaign_offers integer not null default 0, campaign_conversions integer not null default 0,
      campaign_attributed_revenue_minor bigint not null default 0, controlled_incremental_estimate_minor bigint,
      campaign_discount_cost_minor bigint not null default 0, policy_violations_blocked integer not null default 0,
      refunds_supported boolean not null default false, updated_at timestamptz not null default now(),
      unique(merchant_id,period_start,period_end,data_scope)
    );
    create index campaign_assignments_campaign_idx on public.campaign_assignments(campaign_id,assignment_group,assigned_at);
    create index simulated_sessions_merchant_idx on public.simulated_commerce_sessions(merchant_id,campaign_id,created_at);
    create index campaign_metrics_campaign_idx on public.campaign_metrics(campaign_id,window_end desc);
    create index merchant_metrics_merchant_idx on public.merchant_metrics(merchant_id,period_end desc);
    alter table public.campaign_assignments enable row level security; alter table public.simulated_commerce_sessions enable row level security;
    alter table public.campaign_metrics enable row level security; alter table public.merchant_metrics enable row level security;
    create policy campaign_assignments_parties on public.campaign_assignments for select to authenticated using(
      exists(select 1 from public.mandates m where m.id=campaign_assignments.mandate_id and m.user_id=auth.uid())
      or exists(select 1 from public.campaigns c join public.merchant_users mu on mu.merchant_id=c.merchant_id where c.id=campaign_assignments.campaign_id and mu.user_id=auth.uid()));
    create policy simulated_sessions_member on public.simulated_commerce_sessions for select to authenticated using(exists(select 1 from public.merchant_users mu where mu.merchant_id=simulated_commerce_sessions.merchant_id and mu.user_id=auth.uid()));
    create policy campaign_metrics_member on public.campaign_metrics for select to authenticated using(exists(select 1 from public.campaigns c join public.merchant_users mu on mu.merchant_id=c.merchant_id where c.id=campaign_metrics.campaign_id and mu.user_id=auth.uid()));
    create policy merchant_metrics_member on public.merchant_metrics for select to authenticated using(exists(select 1 from public.merchant_users mu where mu.merchant_id=merchant_metrics.merchant_id and mu.user_id=auth.uid()));
    """)


def downgrade():
    op.execute("""
    drop table if exists public.merchant_metrics,public.campaign_metrics,public.simulated_commerce_sessions,public.campaign_assignments cascade;
    alter table public.campaign_offers drop column if exists assignment_id;
    alter table public.transactions drop column if exists data_scope;
    alter table public.campaigns drop column if exists control_percentage,drop column if exists experiment_enabled;
    """)
