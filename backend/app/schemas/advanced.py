from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ExternalOfferInput(BaseModel):
    external_offer_id: str
    title: str
    price_minor: int = Field(ge=0)
    currency: str = "INR"
    source_url: str | None = None
    fetched_at: datetime


class ExternalSearchRequest(BaseModel):
    query: str
    expected_product_key: str | None = None
    offers: list[ExternalOfferInput] = Field(default_factory=list)


class BanditContext(BaseModel):
    listing_age_days: int = Field(ge=0)
    seller_type: str
    category: str
    prior_rounds: int = Field(ge=0)
    remaining_budget_minor: int = Field(ge=0)
    fallback_available: bool


class BanditArm(BaseModel):
    action: Literal[
        "AGGRESSIVE", "BALANCED", "FAST_CLOSE", "UPSELL_VALUE", "UPSELL_PREMIUM"
    ]
    pulls: int = Field(ge=0)
    cumulative_reward: float = 0


class BanditRequest(BaseModel):
    merchant_id: UUID | None = None
    context: BanditContext
    arms: list[BanditArm]


class ZkProveRequest(BaseModel):
    private_budget_minor: int = Field(ge=0)
    public_price_minor: int = Field(ge=0)
    mandate_id: UUID | None = None


class ZkVerifyRequest(BaseModel):
    public_price_minor: int = Field(ge=0)
    budget_commitment: str
    proof: dict


class SignedAttestation(BaseModel):
    verifier_id: str
    decision: Literal["APPROVE", "DENY"]
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_key: str
    signature: str
    issued_at: datetime
    expires_at: datetime


class MultiVerifierRequest(BaseModel):
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_k: int = Field(gt=0)
    expected_verifiers: list[str] = Field(min_length=1)
    attestations: list[SignedAttestation]


class SupplierQuoteInput(BaseModel):
    quote_id: UUID
    merchant_id: UUID
    unit_price_minor: int = Field(ge=0)
    available_quantity: int = Field(ge=0)
    delivery_at: datetime
    vendor_risk_basis_points: int = Field(ge=0, le=10_000)
    merchant_minimum_quantity: int = Field(default=1, gt=0)


class ProcurementOptimizeRequest(BaseModel):
    required_quantity: int = Field(gt=0)
    max_budget_minor: int = Field(ge=0)
    delivery_deadline: datetime
    approved_vendor_ids: list[UUID]
    lambda_delivery: float = Field(default=1, ge=0)
    lambda_vendor_risk: float = Field(default=1, ge=0)
    quotes: list[SupplierQuoteInput]


class SimulatorRequest(BaseModel):
    seed: int = 42
    episodes: int = Field(default=500, ge=10, le=10_000)
    candidate_strategy: Literal["AGGRESSIVE", "BALANCED", "FAST_CLOSE"] = "BALANCED"


class PlatformSnapshot(BaseModel):
    platform: str
    offers: list[ExternalOfferInput] = Field(default_factory=list)
    simulate_failure: bool = False


class UniversalScoutRequest(BaseModel):
    query: str
    expected_product: dict[str, str] = Field(default_factory=dict)
    snapshots: list[PlatformSnapshot] = Field(default_factory=list)
    timeout_seconds: float = Field(default=2.0, gt=0, le=10)


class NegotiabilityFeatures(BaseModel):
    platform: str
    seller_type: str
    category: str
    listing_age_days: int = Field(ge=0)
    explicit_negotiable: bool = False
    rfq_supported: bool = False
    quantity: int = Field(default=1, gt=0)
    historical_price_edits: int = Field(default=0, ge=0)
    price_roundness: float = Field(default=0, ge=0, le=1)
    merchant_negotiation_enabled: bool = False


class NegotiabilityRequest(BaseModel):
    features: NegotiabilityFeatures


class RacComponent(BaseModel):
    amount_minor: int = Field(ge=0)
    source: str
    trust_class: Literal[
        "MERCHANT_API", "MERCHANT_SIGNED", "SYSTEM_DERIVED", "UNTRUSTED_EXTERNAL"
    ]
    source_reference: str | None = None


class RacRequest(BaseModel):
    price: RacComponent
    shipping: RacComponent
    verified_discount: RacComponent
    confirmed_cashback: RacComponent
    condition_penalty: RacComponent
    warranty_penalty: RacComponent
    seller_risk_penalty: RacComponent
    delivery_penalty: RacComponent


class LinUcbState(BaseModel):
    action: Literal["AGGRESSIVE", "BALANCED", "FAST_CLOSE", "BULK_DISCOUNT", "DEADLINE_BASED"]
    a_matrix: list[list[float]]
    b_vector: list[float]
    observations: int = Field(default=0, ge=0)


class LinUcbSelectRequest(BaseModel):
    merchant_id: UUID | None = None
    context_key: str = Field(default="DEFAULT", min_length=1, max_length=180)
    context: list[float] = Field(min_length=1, max_length=32)
    alpha: float = Field(default=1.0, ge=0, le=10)
    states: list[LinUcbState]


class LinUcbUpdateRequest(BaseModel):
    merchant_id: UUID | None = None
    context_key: str = Field(default="DEFAULT", min_length=1, max_length=180)
    context: list[float] = Field(min_length=1, max_length=32)
    reward: float
    state: LinUcbState


class CfrRequest(BaseModel):
    iterations: int = Field(default=5_000, ge=100, le=100_000)
    seed: int = 42


class AnalyticsObservation(BaseModel):
    treatment: int = Field(ge=0, le=1)
    outcome: float
    prior_sessions: float = Field(ge=0)
    inventory_pressure: float = Field(ge=0)


class CausalAnalysisRequest(BaseModel):
    observations: list[AnalyticsObservation] = Field(min_length=20)


class DpAggregateRequest(BaseModel):
    values: list[float] = Field(min_length=1)
    epsilon: float = Field(gt=0, le=20)
    lower: float
    upper: float
    statistic: Literal["MEAN", "SUM", "COUNT"] = "MEAN"


class GraphNode(BaseModel):
    id: str
    kind: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str


class ProvenanceGraphRequest(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    source_id: str | None = None
    target_id: str | None = None


class HomomorphicAggregateRequest(BaseModel):
    values: list[int] = Field(min_length=1, max_length=10_000)


class BlsSignerInput(BaseModel):
    verifier_id: Literal["MANDATE", "POLICY", "RISK"]
    private_key: int = Field(gt=0)


class BlsApprovalRequest(BaseModel):
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    signers: list[BlsSignerInput] = Field(min_length=2, max_length=3)
    required_k: int = Field(default=2, ge=2, le=3)


class VdfRequest(BaseModel):
    challenge: str = Field(min_length=1, max_length=256)
    iterations: int = Field(default=2_000, ge=100, le=100_000)


class SecurityEvidenceRequest(BaseModel):
    cart_id: UUID


class SealedBidInput(BaseModel):
    bid_id: UUID
    vendor_id: UUID
    unit_cost_minor: int = Field(gt=0)
    quantity: int = Field(gt=0)
    delivery_days: int = Field(gt=0)
    risk_basis_points: int = Field(default=0, ge=0, le=10_000)
    nonce: str = Field(min_length=16)


class VcgProcurementRequest(BaseModel):
    required_quantity: int = Field(gt=0)
    buyer_value_per_unit_minor: int = Field(gt=0)
    max_budget_minor: int = Field(gt=0)
    delivery_deadline_days: int = Field(gt=0)
    approved_vendor_ids: list[UUID] = Field(min_length=2)
    bids: list[SealedBidInput] = Field(min_length=2)
    vdf_iterations: int = Field(default=2_000, ge=100, le=100_000)

    @model_validator(mode="after")
    def validate_vendor_set(self):
        approved = set(self.approved_vendor_ids)
        bid_vendors = [bid.vendor_id for bid in self.bids]
        if len(approved) != len(self.approved_vendor_ids):
            raise ValueError("approved_vendor_ids must be unique")
        if len(set(bid_vendors)) != len(bid_vendors):
            raise ValueError("exactly one sealed bid is allowed per vendor")
        if not set(bid_vendors).issubset(approved):
            raise ValueError("every bid vendor must be in approved_vendor_ids")
        if len({bid.bid_id for bid in self.bids}) != len(self.bids):
            raise ValueError("bid_id values must be unique")
        return self
