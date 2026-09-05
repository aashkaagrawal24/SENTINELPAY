from pathlib import Path


def test_rls_enabled_for_phase_1_to_4_tables():
    migration_dir = Path(__file__).parents[1] / "migrations" / "versions"
    sql = "\n".join(path.read_text() for path in migration_dir.glob("*.py"))
    tables = [
        "profiles",
        "merchants",
        "merchant_products",
        "merchant_policies",
        "mandates",
        "conversation_threads",
        "carts",
        "transactions",
        "policy_evaluations",
    ]
    for table in tables:
        assert f"alter table public.{table} enable row level security" in sql


def test_frontend_source_contains_no_backend_secret_names():
    frontend = Path(__file__).parents[2] / "frontend" / "web"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in frontend.rglob("*.ts*")
        if "node_modules" not in path.parts and ".next" not in path.parts
    )
    for secret in (
        "SUPABASE_SERVER_SECRET",
        "RAZORPAY_TEST_KEY_SECRET",
        "GROQ_API_KEY",
        "NVIDIA_NIM_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        assert secret not in source
