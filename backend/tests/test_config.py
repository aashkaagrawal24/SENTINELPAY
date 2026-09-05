import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_missing_config_fails(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
