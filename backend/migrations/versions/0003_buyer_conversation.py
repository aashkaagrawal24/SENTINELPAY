"""Buyer intent, mandates, agent sessions and conversations."""

from alembic import op

revision = "0003_buyer_conversation"
down_revision = "0002_merchant_commerce"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    alter table public.agent_sessions add column mandate_id uuid references public.mandates(id) on delete set null, add column status varchar(20) not null default 'ACTIVE', add column started_at timestamptz not null default now(), add column ended_at timestamptz, add column converted boolean not null default false, add column transaction_id uuid, add column metadata jsonb not null default '{}'::jsonb;
    alter table public.intents add column raw_text text not null default '', add column parsed_payload jsonb not null default '{}'::jsonb, add column parser_provider varchar(50), add column parser_model varchar(100), add column parser_version varchar(50), add column parser_confidence numeric(5,4), add column schema_version varchar(20) not null default '1.0';
    alter table public.mandates add column intent_id uuid references public.intents(id), add column product_scope jsonb not null default '{}'::jsonb, add column max_total_amount_minor bigint, add column currency char(3) not null default 'INR', add column max_quantity integer not null default 1, add column allowed_conditions jsonb not null default '[]'::jsonb, add column preferred_brands jsonb not null default '[]'::jsonb, add column excluded_brands jsonb not null default '[]'::jsonb, add column seller_scope jsonb not null default '{}'::jsonb, add column delivery_deadline timestamptz, add column negotiation_allowed boolean not null default false, add column upsell_allowed boolean not null default false, add column cross_sell_allowed boolean not null default false, add column campaign_offer_allowed boolean not null default false, add column auto_purchase_allowed boolean not null default false, add column expires_at timestamptz not null default (now() + interval '1 hour'), add column nonce uuid not null default gen_random_uuid(), add column execution_count integer not null default 0, add column max_executions integer not null default 1, add column status varchar(16) not null default 'ACTIVE', add column integrity_hash char(64) not null default repeat('0',64), add constraint mandates_nonce_unique unique(nonce), add constraint mandates_status_check check(status in ('ACTIVE','CONSUMED','EXPIRED','REVOKED','CANCELLED'));
    create table public.conversation_threads (id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade, agent_session_id uuid references public.agent_sessions(id) on delete set null, created_at timestamptz not null default now(), updated_at timestamptz not null default now());
    create table public.conversation_messages (id uuid primary key default gen_random_uuid(), thread_id uuid not null references public.conversation_threads(id) on delete cascade, role varchar(20) not null check(role in ('USER','ASSISTANT','SYSTEM')), content text not null, payload jsonb not null default '{}'::jsonb, source_category varchar(30) not null default 'USER_INPUT', created_at timestamptz not null default now());
    alter table public.conversation_threads enable row level security; alter table public.conversation_messages enable row level security;
    create policy conversation_own on public.conversation_threads for all to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid()); create policy messages_own on public.conversation_messages for all to authenticated using(exists(select 1 from public.conversation_threads t where t.id=conversation_messages.thread_id and t.user_id=auth.uid())) with check(exists(select 1 from public.conversation_threads t where t.id=conversation_messages.thread_id and t.user_id=auth.uid()));
    create or replace function public.prevent_mandate_authority_mutation() returns trigger language plpgsql as $$ begin if old.status='ACTIVE' and (new.max_total_amount_minor,new.currency,new.max_quantity,new.product_scope,new.allowed_conditions,new.preferred_brands,new.excluded_brands,new.seller_scope,new.delivery_deadline,new.negotiation_allowed,new.upsell_allowed,new.cross_sell_allowed,new.campaign_offer_allowed,new.auto_purchase_allowed,new.expires_at,new.nonce,new.max_executions) is distinct from (old.max_total_amount_minor,old.currency,old.max_quantity,old.product_scope,old.allowed_conditions,old.preferred_brands,old.excluded_brands,old.seller_scope,old.delivery_deadline,old.negotiation_allowed,old.upsell_allowed,old.cross_sell_allowed,old.campaign_offer_allowed,old.auto_purchase_allowed,old.expires_at,old.nonce,old.max_executions) then raise exception 'Active mandate authority is immutable'; end if; return new; end; $$;
    create trigger mandate_immutable before update on public.mandates for each row execute function public.prevent_mandate_authority_mutation();
    """)


def downgrade():
    op.execute(
        "drop table if exists public.conversation_messages,public.conversation_threads cascade; drop function if exists public.prevent_mandate_authority_mutation cascade;"
    )
