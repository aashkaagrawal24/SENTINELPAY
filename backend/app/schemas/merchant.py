from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class VariantInput(BaseModel):
    variant_key: str
    name: str
    attributes: dict[str, str] = Field(default_factory=dict)
    price_override_minor: int | None = Field(default=None, ge=0)


class ProductInput(BaseModel):
    sku: str
    name: str
    brand: str | None = None
    category: str
    description: str | None = None
    condition: str = "NEW"
    base_price_minor: int = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    active: bool = True
    metadata: dict = Field(default_factory=dict)
    variants: list[VariantInput] = Field(default_factory=list)


class ProductPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    base_price_minor: int | None = Field(default=None, ge=0)
    active: bool | None = None


class InventoryInput(BaseModel):
    variant_id: UUID | None = None
    available_quantity: int = Field(ge=0)
    reserved_quantity: int = Field(default=0, ge=0)
    reorder_threshold: int | None = Field(default=None, ge=0)
    target_threshold: int | None = Field(default=None, ge=0)


class PolicyInput(BaseModel):
    scope: Literal["GLOBAL", "CATEGORY", "PRODUCT"]
    scope_reference: str | None = None
    base_price_minor: int | None = Field(default=None, ge=0)
    minimum_sale_price_minor: int = Field(ge=0)
    maximum_discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    maximum_discount_minor: int | None = Field(default=None, ge=0)
    negotiation_enabled: bool = False
    max_negotiation_rounds: int = Field(default=0, ge=0)
    upsell_enabled: bool = False
    cross_sell_enabled: bool = False
    campaign_discount_limit_percent: Decimal | None = Field(default=None, ge=0, le=100)
    campaign_budget_limit_minor: int | None = Field(default=None, ge=0)
    minimum_margin_percent: Decimal | None = None
    approval_threshold_minor: int | None = Field(default=None, ge=0)
    valid_from: datetime
    valid_until: datetime | None = None
    status: Literal["DRAFT", "ACTIVE", "EXPIRED", "RETIRED"] = "DRAFT"


class RelationshipInput(BaseModel):
    source_product_id: UUID
    target_product_id: UUID
    relationship_type: Literal["UPSELL", "CROSS_SELL", "SUBSTITUTE", "BUNDLE", "ACCESSORY"]
    priority: int = 0
    weight: Decimal = Decimal(1)
    active: bool = True
