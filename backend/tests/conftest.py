import os
from dotenv import load_dotenv
import pytest

load_dotenv() # Load from .env if present

# Ensure variables exist in case .env is missing
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon")
os.environ.setdefault("SUPABASE_DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test")
os.environ.setdefault("SUPABASE_SERVER_SECRET", "test-secret")


@pytest.fixture
def anyio_backend():
    return "asyncio"
