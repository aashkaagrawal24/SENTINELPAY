"""Add explicit refund-adjusted merchant revenue metrics."""

from alembic import op

revision = "0012_refund_adjusted_analytics"
down_revision = "0011_complete_advanced_stack"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        alter table public.merchant_metrics add column processed_refunds_minor bigint not null default 0
          check(processed_refunds_minor>=0);
        alter table public.merchant_metrics add column net_revenue_minor bigint not null default 0;
        """
    )


def downgrade():
    op.execute(
        """
        alter table public.merchant_metrics drop column if exists net_revenue_minor;
        alter table public.merchant_metrics drop column if exists processed_refunds_minor;
        """
    )
