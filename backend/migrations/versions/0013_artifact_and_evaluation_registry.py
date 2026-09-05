"""Register reproducible model, cryptographic and evaluation artifacts."""

from alembic import op

revision = "0013_artifact_registry"
down_revision = "0012_refund_adjusted_analytics"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        create table public.artifact_registry (
          id uuid primary key default gen_random_uuid(), artifact_key varchar(100) not null,
          version varchar(40) not null, artifact_type varchar(40) not null,
          sha256 char(64) not null, metadata jsonb not null default '{}'::jsonb,
          setup_class varchar(40) not null, active boolean not null default false,
          created_at timestamptz not null default now(), unique(artifact_key,version)
        );
        create unique index uq_active_artifact_key on public.artifact_registry(artifact_key) where active;
        create table public.evaluation_datasets (
          id uuid primary key default gen_random_uuid(), dataset_key varchar(100) not null,
          version varchar(40) not null, sha256 char(64) not null, row_count integer not null check(row_count>0),
          provenance varchar(100) not null, intended_use text not null,
          contains_personal_data boolean not null default false,
          created_at timestamptz not null default now(), unique(dataset_key,version)
        );
        create table public.benchmark_runs (
          id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id) on delete cascade,
          suite_version varchar(40) not null, results jsonb not null, passed_checks integer not null check(passed_checks>=0),
          total_checks integer not null check(total_checks>0), score_percent numeric(8,4) not null check(score_percent between 0 and 100),
          status varchar(16) not null check(status in ('PASS','PARTIAL','FAIL')),
          created_at timestamptz not null default now()
        );
        alter table public.artifact_registry enable row level security;
        alter table public.evaluation_datasets enable row level security;
        alter table public.benchmark_runs enable row level security;
        create policy artifact_registry_read on public.artifact_registry for select to authenticated using(true);
        create policy evaluation_datasets_read on public.evaluation_datasets for select to authenticated using(true);
        create policy benchmark_runs_owner_read on public.benchmark_runs for select to authenticated using(user_id=auth.uid());

        insert into public.artifact_registry(artifact_key,version,artifact_type,sha256,metadata,setup_class,active) values
        ('budget_sufficiency_circuit','1','CIRCOM_SOURCE','d7edcefa198073c42003b5a1e502446f2b2f04d70582ec8d9e8a2782e498fe74',
         jsonb_build_object('scheme','Groth16','claim','private_budget_gte_public_price','private_inputs',jsonb_build_array('privateBudget'),'public_inputs',jsonb_build_array('publicPrice')),
         'CONTROLLED_TEST_CEREMONY',true),
        ('budget_sufficiency_r1cs','1','R1CS','025bf4c14a249638261a371bb7f41db7f5221b535b9131e3ac2cb752fd3952d2',
         jsonb_build_object('curve','bn128'),'CONTROLLED_TEST_CEREMONY',true),
        ('budget_sufficiency_proving_key','1','GROTH16_ZKEY','386539e69130c43499471538b4c6d0bea1a5da258c77a769cfac707082c262fe',
         jsonb_build_object('curve','bn128','third_party_audited',false),'CONTROLLED_TEST_CEREMONY',true),
        ('budget_sufficiency_verification_key','1','GROTH16_VERIFICATION_KEY','d3a07b7828b2a62b8deb079063e69888de87564265cd60797d59e99ff55cff66',
         jsonb_build_object('curve','bn128','third_party_audited',false),'CONTROLLED_TEST_CEREMONY',true),
        ('negotiability_model','negotiability-v1','SKLEARN_JOBLIB','b97cc657a3a73aff3419f227b949f6d2a39bf943764dfab0bcb04c60c267e2cb',
         jsonb_build_object('algorithm','LogisticRegression','training_rows',180,'evaluation_rows',60,'f1',0.622951,'roc_auc',0.68),
         'REPRODUCIBLE_CONTROLLED_DATASET',true);

        insert into public.evaluation_datasets(dataset_key,version,sha256,row_count,provenance,intended_use) values
        ('negotiability_controlled','1','64fb0f93a2a3b2859302938bff5921e4af97d8fe837cb9f1192235f4c0d9cb4c',240,
         'DETERMINISTIC_SYNTHETIC_SEED_4207','Negotiability classification evaluation only');

        insert into public.negotiability_models(version,algorithm,feature_schema,metrics,training_provenance,artifact_sha256,active)
        values('negotiability-v1','sklearn.linear_model.LogisticRegression',
        jsonb_build_object('categorical',jsonb_build_array('platform','seller_type','category'),'numeric',jsonb_build_array('listing_age_days','explicit_negotiable','rfq_supported','quantity','historical_price_edits','price_roundness','merchant_negotiation_enabled')),
        jsonb_build_object('precision',0.612903,'recall',0.633333,'f1',0.622951,'roc_auc',0.68,'brier_score',0.246527,'training_rows',180,'evaluation_rows',60),
        'DETERMINISTIC_CONTROLLED_DATASET','b97cc657a3a73aff3419f227b949f6d2a39bf943764dfab0bcb04c60c267e2cb',true)
        on conflict(version) do update set metrics=excluded.metrics,artifact_sha256=excluded.artifact_sha256,active=true;
        """
    )


def downgrade():
    op.execute("delete from public.negotiability_models where version='negotiability-v1'")
    op.execute(
        "drop table if exists public.benchmark_runs,public.evaluation_datasets,public.artifact_registry cascade"
    )
