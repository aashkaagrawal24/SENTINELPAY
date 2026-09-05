from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.campaign import CampaignPolicy


class CartLineConstraint(BaseModel):
    product_id: str
    quantity: int = Field(ge=1)
    available_quantity: int = Field(ge=0)
    condition: str
    brand: str | None = None


class AdvancedSecurityEvidence(BaseModel):
    zk_budget_verified: bool = False
    mandate_verifier_approved: bool = False
    policy_verifier_approved: bool = False
    risk_verifier_approved: bool = False
    bls_aggregate_verified: bool = False
    provenance_trusted: bool = False
    proof_references: dict[str, str] = Field(default_factory=dict)


class UnifiedPolicyContext(BaseModel):
    final_price_minor: int = Field(ge=0)
    buyer_budget_minor: int = Field(ge=0)
    quantity: int = Field(ge=1)
    buyer_max_quantity: int = Field(ge=1)
    condition: str
    allowed_conditions: list[str]
    brand: str | None = None
    excluded_brands: list[str] = Field(default_factory=list)
    mandate_expires_at: datetime
    mandate_status: str
    execution_count: int = 0
    max_executions: int = 1
    merchant_minimum_minor: int = Field(ge=0)
    base_price_minor: int = Field(ge=0)
    discount_minor: int = Field(ge=0)
    merchant_max_discount_minor: int = Field(ge=0)
    available_quantity: int = Field(ge=0)
    cart_currency: str
    mandate_currency: str
    auto_purchase_allowed: bool = False
    lines: list[CartLineConstraint] = Field(default_factory=list)
    campaign_policy: CampaignPolicy | None = None
    advanced_verification_required: bool = False
    advanced_evidence: AdvancedSecurityEvidence | None = None


class PolicyDecision(BaseModel):
    solver_result: str
    failed_constraints: list[str]
    assertions: list[str]
