from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class PaymentStatus(StrEnum):
    CREATED = "CREATED"
    ORDER_CREATED = "ORDER_CREATED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class CheckoutData(BaseModel):
    payment_attempt_id: UUID
    public_key_id: str
    order_id: str
    amount_minor: int
    currency: str
    status: PaymentStatus


class PaymentCallback(BaseModel):
    payment_attempt_id: UUID
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class RefundStatus(StrEnum):
    REQUESTED = "REQUESTED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class RefundRequest(BaseModel):
    payment_attempt_id: UUID
    amount_minor: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=120)
