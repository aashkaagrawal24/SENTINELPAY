"""Bulk Agentic Commerce — bulk_rfqs, bulk_negotiations, bulk_negotiation_events,
inventory_reservations, bulk_policy_rules + non-breaking column extensions.

Revision ID: 0016_bulk_commerce
Revises: 0015_market_demand
"""

from alembic import op

revision = "0016_bulk_commerce"
down_revision = "0015_market_demand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        -- ── 1. Non-breaking columns on existing tables ──────────────────────
        ALTER TABLE public.transactions
            ADD COLUMN IF NOT EXISTS order_type VARCHAR(16) NOT NULL DEFAULT 'RETAIL'
                CHECK (order_type IN ('RETAIL','BULK')),
            ADD COLUMN IF NOT EXISTS bulk_rfq_id UUID;

        ALTER TABLE public.merchant_products
            ADD COLUMN IF NOT EXISTS bulk_enabled       BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS bulk_min_quantity  INTEGER NOT NULL DEFAULT 50,
            ADD COLUMN IF NOT EXISTS bulk_max_quantity  INTEGER;

        ALTER TABLE public.merchant_inventory
            ADD COLUMN IF NOT EXISTS bulk_reserved_quantity INTEGER NOT NULL DEFAULT 0
                CHECK (bulk_reserved_quantity >= 0);

        ALTER TABLE public.revenue_ledger
            ADD COLUMN IF NOT EXISTS order_type VARCHAR(16) NOT NULL DEFAULT 'RETAIL';

        -- ── 2. bulk_rfqs ─────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS public.bulk_rfqs (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            buyer_user_id           UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
            merchant_id             UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
            product_id              UUID NOT NULL REFERENCES public.merchant_products(id) ON DELETE CASCADE,
            requested_quantity      INTEGER NOT NULL CHECK (requested_quantity > 0),
            required_by             DATE,
            delivery_mode           VARCHAR(40) NOT NULL DEFAULT 'SINGLE',
            allow_substitutes       BOOLEAN NOT NULL DEFAULT FALSE,
            negotiation_enabled     BOOLEAN NOT NULL DEFAULT TRUE,
            split_delivery          BOOLEAN NOT NULL DEFAULT FALSE,
            -- buyer-private: NEVER returned in merchant-facing responses
            private_max_budget_minor BIGINT,
            private_target_unit_price_minor BIGINT,
            status                  VARCHAR(32) NOT NULL DEFAULT 'CREATED'
                CHECK (status IN ('CREATED','SUBMITTED','UNDER_REVIEW','QUOTED','NEGOTIATING',
                                  'ACCEPTED','REJECTED','EXPIRED','CONVERTED_TO_ORDER')),
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at              TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '24 hours',
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_bulk_rfqs_merchant ON public.bulk_rfqs(merchant_id, status);
        CREATE INDEX IF NOT EXISTS idx_bulk_rfqs_buyer ON public.bulk_rfqs(buyer_user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_bulk_rfqs_product ON public.bulk_rfqs(product_id);

        -- ── 3. bulk_negotiations ─────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS public.bulk_negotiations (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            rfq_id      UUID NOT NULL UNIQUE REFERENCES public.bulk_rfqs(id) ON DELETE CASCADE,
            status      VARCHAR(32) NOT NULL DEFAULT 'STARTED'
                CHECK (status IN ('STARTED','OFFER_MADE','COUNTERED','ACCEPTED','REJECTED','EXPIRED')),
            final_unit_price_minor  BIGINT,
            final_quantity          INTEGER,
            final_total_minor       BIGINT,
            rounds                  INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_bulk_neg_rfq ON public.bulk_negotiations(rfq_id);

        -- ── 4. bulk_negotiation_events ────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS public.bulk_negotiation_events (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            negotiation_id      UUID NOT NULL REFERENCES public.bulk_negotiations(id) ON DELETE CASCADE,
            rfq_id              UUID NOT NULL REFERENCES public.bulk_rfqs(id) ON DELETE CASCADE,
            sequence            INTEGER NOT NULL,
            actor               VARCHAR(20) NOT NULL CHECK (actor IN ('BUYER_AGENT','MERCHANT_AGENT','SYSTEM')),
            offer_type          VARCHAR(20) NOT NULL
                CHECK (offer_type IN ('REQUEST','QUOTE','COUNTER','ACCEPT','REJECT','SYSTEM_EVENT')),
            quantity            INTEGER,
            unit_price_minor    BIGINT,
            total_value_minor   BIGINT,
            message             TEXT,
            -- merchant-private fields intentionally EXCLUDED from this table
            -- buyer-private fields intentionally EXCLUDED from this table
            metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (negotiation_id, sequence)
        );

        CREATE INDEX IF NOT EXISTS idx_bulk_neg_events_neg ON public.bulk_negotiation_events(negotiation_id, sequence);

        -- ── 5. inventory_reservations ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS public.inventory_reservations (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            product_id      UUID NOT NULL REFERENCES public.merchant_products(id) ON DELETE CASCADE,
            merchant_id     UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
            rfq_id          UUID REFERENCES public.bulk_rfqs(id) ON DELETE SET NULL,
            negotiation_id  UUID REFERENCES public.bulk_negotiations(id) ON DELETE SET NULL,
            transaction_id  UUID REFERENCES public.transactions(id) ON DELETE SET NULL,
            order_id        UUID,   -- filled when payment captured
            quantity        INTEGER NOT NULL CHECK (quantity > 0),
            status          VARCHAR(16) NOT NULL DEFAULT 'ACTIVE'
                CHECK (status IN ('ACTIVE','CONVERTED','RELEASED','EXPIRED')),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at      TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '15 minutes',
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_inv_res_product ON public.inventory_reservations(product_id, status);
        CREATE INDEX IF NOT EXISTS idx_inv_res_rfq ON public.inventory_reservations(rfq_id);

        -- ── 6. bulk_policy_rules ──────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS public.bulk_policy_rules (
            id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            merchant_id                     UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
            product_id                      UUID REFERENCES public.merchant_products(id) ON DELETE CASCADE,
            -- quantity tiers
            min_quantity                    INTEGER NOT NULL DEFAULT 1,
            max_quantity                    INTEGER,
            -- economics
            max_discount_percent            NUMERIC(5,2) NOT NULL DEFAULT 10.0,
            min_margin_percent              NUMERIC(5,2) NOT NULL DEFAULT 15.0,
            max_autonomous_order_value_minor BIGINT NOT NULL DEFAULT 10000000,  -- ₹100,000
            max_inventory_allocation_percent NUMERIC(5,2) NOT NULL DEFAULT 60.0,
            reservation_duration_minutes    INTEGER NOT NULL DEFAULT 15,
            -- AI recommendation
            ai_recommended                  BOOLEAN NOT NULL DEFAULT FALSE,
            ai_reasoning                    TEXT,
            ai_recommended_at               TIMESTAMPTZ,
            -- lifecycle
            status                          VARCHAR(16) NOT NULL DEFAULT 'DRAFT'
                CHECK (status IN ('DRAFT','ACTIVE','EXPIRED','REJECTED')),
            approved_by_merchant            BOOLEAN NOT NULL DEFAULT FALSE,
            created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                      TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_bulk_policy_merchant ON public.bulk_policy_rules(merchant_id, status);
        CREATE INDEX IF NOT EXISTS idx_bulk_policy_product ON public.bulk_policy_rules(product_id, status);

        -- ── 7. FK from transactions.bulk_rfq_id → bulk_rfqs ──────────────────
        -- Add after bulk_rfqs exists
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'transactions_bulk_rfq_id_fk'
            ) THEN
                ALTER TABLE public.transactions
                    ADD CONSTRAINT transactions_bulk_rfq_id_fk
                    FOREIGN KEY (bulk_rfq_id) REFERENCES public.bulk_rfqs(id) ON DELETE SET NULL;
            END IF;
        END $$;

        -- ── 8. Enable RLS on new tables ───────────────────────────────────────
        ALTER TABLE public.bulk_rfqs ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.bulk_negotiations ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.bulk_negotiation_events ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.inventory_reservations ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.bulk_policy_rules ENABLE ROW LEVEL SECURITY;

        -- Basic RLS policies (bypass for service role used by FastAPI)
        CREATE POLICY bulk_rfqs_buyer ON public.bulk_rfqs FOR ALL TO authenticated
            USING (buyer_user_id = auth.uid());
        CREATE POLICY bulk_rfqs_merchant ON public.bulk_rfqs FOR SELECT TO authenticated
            USING (EXISTS (
                SELECT 1 FROM public.merchant_users mu
                WHERE mu.merchant_id = bulk_rfqs.merchant_id AND mu.user_id = auth.uid()
            ));
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS public.bulk_policy_rules CASCADE;
        DROP TABLE IF EXISTS public.inventory_reservations CASCADE;
        DROP TABLE IF EXISTS public.bulk_negotiation_events CASCADE;
        DROP TABLE IF EXISTS public.bulk_negotiations CASCADE;
        DROP TABLE IF EXISTS public.bulk_rfqs CASCADE;

        ALTER TABLE public.transactions
            DROP COLUMN IF EXISTS order_type,
            DROP COLUMN IF EXISTS bulk_rfq_id;

        ALTER TABLE public.merchant_products
            DROP COLUMN IF EXISTS bulk_enabled,
            DROP COLUMN IF EXISTS bulk_min_quantity,
            DROP COLUMN IF EXISTS bulk_max_quantity;

        ALTER TABLE public.merchant_inventory
            DROP COLUMN IF EXISTS bulk_reserved_quantity;

        ALTER TABLE public.revenue_ledger
            DROP COLUMN IF EXISTS order_type;
    """)
