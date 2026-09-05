"""Bind ZK and BLS authorization evidence to an exact user and cart."""

from alembic import op

revision = "0014_bind_security_evidence"
down_revision = "0013_artifact_registry"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        alter table public.zk_budget_proofs
          add column user_cart_id uuid references public.carts(id) on delete cascade,
          add column authority_scope varchar(32) not null default 'EVALUATION_ONLY'
          check(authority_scope in ('EVALUATION_ONLY','SECURITY_KERNEL_INPUT'));
        create index ix_zk_proof_authority_binding on public.zk_budget_proofs(user_id,user_cart_id,mandate_id,public_price_minor)
          where authority_scope='SECURITY_KERNEL_INPUT' and verified;

        alter table public.bls_approval_runs
          add column user_id uuid references public.profiles(id) on delete cascade,
          add column user_cart_id uuid references public.carts(id) on delete cascade,
          add column authority_scope varchar(32) not null default 'EVALUATION_ONLY'
          check(authority_scope in ('EVALUATION_ONLY','SECURITY_KERNEL_INPUT')),
          add column key_source varchar(48) not null default 'CALLER_SUPPLIED_EVALUATION_KEYS',
          add column verifier_decisions jsonb not null default '[]'::jsonb;
        create index ix_bls_authority_binding on public.bls_approval_runs(user_id,user_cart_id,payload_hash)
          where authority_scope='SECURITY_KERNEL_INPUT' and aggregate_valid;
        create policy bls_approval_owner_read on public.bls_approval_runs for select to authenticated using(user_id=auth.uid());
        """
    )


def downgrade():
    op.execute("drop policy if exists bls_approval_owner_read on public.bls_approval_runs")
    op.execute("drop index if exists public.ix_bls_authority_binding")
    op.execute(
        """alter table public.bls_approval_runs
        drop column if exists verifier_decisions,drop column if exists key_source,
        drop column if exists authority_scope,drop column if exists user_cart_id,drop column if exists user_id"""
    )
    op.execute("drop index if exists public.ix_zk_proof_authority_binding")
    op.execute(
        "alter table public.zk_budget_proofs drop column if exists authority_scope,drop column if exists user_cart_id"
    )
