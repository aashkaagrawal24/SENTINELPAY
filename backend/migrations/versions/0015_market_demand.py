"""market_demand table for tracking missed buyer searches

Revision ID: 0015_market_demand
Revises: 0014_bind_security_evidence
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_market_demand"
down_revision = "0014_bind_security_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS market_demand (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            product_query   TEXT NOT NULL,
            estimated_price_minor BIGINT,
            currency        VARCHAR(3) NOT NULL DEFAULT 'INR',
            merchant_id     UUID REFERENCES merchants(id) ON DELETE CASCADE,
            search_count    INTEGER NOT NULL DEFAULT 1,
            last_searched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_market_demand_query_merchant UNIQUE (product_query, merchant_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_market_demand_merchant ON market_demand(merchant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_market_demand_search_count ON market_demand(search_count DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS market_demand")
