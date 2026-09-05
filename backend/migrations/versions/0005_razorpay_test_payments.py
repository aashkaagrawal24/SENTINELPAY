"""Razorpay Test Mode payment attempts and durable event deduplication."""

from alembic import op

revision = "0005_razorpay_test_payments"
down_revision = "0004_core_commerce_security"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    alter table public.payment_attempts drop column status;
    alter table public.payment_attempts add column razorpay_order_id varchar(80) unique, add column razorpay_payment_id varchar(80) unique, add column amount_minor bigint not null default 0 check(amount_minor>=0), add column currency char(3) not null default 'INR', add column status varchar(24) not null default 'CREATED' check(status in ('CREATED','ORDER_CREATED','PAYMENT_PENDING','CAPTURED','FAILED','UNKNOWN')), add column provider_payload_safe jsonb not null default '{}'::jsonb, add column updated_at timestamptz not null default now(), add column verified_at timestamptz; alter table public.payment_attempts alter column amount_minor drop default,alter column currency drop default;
    alter table public.transactions add column payment_status varchar(24) not null default 'NOT_STARTED', add column active_payment_attempt_id uuid references public.payment_attempts(id);
    alter table public.transactions drop constraint transactions_status_check; alter table public.transactions add constraint transactions_status_check check(status in ('DRAFT','CART_READY','POLICY_CHECKING','AUTHORIZED','DENIED','REQUIRES_APPROVAL','CANCELLED','SUCCESS'));
    create unique index one_live_payment_attempt_per_transaction on public.payment_attempts(transaction_id) where status in ('CREATED','ORDER_CREATED','PAYMENT_PENDING','CAPTURED','UNKNOWN');
    create index payment_attempts_transaction_idx on public.payment_attempts(transaction_id,created_at desc);
    create table public.payment_provider_events (id uuid primary key default gen_random_uuid(), provider varchar(30) not null, provider_event_id char(64) not null, event_type varchar(80) not null, payment_attempt_id uuid references public.payment_attempts(id), payload_safe jsonb not null default '{}'::jsonb, processed_at timestamptz not null default now(), unique(provider,provider_event_id));
    alter table public.payment_provider_events enable row level security;
    create policy payment_attempts_own on public.payment_attempts for select to authenticated using(exists(select 1 from public.transactions t where t.id=payment_attempts.transaction_id and t.user_id=auth.uid()));
    create policy payment_events_own on public.payment_provider_events for select to authenticated using(exists(select 1 from public.payment_attempts pa join public.transactions t on t.id=pa.transaction_id where pa.id=payment_provider_events.payment_attempt_id and t.user_id=auth.uid()));
    create trigger payment_attempts_updated before update on public.payment_attempts for each row execute function public.set_updated_at();
    """)


def downgrade():
    op.execute(
        "drop table if exists public.payment_provider_events; alter table public.transactions drop column if exists active_payment_attempt_id,drop column if exists payment_status; alter table public.payment_attempts drop column if exists razorpay_order_id,drop column if exists razorpay_payment_id,drop column if exists amount_minor,drop column if exists currency,drop column if exists provider_payload_safe,drop column if exists updated_at,drop column if exists verified_at; alter table public.payment_attempts drop column status; alter table public.payment_attempts add column status varchar(24) not null default 'NOT_STARTED';"
    )
