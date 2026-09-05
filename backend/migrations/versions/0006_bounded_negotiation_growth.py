"""Bounded negotiation sessions and basket-growth revenue signals."""

from alembic import op

revision = "0006_bounded_negotiation_growth"
down_revision = "0005_razorpay_test_payments"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    create table public.negotiation_sessions (
      id uuid primary key default gen_random_uuid(), buyer_user_id uuid not null references public.profiles(id), mandate_id uuid not null references public.mandates(id), merchant_id uuid not null references public.merchants(id), product_id uuid not null references public.merchant_products(id), merchant_policy_id uuid not null references public.merchant_policies(id), merchant_policy_version integer not null, starting_price_minor bigint not null check(starting_price_minor>=0), buyer_ceiling_minor bigint not null check(buyer_ceiling_minor>=0), merchant_floor_minor bigint not null check(merchant_floor_minor>=0), fallback_offer_id uuid, fallback_cart_id uuid references public.carts(id), fallback_price_minor bigint, fallback_valid_until timestamptz, current_round integer not null default 0, max_rounds integer not null check(max_rounds>0), last_buyer_offer_minor bigint, last_merchant_ask_minor bigint, status varchar(20) not null check(status in ('OPEN','ACCEPTED','REJECTED','FALLBACK','EXPIRED','CANCELLED')), final_agreed_price_minor bigint, created_at timestamptz not null default now(), expires_at timestamptz not null, updated_at timestamptz not null default now()
    );
    create table public.negotiation_messages (
      id uuid primary key default gen_random_uuid(), session_id uuid not null references public.negotiation_sessions(id) on delete cascade, actor varchar(20) not null check(actor in ('BUYER_AGENT','MERCHANT_AGENT','SYSTEM')), round_number integer not null, text text not null, proposed_amount_minor bigint, structured_action varchar(24) not null check(structured_action in ('OPEN','OFFER','COUNTER','CONTINUE','ACCEPT','REJECT','FALLBACK','EXPIRE','BLOCK')), model_provider varchar(60), model_name varchar(120), model_version varchar(60), created_at timestamptz not null default now()
    );
    create table public.upsell_events (
      id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id), mandate_id uuid not null references public.mandates(id), merchant_id uuid not null references public.merchants(id), source_product_id uuid not null references public.merchant_products(id), offered_product_id uuid not null references public.merchant_products(id), negotiation_session_id uuid references public.negotiation_sessions(id), cart_id uuid references public.carts(id), transaction_id uuid references public.transactions(id), accepted boolean not null default false, offered_amount_minor bigint not null, incremental_revenue_minor bigint not null default 0, recommit_result varchar(24), recommit_hash char(64), created_at timestamptz not null default now(), accepted_at timestamptz
    );
    create table public.cross_sell_events (
      id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id), mandate_id uuid not null references public.mandates(id), merchant_id uuid not null references public.merchants(id), source_product_id uuid not null references public.merchant_products(id), offered_product_id uuid not null references public.merchant_products(id), negotiation_session_id uuid references public.negotiation_sessions(id), cart_id uuid references public.carts(id), transaction_id uuid references public.transactions(id), accepted boolean not null default false, offered_amount_minor bigint not null, incremental_revenue_minor bigint not null default 0, recommit_result varchar(24), recommit_hash char(64), created_at timestamptz not null default now(), accepted_at timestamptz
    );
    create index negotiation_buyer_idx on public.negotiation_sessions(buyer_user_id,created_at desc); create index negotiation_product_idx on public.negotiation_sessions(product_id,status); create index negotiation_messages_session_idx on public.negotiation_messages(session_id,round_number); create index upsell_events_user_idx on public.upsell_events(user_id,created_at); create index cross_sell_events_user_idx on public.cross_sell_events(user_id,created_at);
    alter table public.negotiation_sessions enable row level security; alter table public.negotiation_messages enable row level security; alter table public.upsell_events enable row level security; alter table public.cross_sell_events enable row level security;
    create policy negotiation_buyer_read on public.negotiation_sessions for select to authenticated using(buyer_user_id=auth.uid()); create policy negotiation_merchant_read on public.negotiation_sessions for select to authenticated using(exists(select 1 from public.merchant_users mu where mu.merchant_id=negotiation_sessions.merchant_id and mu.user_id=auth.uid())); create policy negotiation_messages_party_read on public.negotiation_messages for select to authenticated using(exists(select 1 from public.negotiation_sessions ns where ns.id=negotiation_messages.session_id and (ns.buyer_user_id=auth.uid() or exists(select 1 from public.merchant_users mu where mu.merchant_id=ns.merchant_id and mu.user_id=auth.uid())))); create policy upsell_buyer_read on public.upsell_events for select to authenticated using(user_id=auth.uid()); create policy cross_sell_buyer_read on public.cross_sell_events for select to authenticated using(user_id=auth.uid());
    create trigger negotiation_sessions_updated before update on public.negotiation_sessions for each row execute function public.set_updated_at();
    """)


def downgrade():
    op.execute(
        "drop table if exists public.cross_sell_events,public.upsell_events,public.negotiation_messages,public.negotiation_sessions cascade;"
    )
