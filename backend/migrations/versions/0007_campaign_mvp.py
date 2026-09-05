"""Bounded campaigns, opportunities, offers, events, and redemption controls."""

from alembic import op

revision = "0007_campaign_mvp"
down_revision = "0006_bounded_negotiation_growth"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    create table public.campaign_opportunities (
      id uuid primary key default gen_random_uuid(), merchant_id uuid not null references public.merchants(id) on delete cascade,
      trigger_type varchar(16) not null check(trigger_type in ('SCHEDULED','REALTIME','MANUAL')), product_ids jsonb not null default '[]'::jsonb,
      recommended_campaign_type varchar(32) not null, score numeric(6,5) not null check(score>=0 and score<=1), reasons jsonb not null,
      input_metrics jsonb not null, status varchar(16) not null default 'OPEN' check(status in ('OPEN','ACCEPTED','REJECTED','EXPIRED')),
      generated_at timestamptz not null default now(), expires_at timestamptz not null, converted_campaign_id uuid
    );
    create table public.campaigns (
      id uuid primary key default gen_random_uuid(), merchant_id uuid not null references public.merchants(id) on delete cascade,
      opportunity_id uuid references public.campaign_opportunities(id), name varchar(180) not null, campaign_type varchar(32) not null,
      objective varchar(160) not null, status varchar(16) not null default 'PROPOSED' check(status in ('DRAFT','PROPOSED','APPROVED','SCHEDULED','ACTIVE','PAUSED','COMPLETED','STOPPED')),
      discount_type varchar(16) not null check(discount_type in ('PERCENT','FIXED')), discount_value bigint not null check(discount_value>0),
      max_discount_per_order_minor bigint not null check(max_discount_per_order_minor>0), total_discount_budget_minor bigint not null check(total_discount_budget_minor>=0),
      used_discount_budget_minor bigint not null default 0 check(used_discount_budget_minor>=0), reserved_discount_budget_minor bigint not null default 0 check(reserved_discount_budget_minor>=0), maximum_redemptions integer not null check(maximum_redemptions>0),
      current_redemptions integer not null default 0 check(current_redemptions>=0), reserved_redemptions integer not null default 0 check(reserved_redemptions>=0), minimum_margin_percent numeric(5,2), minimum_final_price_minor bigint,
      auto_optimize_allowed boolean not null default false, requires_merchant_approval boolean not null default true,
      eligibility jsonb not null default '{}'::jsonb, start_time timestamptz not null, end_time timestamptz not null,
      stop_conditions jsonb not null default '{}'::jsonb, created_by uuid not null references public.profiles(id), approved_by uuid references public.profiles(id),
      approved_at timestamptz, created_at timestamptz not null default now(), updated_at timestamptz not null default now(), check(end_time>start_time)
    );
    alter table public.campaign_opportunities add constraint campaign_opportunity_conversion_fk foreign key(converted_campaign_id) references public.campaigns(id);
    create table public.campaign_products (
      campaign_id uuid not null references public.campaigns(id) on delete cascade, product_id uuid not null references public.merchant_products(id) on delete cascade,
      primary key(campaign_id,product_id)
    );
    create table public.campaign_offers (
      id uuid primary key default gen_random_uuid(), campaign_id uuid not null references public.campaigns(id), user_id uuid not null references public.profiles(id),
      mandate_id uuid not null references public.mandates(id), product_id uuid not null references public.merchant_products(id), cart_id uuid references public.carts(id),
      status varchar(16) not null default 'ELIGIBLE' check(status in ('ELIGIBLE','APPLIED','REDEEMED','EXPIRED','REVOKED')),
      discount_minor bigint not null check(discount_minor>0), eligibility_snapshot jsonb not null, expires_at timestamptz not null,
      created_at timestamptz not null default now(), applied_at timestamptz, unique(campaign_id,mandate_id,product_id)
    );
    create table public.campaign_events (
      id uuid primary key default gen_random_uuid(), campaign_id uuid references public.campaigns(id) on delete cascade,
      opportunity_id uuid references public.campaign_opportunities(id) on delete cascade, merchant_id uuid not null references public.merchants(id),
      event_type varchar(48) not null, actor_type varchar(24) not null, actor_id uuid, payload jsonb not null default '{}'::jsonb,
      created_at timestamptz not null default now()
    );
    create table public.campaign_redemptions (
      id uuid primary key default gen_random_uuid(), campaign_id uuid not null references public.campaigns(id), offer_id uuid not null unique references public.campaign_offers(id),
      transaction_id uuid not null unique references public.transactions(id), discount_minor bigint not null,
      status varchar(16) not null default 'RESERVED' check(status in ('RESERVED','REDEEMED','RELEASED')), created_at timestamptz not null default now(), redeemed_at timestamptz, released_at timestamptz
    );
    alter table public.carts add column campaign_id uuid references public.campaigns(id), add column campaign_offer_id uuid references public.campaign_offers(id), add column campaign_discount_minor bigint not null default 0, add column campaign_reconfirmation_required boolean not null default false;
    alter table public.transactions add column campaign_offer_id uuid references public.campaign_offers(id);
    alter table public.policy_evaluations add constraint policy_evaluations_campaign_fk foreign key(campaign_id) references public.campaigns(id);
    create index campaign_opportunities_merchant_idx on public.campaign_opportunities(merchant_id,status,score desc);
    create index campaigns_merchant_status_idx on public.campaigns(merchant_id,status,start_time,end_time);
    create index campaign_products_product_idx on public.campaign_products(product_id,campaign_id);
    create index campaign_offers_user_idx on public.campaign_offers(user_id,status,expires_at);
    create index campaign_events_campaign_idx on public.campaign_events(campaign_id,created_at desc);
    alter table public.campaign_opportunities enable row level security; alter table public.campaigns enable row level security;
    alter table public.campaign_products enable row level security; alter table public.campaign_offers enable row level security;
    alter table public.campaign_events enable row level security; alter table public.campaign_redemptions enable row level security;
    create policy campaign_opportunities_member on public.campaign_opportunities for all to authenticated using(exists(select 1 from public.merchant_users mu where mu.merchant_id=campaign_opportunities.merchant_id and mu.user_id=auth.uid())) with check(exists(select 1 from public.merchant_users mu where mu.merchant_id=campaign_opportunities.merchant_id and mu.user_id=auth.uid() and mu.role in ('OWNER','ADMIN')));
    create policy campaigns_member on public.campaigns for select to authenticated using(exists(select 1 from public.merchant_users mu where mu.merchant_id=campaigns.merchant_id and mu.user_id=auth.uid()));
    create policy campaigns_operator on public.campaigns for all to authenticated using(exists(select 1 from public.merchant_users mu where mu.merchant_id=campaigns.merchant_id and mu.user_id=auth.uid() and mu.role in ('OWNER','ADMIN'))) with check(exists(select 1 from public.merchant_users mu where mu.merchant_id=campaigns.merchant_id and mu.user_id=auth.uid() and mu.role in ('OWNER','ADMIN')));
    create policy campaign_products_member on public.campaign_products for all to authenticated using(exists(select 1 from public.campaigns c join public.merchant_users mu on mu.merchant_id=c.merchant_id where c.id=campaign_products.campaign_id and mu.user_id=auth.uid())) with check(exists(select 1 from public.campaigns c join public.merchant_users mu on mu.merchant_id=c.merchant_id where c.id=campaign_products.campaign_id and mu.user_id=auth.uid() and mu.role in ('OWNER','ADMIN')));
    create policy campaign_offers_buyer on public.campaign_offers for select to authenticated using(user_id=auth.uid());
    create policy campaign_events_member on public.campaign_events for select to authenticated using(exists(select 1 from public.merchant_users mu where mu.merchant_id=campaign_events.merchant_id and mu.user_id=auth.uid()));
    create policy campaign_redemptions_buyer on public.campaign_redemptions for select to authenticated using(exists(select 1 from public.transactions t where t.id=campaign_redemptions.transaction_id and t.user_id=auth.uid()));
    create trigger campaigns_updated before update on public.campaigns for each row execute function public.set_updated_at();
    """)


def downgrade():
    op.execute("""
    alter table public.policy_evaluations drop constraint if exists policy_evaluations_campaign_fk;
    alter table public.transactions drop column if exists campaign_offer_id;
    alter table public.carts drop column if exists campaign_reconfirmation_required, drop column if exists campaign_discount_minor, drop column if exists campaign_offer_id, drop column if exists campaign_id;
    drop table if exists public.campaign_redemptions,public.campaign_events,public.campaign_offers,public.campaign_products,public.campaigns,public.campaign_opportunities cascade;
    """)
