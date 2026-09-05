from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

ValueType = Literal[
    "REAL_DATA",
    "DERIVED",
    "ASSUMPTION",
    "AI_EXTRACTED",
    "SIMULATED",
    "OPTIMIZED",
    "MODEL_ESTIMATE",
]
TrustClass = Literal[
    "USER_SIGNED",
    "MERCHANT_API",
    "MERCHANT_SIGNED",
    "RAZORPAY_VERIFIED",
    "SYSTEM_DERIVED",
    "MODEL_INFERRED",
    "UNTRUSTED_EXTERNAL",
]


class ProvenanceCreate(BaseModel):
    entity_type: str = Field(min_length=1, max_length=60)
    entity_id: UUID
    field_name: str = Field(min_length=1, max_length=100)
    value_snapshot: Any
    unit: str | None = None
    value_type: ValueType
    trust_class: TrustClass
    method: str | None = None
    model_name: str | None = None
    model_version: str | None = None
    source: str
    source_reference: str | None = None
    source_date: datetime | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    assumption: bool = False
    financial_authority: bool = False
    user_id: UUID | None = None
    merchant_id: UUID | None = None


class JudgeAttackRequest(BaseModel):
    scenario_key: str
    merchant_id: UUID | None = None


class JudgeAttackResult(BaseModel):
    scenario_key: str
    category: str
    attack: dict[str, Any]
    ai_response: str
    buyer_policy: dict[str, Any]
    merchant_policy: dict[str, Any]
    campaign_policy: dict[str, Any]
    z3_assertions: list[str]
    solver_result: Literal["SAT", "UNSAT", "NOT_RUN"]
    failed_constraints: list[str]
    security_kernel_result: Literal["ALLOW", "DENY", "REQUIRE_APPROVAL"]
    razorpay_called: bool
    blocked: bool
    advanced_layers: dict[str, Any] = Field(default_factory=dict)
    audit_event_id: UUID | None = None
    execution_ms: float = 0

