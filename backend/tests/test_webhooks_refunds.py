import json
from uuid import uuid4
import httpx
import pytest

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.core.config import Settings, get_settings
from app.main import app as fastapi_app
from app.schemas.payment import PaymentStatus, RefundStatus
import app.api.payment_routes

# We will mock the `payment_service` function in `payment_routes.py` directly for E2E testing
# to avoid database setup issues, focusing on the endpoints, HTTP status codes, and JSON mappings.

class MockPaymentService:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        
    def process_webhook(self, raw_body, signature):
        if self.should_fail:
            raise PermissionError("Invalid signature")
        from app.db.payment_repository import PaymentAttemptRecord
        return PaymentAttemptRecord(
            id=uuid4(),
            transaction_id=uuid4(),
            idempotency_key="mock",
            amount_minor=1000,
            currency="INR",
            status=PaymentStatus.CAPTURED
        )

    def create_refund(self, attempt_id, user_id, amount, reason, idempotency_key):
        if self.should_fail:
            raise ValueError("Refund exceeds amount")
        from app.services.payment_service import RefundRecord
        return RefundRecord(
            id=uuid4(),
            payment_attempt_id=attempt_id,
            amount_minor=amount,
            currency="INR",
            idempotency_key=idempotency_key,
            status=RefundStatus.REQUESTED,
            provider_refund_id=None
        )

    def reconcile_refund(self, refund_id):
        from app.services.payment_service import RefundRecord
        return RefundRecord(
            id=refund_id,
            payment_attempt_id=uuid4(),
            amount_minor=1000,
            currency="INR",
            idempotency_key="key",
            status=RefundStatus.PROCESSED,
            provider_refund_id="prov_123"
        )

    def reconcile_payment(self, attempt_id):
        from app.db.payment_repository import PaymentAttemptRecord
        return PaymentAttemptRecord(
            id=attempt_id,
            transaction_id=uuid4(),
            idempotency_key="mock",
            amount_minor=1000,
            currency="INR",
            status=PaymentStatus.UNKNOWN
        )


class MockDb:
    def execute(self, stmt, params=None):
        class Result:
            def scalar(self): return True
            def mappings(self):
                class Mappings:
                    def one(self):
                        return {
                            "id": params.get("id") if params else uuid4(),
                            "transaction_id": uuid4(),
                            "status": "CAPTURED",
                            "provider_order_id": "order_123",
                            "amount_minor": 1000,
                            "created_at": "2024-01-01T00:00:00Z"
                        }
                    def one_or_none(self):
                        return None
                return Mappings()
        return Result()
    def commit(self):
        pass


@pytest.fixture
def mock_payment_service(monkeypatch):
    from app.db.payment_repository import SqlPaymentRepository, PaymentAttemptRecord
    from datetime import datetime

    def mock_get_attempt(self, attempt_id):
        return PaymentAttemptRecord(
            id=attempt_id,
            transaction_id=uuid4(),
            idempotency_key="mock",
            amount_minor=1000,
            currency="INR",
            status=PaymentStatus.CAPTURED,
            razorpay_order_id="order_123",
            razorpay_payment_id="pay_123"
        )
    
    monkeypatch.setattr(SqlPaymentRepository, "get_attempt", mock_get_attempt)
    def _mock_service(db, settings, require_webhook=False):
        if not settings.razorpay_test_key_id or not settings.razorpay_test_key_secret:
            from fastapi import HTTPException
            raise HTTPException(503, "Razorpay Test Mode credentials are not configured")
        if require_webhook and not settings.razorpay_webhook_secret:
            from fastapi import HTTPException
            raise HTTPException(503, "Razorpay webhook secret is not configured")
        return MockPaymentService(should_fail=getattr(settings, "mock_should_fail", False))
    
    monkeypatch.setattr(app.api.payment_routes, "payment_service", _mock_service)


@pytest.mark.anyio
async def test_webhook_fails_without_deployment_secret(mock_payment_service):
    settings = Settings(
        razorpay_test_key_id="test", 
        razorpay_test_key_secret="test", 
        razorpay_webhook_secret=None
    )
    fastapi_app.dependency_overrides[get_settings] = lambda: settings
    
    try:
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/webhooks/razorpay", 
                headers={"x-razorpay-signature": "test"}
            )
        assert response.status_code == 503
        assert "webhook secret is not configured" in response.json()["detail"]
    finally:
        fastapi_app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_webhook_success_with_secret(mock_payment_service):
    settings = Settings(
        razorpay_test_key_id="test", 
        razorpay_test_key_secret="test", 
        razorpay_webhook_secret="secret"
    )
    fastapi_app.dependency_overrides[get_settings] = lambda: settings
    
    try:
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/webhooks/razorpay", 
                headers={"x-razorpay-signature": "test"},
                json={"event": "payment.captured"}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is True
        assert data["status"] == "CAPTURED"
        assert data["payment_attempt_id"] is not None
    finally:
        fastapi_app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_refund_endpoints(mock_payment_service):
    user = AuthenticatedUser(uuid4(), "test@test.com")
    settings = Settings(razorpay_test_key_id="test", razorpay_test_key_secret="test")
    
    from app.db.session import get_db_session
    fastapi_app.dependency_overrides[get_current_user] = lambda: user
    fastapi_app.dependency_overrides[get_settings] = lambda: settings
    fastapi_app.dependency_overrides[get_db_session] = lambda: MockDb()
    
    try:
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Test POST /api/payments/refunds
            attempt_id = str(uuid4())
            response = await client.post(
                "/api/payments/refunds",
                json={
                    "payment_attempt_id": attempt_id,
                    "amount_minor": 1000,
                    "reason": "Customer request",
                    "idempotency_key": "refund-123"
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "REQUESTED"
            
            # Test GET /api/payments/refunds/{refund_id}
            refund_id = data["id"]
            response = await client.get(f"/api/payments/refunds/{refund_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "PROCESSED"
            assert data["provider_refund_id"] == "prov_123"
            
            # Test POST /api/payments/{attempt_id}/reconcile
            response = await client.post(f"/api/payments/{attempt_id}/reconcile")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "UNKNOWN"
            assert data["resolution"] == "MANUAL_REVIEW"
    finally:
        fastapi_app.dependency_overrides.clear()

