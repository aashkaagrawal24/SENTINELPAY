from uuid import UUID

import httpx
import pytest

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.db.session import get_db_session
from app.main import app


@pytest.mark.anyio
async def test_health():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Correlation-ID": "test-id"})
    assert response.status_code == 200 and response.json()["correlation_id"] == "test-id"


@pytest.mark.anyio
async def test_me_requires_auth():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/me")).status_code == 401


@pytest.mark.anyio
async def test_me_mocked_identity():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        UUID("00000000-0000-0000-0000-000000000001"), "buyer@example.com"
    )
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/api/me")).json()["email"] == "buyer@example.com"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_ready_checks_database():
    class FakeDb:
        def execute(self, _statement):
            return 1

    app.dependency_overrides[get_db_session] = lambda: FakeDb()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/ready")).json()["status"] == "ready"
    finally:
        app.dependency_overrides.clear()
