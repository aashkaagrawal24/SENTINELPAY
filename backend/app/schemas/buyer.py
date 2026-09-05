from datetime import datetime

from pydantic import BaseModel, Field


class ParsedIntent(BaseModel):
    product_query: str
    max_budget_minor: int | None = Field(default=None, ge=0)
    currency: str = "INR"
    quantity: int = Field(default=1, ge=1)
    allowed_conditions: list[str] = Field(default_factory=list)
    preferred_brands: list[str] = Field(default_factory=list)
    excluded_brands: list[str] = Field(default_factory=list)
    delivery_deadline: datetime | None = None
    negotiation_allowed: bool = False
    upsell_allowed: bool = False
    cross_sell_allowed: bool = False
    campaign_offer_allowed: bool = False
    auto_purchase_allowed: bool = False
    mandate_expiry_minutes: int = Field(default=60, ge=5, le=1440)
