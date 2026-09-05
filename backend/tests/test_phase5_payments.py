import json
from dataclasses import replace
from uuid import UUID, uuid4

import httpx
import pytest

from app.schemas.payment import PaymentStatus
from app.services.payment_service import (
    PaymentAttemptClaim,
    PaymentAttemptRecord,
    PaymentContext,
    PaymentService,
    PaymentStateMachine,
)
from app.services.security_kernel import cart_commitment


def sample_cart():
    return {
        "merchant_id": "m",
        "mandate_id": "x",
        "currency": "INR",
        "subtotal_minor": 1_999_900,
        "discount_minor": 0,
        "shipping_minor": 0,
        "total_minor": 1_999_900,
        "delivery": {},
        "version": 1,
        "items": [{"product_id": "p", "quantity": 1, "unit_price_minor": 1_999_900}],
    }


class FakeRepository:
    def __init__(self, context: PaymentContext):
        self.context, self.attempts, self.events = context, {}, set()
        self.orders_created = 0
        self.capture_effects = 0

    def lock_context(self, transaction_id):
        return self.context

    def reusable_attempt(self, transaction_id, key):
        return next(
            (
                a
                for a in self.attempts.values()
                if a.transaction_id == transaction_id
                and (
                    a.idempotency_key == key
                    or a.status
                    in {
                        PaymentStatus.CREATED,
                        PaymentStatus.ORDER_CREATED,
                        PaymentStatus.PAYMENT_PENDING,
                        PaymentStatus.CAPTURED,
                        PaymentStatus.UNKNOWN,
                    }
                )
            ),
            None,
        )

    def create_attempt(self, context, key):
        attempt = PaymentAttemptRecord(
            uuid4(),
            context.transaction_id,
            key,
            context.cart["total_minor"],
            context.cart["currency"],
            PaymentStatus.CREATED,
        )
        self.attempts[attempt.id] = attempt
        return PaymentAttemptClaim(attempt, True)

    def set_order(self, attempt_id, order_id, safe_payload):
        current = self.attempts[attempt_id]
        PaymentStateMachine.ensure(current.status, PaymentStatus.ORDER_CREATED)
        updated = replace(current, status=PaymentStatus.ORDER_CREATED, razorpay_order_id=order_id)
        self.attempts[attempt_id] = updated
        self.orders_created += 1
        return updated

    def transition(self, attempt_id, target, payment_id=None, safe_payload=None):
        current = self.attempts[attempt_id]
        PaymentStateMachine.ensure(current.status, target)
        updated = replace(
            current, status=target, razorpay_payment_id=payment_id or current.razorpay_payment_id
        )
        self.attempts[attempt_id] = updated
        return updated

    def capture_once(self, attempt_id, payment_id, safe_payload):
        current = self.attempts[attempt_id]
        if current.status == PaymentStatus.CAPTURED:
            return current
        PaymentStateMachine.ensure(current.status, PaymentStatus.CAPTURED)
        updated = replace(current, status=PaymentStatus.CAPTURED, razorpay_payment_id=payment_id)
        self.attempts[attempt_id] = updated
        self.capture_effects += 1
        return updated

    def get_attempt(self, attempt_id):
        return self.attempts[attempt_id]

    def get_attempt_by_order(self, order_id):
        return next((a for a in self.attempts.values() if a.razorpay_order_id == order_id), None)

    def record_event_once(self, event_id, event_type, attempt_id, safe_payload):
        if event_id in self.events:
            return False
        self.events.add(event_id)
        return True

    def commit(self):
        return None


class FakeProvider:
    public_key_id = "rzp_test_public"

    def __init__(self, status="authorized", fail_create=False):
        self.status, self.fail_create, self.calls = status, fail_create, 0

    def create_order(self, amount_minor, currency, receipt):
        self.calls += 1
        if self.fail_create:
            raise httpx.ReadTimeout("uncertain")
        return {
            "id": "order_test_1",
            "amount": amount_minor,
            "currency": currency,
            "status": "created",
        }

    def fetch_payment(self, payment_id):
        return {
            "id": payment_id,
            "order_id": "order_test_1",
            "amount": 1_999_900,
            "currency": "INR",
            "status": self.status,
            "captured": self.status == "captured",
        }

    def fetch_order_payments(self, order_id):
        return [
            {
                "id": "pay_resolved",
                "order_id": order_id,
                "amount": 1_999_900,
                "currency": "INR",
                "status": self.status,
            }
        ]

    def verify_callback(self, order_id, payment_id, signature):
        return signature == "valid"

    def verify_webhook(self, raw_body, signature):
        return signature == "valid"


def context(**changes):
    cart = sample_cart()
    values = {
        "transaction_id": UUID("10000000-0000-0000-0000-000000000001"),
        "transaction_status": "AUTHORIZED",
        "human_confirmed": True,
        "mandate_id": UUID("20000000-0000-0000-0000-000000000001"),
        "mandate_status": "ACTIVE",
        "execution_count": 0,
        "max_executions": 1,
        "cart": cart,
        "approved_hash": cart_commitment(cart),
        "security_fresh": True,
    }
    values.update(changes)
    return PaymentContext(**values)


def prepared(status="authorized"):
    repo = FakeRepository(context())
    provider = FakeProvider(status)
    service = PaymentService(repo, provider)
    checkout = service.create_order(repo.context.transaction_id, "key-1")
    return repo, provider, service, checkout


def test_refuses_without_security_allow_and_detects_cart_mutation():
    for ctx in (
        context(transaction_status="DENIED"),
        context(approved_hash="bad"),
        context(security_fresh=False),
    ):
        with pytest.raises(PermissionError):
            PaymentService(FakeRepository(ctx), FakeProvider()).create_order(
                ctx.transaction_id, "key"
            )


def test_exact_amount_and_duplicate_order_are_idempotent():
    repo, provider, service, first = prepared()
    second = service.create_order(repo.context.transaction_id, "key-1")
    assert first.order_id == second.order_id and provider.calls == 1 and repo.orders_created == 1
    assert first.amount_minor == repo.context.cart["total_minor"]


def test_callback_signature_required_and_callback_not_final_truth():
    repo, _provider, service, checkout = prepared("authorized")
    with pytest.raises(PermissionError):
        service.verify_browser_callback(
            checkout.payment_attempt_id, checkout.order_id, "pay_1", "invalid"
        )
    result = service.verify_browser_callback(
        checkout.payment_attempt_id, checkout.order_id, "pay_1", "valid"
    )
    assert result.status == PaymentStatus.PAYMENT_PENDING and repo.capture_effects == 0


def test_trusted_capture_consumes_exactly_once():
    repo, _provider, service, checkout = prepared("captured")
    first = service.verify_browser_callback(
        checkout.payment_attempt_id, checkout.order_id, "pay_1", "valid"
    )
    assert first.status == PaymentStatus.CAPTURED and repo.capture_effects == 1
    webhook = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_1",
                    "order_id": "order_test_1",
                    "amount": 1_999_900,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    service.process_webhook(json.dumps(webhook).encode(), "valid")
    service.process_webhook(json.dumps(webhook).encode(), "valid")
    late_failure = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_1",
                    "order_id": "order_test_1",
                    "amount": 1_999_900,
                    "currency": "INR",
                    "status": "failed",
                }
            }
        },
    }
    service.process_webhook(json.dumps(late_failure).encode(), "valid")
    assert repo.capture_effects == 1
    assert repo.get_attempt(checkout.payment_attempt_id).status == PaymentStatus.CAPTURED


def test_invalid_webhook_and_out_of_order_regression_blocked():
    repo, _provider, service, checkout = prepared("captured")
    with pytest.raises(PermissionError):
        service.process_webhook(b"{}", "invalid")
    service.verify_browser_callback(
        checkout.payment_attempt_id, checkout.order_id, "pay_1", "valid"
    )
    with pytest.raises(ValueError):
        repo.transition(checkout.payment_attempt_id, PaymentStatus.PAYMENT_PENDING)


def test_unknown_never_auto_retries_and_failed_allows_new_key():
    ctx = context()
    repo = FakeRepository(ctx)
    provider = FakeProvider(fail_create=True)
    service = PaymentService(repo, provider)
    with pytest.raises(httpx.ReadTimeout):
        service.create_order(ctx.transaction_id, "key-1")
    with pytest.raises(ValueError, match="UNKNOWN"):
        service.create_order(ctx.transaction_id, "key-2")
    assert provider.calls == 1
    failed_repo, failed_provider, failed_service, checkout = prepared("failed")
    failed_service.verify_browser_callback(
        checkout.payment_attempt_id, checkout.order_id, "pay_2", "valid"
    )
    retry = failed_service.create_order(failed_repo.context.transaction_id, "key-2")
    assert retry.order_id == "order_test_1" and failed_provider.calls == 2


def test_unknown_reconciles_existing_order_without_new_order():
    repo, provider, service, checkout = prepared("captured")
    repo.transition(checkout.payment_attempt_id, PaymentStatus.UNKNOWN)
    resolved = service.resolve_unknown(checkout.payment_attempt_id)
    assert resolved.status == PaymentStatus.CAPTURED
    assert provider.calls == 1 and repo.capture_effects == 1
