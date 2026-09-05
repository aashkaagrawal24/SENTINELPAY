"""Canonical carts, policy evaluations, commitments, and transaction authorization shell."""

from alembic import op

revision = "0004_core_commerce_security"
down_revision = "0003_buyer_conversation"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    create table public.carts (id uuid primary key default gen_random_uuid(), merchant_id uuid not null references public.merchants(id), user_id uuid not null references public.profiles(id), mandate_id uuid not null references public.mandates(id), status varchar(24) not null default 'DRAFT', currency char(3) not null, subtotal_minor bigint not null default 0, discount_minor bigint not null default 0, shipping_minor bigint not null default 0, total_minor bigint not null default 0, delivery jsonb not null default '{}'::jsonb, version integer not null default 1, created_at timestamptz not null default now(), updated_at timestamptz not null default now());
    create table public.cart_items (id uuid primary key default gen_random_uuid(), cart_id uuid not null references public.carts(id) on delete cascade, product_id uuid not null references public.merchant_products(id), variant_id uuid references public.product_variants(id), quantity integer not null check(quantity>0), unit_price_minor bigint not null check(unit_price_minor>=0), condition varchar(40) not null, product_snapshot jsonb not null, source_version timestamptz not null, created_at timestamptz not null default now());
    create table public.transactions (id uuid primary key default gen_random_uuid(), cart_id uuid not null references public.carts(id), user_id uuid not null references public.profiles(id), mandate_id uuid not null references public.mandates(id), status varchar(24) not null check(status in ('DRAFT','CART_READY','POLICY_CHECKING','AUTHORIZED','DENIED','REQUIRES_APPROVAL','CANCELLED')), idempotency_key varchar(120) not null unique, human_confirmed boolean not null default false, created_at timestamptz not null default now(), updated_at timestamptz not null default now());
    create table public.policy_evaluations (id uuid primary key default gen_random_uuid(), transaction_id uuid not null references public.transactions(id), buyer_mandate_id uuid not null references public.mandates(id), merchant_policy_id uuid not null references public.merchant_policies(id), merchant_policy_version integer not null, campaign_id uuid, input_snapshot jsonb not null, assertions jsonb not null, solver_result varchar(12) not null check(solver_result in ('SAT','UNSAT','ERROR')), failed_constraints jsonb not null default '[]'::jsonb, solver_version varchar(40) not null, created_at timestamptz not null default now());
    create table public.cart_commitments (id uuid primary key default gen_random_uuid(), cart_id uuid not null references public.carts(id), transaction_id uuid not null unique references public.transactions(id), approved_hash char(64) not null, approved_at timestamptz not null default now());
    create table public.payment_attempts (id uuid primary key default gen_random_uuid(), transaction_id uuid not null references public.transactions(id), idempotency_key varchar(120) not null unique, status varchar(24) not null default 'NOT_STARTED', created_at timestamptz not null default now());
    alter table public.agent_sessions add constraint agent_sessions_transaction_fk foreign key(transaction_id) references public.transactions(id) on delete set null;
    create index carts_user_idx on public.carts(user_id,created_at); create index cart_items_cart_idx on public.cart_items(cart_id); create index transactions_mandate_idx on public.transactions(mandate_id,status); create index policy_evaluations_transaction_idx on public.policy_evaluations(transaction_id);
    alter table public.carts enable row level security; alter table public.cart_items enable row level security; alter table public.transactions enable row level security; alter table public.policy_evaluations enable row level security; alter table public.cart_commitments enable row level security; alter table public.payment_attempts enable row level security;
    create policy carts_own on public.carts for all to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid()); create policy cart_items_own on public.cart_items for all to authenticated using(exists(select 1 from public.carts c where c.id=cart_items.cart_id and c.user_id=auth.uid())) with check(exists(select 1 from public.carts c where c.id=cart_items.cart_id and c.user_id=auth.uid())); create policy transactions_own on public.transactions for select to authenticated using(user_id=auth.uid()); create policy evaluations_own on public.policy_evaluations for select to authenticated using(exists(select 1 from public.transactions t where t.id=policy_evaluations.transaction_id and t.user_id=auth.uid())); create policy commitments_own on public.cart_commitments for select to authenticated using(exists(select 1 from public.transactions t where t.id=cart_commitments.transaction_id and t.user_id=auth.uid()));
    create trigger carts_updated before update on public.carts for each row execute function public.set_updated_at(); create trigger transactions_updated before update on public.transactions for each row execute function public.set_updated_at();
    """)


def downgrade():
    op.execute(
        "drop table if exists public.payment_attempts,public.cart_commitments,public.policy_evaluations,public.transactions,public.cart_items,public.carts cascade;"
    )
