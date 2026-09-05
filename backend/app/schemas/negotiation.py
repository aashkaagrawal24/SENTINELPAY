from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class NegotiationStatus(StrEnum):
    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FALLBACK = "FALLBACK"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class NegotiationActor(StrEnum):
    BUYER_AGENT = "BUYER_AGENT"
    MERCHANT_AGENT = "MERCHANT_AGENT"


class NegotiationState(BaseModel):
    id: UUID
    starting_price_minor: int = Field(ge=0)
    buyer_ceiling_minor: int = Field(ge=0)
    merchant_floor_minor: int = Field(ge=0)
    fallback_price_minor: int | None = Field(default=None, ge=0)
    fallback_valid_until: datetime | None = None
    current_round: int = 0
    max_rounds: int = Field(gt=0)
    last_buyer_offer_minor: int | None = None
    last_merchant_ask_minor: int | None = None
    status: NegotiationStatus = NegotiationStatus.OPEN
    final_agreed_price_minor: int | None = None
    expires_at: datetime


class NegotiationDecision(BaseModel):
    decision: str
    status: NegotiationStatus
    accepted_price_minor: int | None = None
    reason_code: str
    current_round: int
