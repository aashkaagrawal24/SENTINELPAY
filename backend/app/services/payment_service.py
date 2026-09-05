import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol
from uuid import UUID

import httpx

from app.schemas.payment import CheckoutData, PaymentStatus, RefundStatus
from app.services.security_kernel import SecurityKernel


class PaymentStateMachine:
    ALLOWED: ClassVar[dict[PaymentStatus, set[PaymentStatus]]] = {
        PaymentStatus.CREATED: {
            PaymentStatus.ORDER_CREATED,
            PaymentStatus.FAILED,
            PaymentStatus.UNKNOWN,
        },
        PaymentStatus.ORDER_CREATED: {
            PaymentStatus.PAYMENT_PENDING,
            PaymentStatus.FAILED,
            PaymentStatus.UNKNOWN,
        },
        PaymentStatus.PAYMENT_PENDING: {
            PaymentStatus.CAPTURED,
            PaymentStatus.FAILED,
            PaymentStatus.UNKNOWN,
        },
        PaymentStatus.UNKNOWN: {
            PaymentStatus.PAYMENT_PENDING,
            PaymentStatus.CAPTURED,
            PaymentStatus.FAILED,
        },
        PaymentStatus.FAILED: set(),
        PaymentStatus.CAPTURED: set(),
    }

    @classmethod
    def ensure(cls, current: PaymentStatus, target: PaymentStatus) -> None:
        if current == target:
            return
        if target not in cls.ALLOWED[current]:
            raise ValueError(f"Invalid payment transition {current} -> {target}")


@dataclass(frozen=True)
class PaymentContext:
    transaction_id: UUID
    transaction_status: str
    human_confirmed: bool
    mandate_id: UUID
    mandate_status: str
    execution_count: int
    max_executions: int
    cart: dict
    approved_hash: str
    security_fresh: bool


@dataclass(frozen=True)
class PaymentAttemptRecord:
    id: UUID
    transaction_id: UUID
    idempotency_key: str
    amount_minor: int
    currency: str
    status: PaymentStatus
    razorpay_order_id: str | None = None
    razorpay_payment_id: str | None = None


@dataclass(frozen=True)
class PaymentAttemptClaim:
    attempt: PaymentAttemptRecord
    created: bool


@dataclass(frozen=True)
class RefundRecord:
    id: UUID
    payment_attempt_id: UUID
    amount_minor: int
    currency: str
    idempotency_key: str
    status: RefundStatus
    provider_refund_id: str | None = None


class PaymentRepository(Protocol):
    def lock_context(self, transaction_id: UUID) -> PaymentContext: ...
    def reusable_attempt(
        self, transaction_id: UUID, idempotency_key: str
    ) -> PaymentAttemptRecord | None: ...
    def create_attempt(
        self, context: PaymentContext, idempotency_key: str
    ) -> PaymentAttemptClaim: ...
    def set_order(
        self, attempt_id: UUID, order_id: str, safe_payload: dict
    ) -> PaymentAttemptRecord: ...
    def transition(
        self,
        attempt_id: UUID,
        target: PaymentStatus,
        payment_id: str | None = None,
        safe_payload: dict | None = None,
    ) -> PaymentAttemptRecord: ...
    def capture_once(
        self, attempt_id: UUID, payment_id: str, safe_payload: dict
    ) -> PaymentAttemptRecord: ...
    def get_attempt(self, attempt_id: UUID) -> PaymentAttemptRecord: ...
    def get_attempt_by_order(self, order_id: str) -> PaymentAttemptRecord | None: ...
    def record_event_once(
        self, event_id: str, event_type: str, attempt_id: UUID | None, safe_payload: dict
    ) -> bool: ...
    def claim_refund(
        self, attempt_id: UUID, user_id: UUID, amount_minor: int, reason: str, idempotency_key: str
    ) -> tuple[RefundRecord, bool]: ...
    def update_refund(
        self, refund_id: UUID, status: RefundStatus, provider_refund_id: str | None, safe_payload: dict
    ) -> RefundRecord: ...
    def get_refund(self, refund_id: UUID) -> RefundRecord: ...
    def record_reconciliation(
        self, attempt_id: UUID, provider_status: str | None, amount_matches: bool,
        currency_matches: bool, resolution: str, safe_details: dict
    ) -> None: ...

    def commit(self) -> None: ...


class RazorpayProvider(Protocol):
    public_key_id: str

    def create_order(self, amount_minor: int, currency: str, receipt: str) -> dict[str, Any]: ...
    def fetch_payment(self, payment_id: str) -> dict[str, Any]: ...
    def fetch_order_payments(self, order_id: str) -> list[dict[str, Any]]: ...
    def verify_callback(self, order_id: str, payment_id: str, signature: str) -> bool: ...
    def verify_webhook(self, raw_body: bytes, signature: str) -> bool: ...
    def create_refund(
        self, payment_id: str, amount_minor: int, idempotency_key: str, reason: str
    ) -> dict[str, Any]: ...
    def fetch_refund(self, refund_id: str) -> dict[str, Any]: ...


class RazorpayHttpProvider:
    def __init__(
        self, key_id: str, key_secret: str, webhook_secret: str, api_url: str, timeout: float
    ):
        self.public_key_id, self.key_secret, self.webhook_secret, self.api_url, self.timeout = (
            key_id,
            key_secret,
            webhook_secret,
            api_url.rstrip("/"),
            timeout,
        )

    def create_order(self, amount_minor: int, currency: str, receipt: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self.api_url}/orders",
            auth=(self.public_key_id, self.key_secret),
            json={
                "amount": amount_minor,
                "currency": currency,
                "receipt": receipt,
                "notes": {"sentinelpay": "test_mode"},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.api_url}/payments/{payment_id}",
            auth=(self.public_key_id, self.key_secret),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def fetch_order_payments(self, order_id: str) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self.api_url}/orders/{order_id}/payments",
            auth=(self.public_key_id, self.key_secret),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return list(response.json().get("items", []))

    def verify_callback(self, order_id: str, payment_id: str, signature: str) -> bool:
        expected = hmac.new(
            self.key_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_webhook(self, raw_body: bytes, signature: str) -> bool:
        expected = hmac.new(self.webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def create_refund(
        self, payment_id: str, amount_minor: int, idempotency_key: str, reason: str
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{self.api_url}/payments/{payment_id}/refund",
            auth=(self.public_key_id, self.key_secret),
            json={
                "amount": amount_minor,
                "speed": "normal",
                "notes": {
                    "sentinelpay_idempotency_key": idempotency_key,
                    "reason": reason,
                    "mode": "test",
                },
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def fetch_refund(self, refund_id: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.api_url}/refunds/{refund_id}",
            auth=(self.public_key_id, self.key_secret),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()


def safe_provider_payload(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "id",
        "entity",
        "amount",
        "currency",
        "status",
        "order_id",
        "captured",
        "method",
        "error_code",
        "error_description",
        "created_at",
    }
    return {key: payload[key] for key in allowed if key in payload}


class PaymentService:
    def __init__(self, repository: PaymentRepository, provider: RazorpayProvider):
        self.repository, self.provider = repository, provider

    def create_order(self, transaction_id: UUID, idempotency_key: str) -> CheckoutData:
        existing = self.repository.reusable_attempt(transaction_id, idempotency_key)
        if existing:
            if existing.status == PaymentStatus.FAILED:
                raise ValueError(
                    "Failed attempt requires a new idempotency key and policy revalidation"
                )
            if not existing.razorpay_order_id:
                raise ValueError("Payment state is UNKNOWN; existing attempt must be resolved")
            return self._checkout(existing)
        context = self.repository.lock_context(transaction_id)
        if context.transaction_status != "AUTHORIZED" or not context.human_confirmed:
            raise PermissionError("SecurityKernel ALLOW and human confirmation required")
        if not context.security_fresh or not SecurityKernel.verify_current_cart(
            context.cart, context.approved_hash
        ):
            raise PermissionError("Security authorization is stale or cart commitment changed")
        if context.mandate_status != "ACTIVE" or context.execution_count >= context.max_executions:
            raise PermissionError("Mandate is consumed, replayed, or inactive")
        claim = self.repository.create_attempt(context, idempotency_key)
        attempt = claim.attempt
        if not claim.created:
            if attempt.razorpay_order_id:
                return self._checkout(attempt)
            raise ValueError(
                "Payment order creation is already in progress; no duplicate was created"
            )
        try:
            order = self.provider.create_order(
                attempt.amount_minor, attempt.currency, str(transaction_id)
            )
            if (
                int(order["amount"]) != attempt.amount_minor
                or order["currency"] != attempt.currency
            ):
                self.repository.transition(
                    attempt.id, PaymentStatus.UNKNOWN, safe_payload=safe_provider_payload(order)
                )
                raise RuntimeError("Provider order amount/currency mismatch")
            attempt = self.repository.set_order(
                attempt.id, str(order["id"]), safe_provider_payload(order)
            )
            attempt = self.repository.transition(attempt.id, PaymentStatus.PAYMENT_PENDING)
            return self._checkout(attempt)
        except (httpx.HTTPError, KeyError, RuntimeError):
            self.repository.transition(attempt.id, PaymentStatus.UNKNOWN)
            raise

    def verify_browser_callback(
        self, attempt_id: UUID, order_id: str, payment_id: str, signature: str
    ) -> PaymentAttemptRecord:
        attempt = self.repository.get_attempt(attempt_id)
        if attempt.razorpay_order_id != order_id or not self.provider.verify_callback(
            order_id, payment_id, signature
        ):
            raise PermissionError("Invalid Razorpay payment signature")
        if attempt.status in (PaymentStatus.CAPTURED, PaymentStatus.FAILED):
            return attempt
        self.repository.transition(attempt_id, PaymentStatus.PAYMENT_PENDING, payment_id)
        try:
            payment = self.provider.fetch_payment(payment_id)
        except httpx.HTTPError:
            return self.repository.transition(attempt_id, PaymentStatus.UNKNOWN, payment_id)
        safe = safe_provider_payload(payment)
        if (
            payment.get("order_id") != order_id
            or int(payment.get("amount", -1)) != attempt.amount_minor
            or payment.get("currency") != attempt.currency
        ):
            return self.repository.transition(attempt_id, PaymentStatus.UNKNOWN, payment_id, safe)
        if payment.get("status") == "captured":
            return self.repository.capture_once(attempt_id, payment_id, safe)
        if payment.get("status") == "failed":
            return self.repository.transition(attempt_id, PaymentStatus.FAILED, payment_id, safe)
        return self.repository.transition(
            attempt_id, PaymentStatus.PAYMENT_PENDING, payment_id, safe
        )

    def process_webhook(self, raw_body: bytes, signature: str) -> PaymentAttemptRecord | None:
        if not self.provider.verify_webhook(raw_body, signature):
            raise PermissionError("Invalid Razorpay webhook signature")
        payload = json.loads(raw_body)
        event_type = str(payload.get("event", "unknown"))
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        order_id, payment_id = payment.get("order_id"), payment.get("id")
        event_id = hashlib.sha256(raw_body).hexdigest()
        attempt = self.repository.get_attempt_by_order(order_id) if order_id else None
        if not self.repository.record_event_once(
            event_id, event_type, attempt.id if attempt else None, safe_provider_payload(payment)
        ):
            return attempt
        if attempt and attempt.status == PaymentStatus.CAPTURED:
            self.repository.commit()
            return attempt
        if not attempt or not payment_id:
            self.repository.commit()
            return attempt
        if event_type in {"payment.captured", "order.paid"} and payment.get("status") == "captured":
            return self.repository.capture_once(
                attempt.id, payment_id, safe_provider_payload(payment)
            )
        if event_type == "payment.failed":
            return self.repository.transition(
                attempt.id, PaymentStatus.FAILED, payment_id, safe_provider_payload(payment)
            )
        return self.repository.transition(
            attempt.id, PaymentStatus.PAYMENT_PENDING, payment_id, safe_provider_payload(payment)
        )

    def resolve_unknown(self, attempt_id: UUID) -> PaymentAttemptRecord:
        attempt = self.repository.get_attempt(attempt_id)
        if attempt.status != PaymentStatus.UNKNOWN:
            return attempt
        try:
            payments = (
                [self.provider.fetch_payment(attempt.razorpay_payment_id)]
                if attempt.razorpay_payment_id
                else self.provider.fetch_order_payments(attempt.razorpay_order_id or "")
            )
        except httpx.HTTPError:
            return attempt
        matching = [
            item
            for item in payments
            if item.get("order_id") == attempt.razorpay_order_id
            and int(item.get("amount", -1)) == attempt.amount_minor
            and item.get("currency") == attempt.currency
        ]
        captured = next((item for item in matching if item.get("status") == "captured"), None)
        if captured:
            return self.repository.capture_once(
                attempt_id, str(captured["id"]), safe_provider_payload(captured)
            )
        pending = next(
            (item for item in matching if item.get("status") in {"authorized", "created"}), None
        )
        if pending:
            return self.repository.transition(
                attempt_id,
                PaymentStatus.PAYMENT_PENDING,
                str(pending["id"]),
                safe_provider_payload(pending),
            )
        if matching and all(item.get("status") == "failed" for item in matching):
            failed = matching[0]
            return self.repository.transition(
                attempt_id, PaymentStatus.FAILED, str(failed["id"]), safe_provider_payload(failed)
            )
        return attempt

    @staticmethod
    def _refund_status(provider_status: str | None) -> RefundStatus:
        return {
            "processed": RefundStatus.PROCESSED,
            "pending": RefundStatus.PROCESSING,
            "failed": RefundStatus.FAILED,
        }.get(str(provider_status).lower(), RefundStatus.UNKNOWN)

    def create_refund(
        self,
        attempt_id: UUID,
        user_id: UUID,
        amount_minor: int,
        reason: str,
        idempotency_key: str,
    ) -> RefundRecord:
        refund, created = self.repository.claim_refund(
            attempt_id, user_id, amount_minor, reason, idempotency_key
        )
        if not created:
            return refund
        attempt = self.repository.get_attempt(attempt_id)
        if not attempt.razorpay_payment_id:
            return self.repository.update_refund(
                refund.id, RefundStatus.UNKNOWN, None, {"reason": "MISSING_PAYMENT_ID"}
            )
        try:
            payload = self.provider.create_refund(
                attempt.razorpay_payment_id, amount_minor, idempotency_key, reason
            )
            if int(payload.get("amount", -1)) != amount_minor:
                return self.repository.update_refund(
                    refund.id,
                    RefundStatus.UNKNOWN,
                    str(payload.get("id")) if payload.get("id") else None,
                    safe_provider_payload(payload),
                )
            return self.repository.update_refund(
                refund.id,
                self._refund_status(payload.get("status")),
                str(payload["id"]),
                safe_provider_payload(payload),
            )
        except (httpx.HTTPError, KeyError):
            return self.repository.update_refund(
                refund.id, RefundStatus.UNKNOWN, None, {"reason": "PROVIDER_UNAVAILABLE"}
            )

    def reconcile_refund(self, refund_id: UUID) -> RefundRecord:
        refund = self.repository.get_refund(refund_id)
        if refund.status in {RefundStatus.PROCESSED, RefundStatus.FAILED}:
            return refund
        if not refund.provider_refund_id:
            return refund
        try:
            payload = self.provider.fetch_refund(refund.provider_refund_id)
        except httpx.HTTPError:
            return refund
        status = self._refund_status(payload.get("status"))
        if int(payload.get("amount", -1)) != refund.amount_minor:
            status = RefundStatus.UNKNOWN
        return self.repository.update_refund(
            refund.id, status, refund.provider_refund_id, safe_provider_payload(payload)
        )

    def reconcile_payment(self, attempt_id: UUID) -> PaymentAttemptRecord:
        before = self.repository.get_attempt(attempt_id)
        after = self.resolve_unknown(attempt_id) if before.status == PaymentStatus.UNKNOWN else before
        self.repository.record_reconciliation(
            attempt_id,
            after.status.value,
            True,
            True,
            "RESOLVED" if after.status != PaymentStatus.UNKNOWN else "MANUAL_REVIEW",
            {"before": before.status.value, "after": after.status.value},
        )
        self.repository.commit()
        return after

    def _checkout(self, attempt: PaymentAttemptRecord) -> CheckoutData:
        return CheckoutData(
            payment_attempt_id=attempt.id,
            public_key_id=self.provider.public_key_id,
            order_id=attempt.razorpay_order_id or "",
            amount_minor=attempt.amount_minor,
            currency=attempt.currency,
            status=attempt.status,
        )
