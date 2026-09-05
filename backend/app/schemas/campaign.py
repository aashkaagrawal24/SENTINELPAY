from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class OpportunityMetrics(BaseModel):
    inventory_pressure: float = Field(ge=0, le=1)
    conversion_gap: float = Field(ge=0, le=1)
    demand_signal: float = Field(ge=0, le=1)
    margin_room: float = Field(ge=0, le=1)
    historical_lift: float = Field(ge=0, le=1)
    available_quantity: int = Field(ge=0)
    product_views: int = Field(ge=0)
    completed_transactions: int = Field(ge=0)
    abandoned_carts: int = Field(ge=0)
    demand_sessions: int = Field(ge=0)
    accepted_growth_events: int = Field(ge=0)


class CampaignProposal(BaseModel):
    opportunity_id: UUID | None = None
    name: str = Field(min_length=2, max_length=180)
    campaign_type: str = "INVENTORY_PUSH"
    objective: str = "Increase bounded conversion"
    product_ids: list[UUID] = Field(min_length=1)
    discount_type: Literal["PERCENT", "FIXED"]
    discount_value: int = Field(gt=0, description="Basis points for PERCENT; minor units for FIXED")
    max_discount_per_order_minor: int = Field(gt=0)
    total_discount_budget_minor: int = Field(gt=0)
    maximum_redemptions: int = Field(gt=0)
    minimum_final_price_minor: int | None = Field(default=None, ge=0)
    eligibility: dict = Field(default_factory=dict)
    start_time: datetime
    end_time: datetime
    stop_conditions: dict = Field(default_factory=dict)
    requires_merchant_approval: bool = True


class CampaignPolicy(BaseModel):
    campaign_id: UUID
    status: str
    starts_at: datetime
    ends_at: datetime
    discount_minor: int = Field(ge=0)
    max_discount_per_order_minor: int = Field(ge=0)
    used_budget_minor: int = Field(ge=0)
    reserved_budget_minor: int = Field(ge=0)
    total_budget_minor: int = Field(ge=0)
    current_redemptions: int = Field(ge=0)
    reserved_redemptions: int = Field(ge=0)
    maximum_redemptions: int = Field(ge=0)
    final_price_minor: int = Field(ge=0)
    minimum_final_price_minor: int = Field(ge=0)
    product_eligible: bool
    segment_eligible: bool
    offer_eligible: bool
