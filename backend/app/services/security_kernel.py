import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum

from z3 import Bool, BoolVal, Int, Solver, sat

from app.schemas.security import PolicyDecision, UnifiedPolicyContext


def canonical_cart(cart: dict) -> str:
    financial = {
        key: cart[key]
        for key in (
            "merchant_id",
            "mandate_id",
            "currency",
            "subtotal_minor",
            "discount_minor",
            "shipping_minor",
            "total_minor",
            "delivery",
            "version",
            "items",
        )
    }
    return json.dumps(financial, sort_keys=True, separators=(",", ":"), default=str)


def cart_commitment(cart: dict) -> str:
    return hashlib.sha256(canonical_cart(cart).encode()).hexdigest()


class UnifiedPolicyService:
    """All hard buyer, merchant, campaign-null, inventory and currency checks use one solver."""

    VERSION = "z3-unified-v1"

    def evaluate(self, context: UnifiedPolicyContext) -> PolicyDecision:
        solver = Solver()
        final_price, quantity, discount, available = (
            Int("final_price"),
            Int("quantity"),
            Int("discount"),
            Int("available"),
        )
        solver.add(
            final_price == context.final_price_minor,
            quantity == context.quantity,
            discount == context.discount_minor,
            available == context.available_quantity,
        )
        checks = {
            "BUYER_BUDGET": final_price <= context.buyer_budget_minor,
            "BUYER_QUANTITY": quantity <= context.buyer_max_quantity,
            "BUYER_CONDITION": BoolVal(
                True if context.lines else context.condition in context.allowed_conditions
            ),
            "BUYER_BRAND": BoolVal(
                True if context.lines else context.brand not in context.excluded_brands
            ),
            "MANDATE_EXPIRY": BoolVal(context.mandate_expires_at > datetime.now(UTC)),
            "MANDATE_ACTIVE": BoolVal(context.mandate_status == "ACTIVE"),
            "MANDATE_EXECUTIONS": BoolVal(context.execution_count < context.max_executions),
            "MERCHANT_FLOOR": final_price >= context.merchant_minimum_minor,
            "MERCHANT_DISCOUNT": discount <= context.merchant_max_discount_minor,
            "INVENTORY": BoolVal(True) if context.lines else quantity <= available,
            "CURRENCY": BoolVal(context.cart_currency == context.mandate_currency),
        }
        if context.campaign_policy:
            campaign = context.campaign_policy
            now = datetime.now(UTC)
            checks.update(
                {
                    "CAMPAIGN_ACTIVE": BoolVal(campaign.status == "ACTIVE"),
                    "CAMPAIGN_STARTED": BoolVal(now >= campaign.starts_at),
                    "CAMPAIGN_NOT_EXPIRED": BoolVal(now <= campaign.ends_at),
                    "CAMPAIGN_ORDER_DISCOUNT": BoolVal(
                        campaign.discount_minor <= campaign.max_discount_per_order_minor
                    ),
                    "CAMPAIGN_BUDGET": BoolVal(
                        campaign.used_budget_minor
                        + campaign.reserved_budget_minor
                        + campaign.discount_minor
                        <= campaign.total_budget_minor
                    ),
                    "CAMPAIGN_REDEMPTIONS": BoolVal(
                        campaign.current_redemptions + campaign.reserved_redemptions
                        < campaign.maximum_redemptions
                    ),
                    "CAMPAIGN_MARGIN": BoolVal(
                        campaign.final_price_minor >= campaign.minimum_final_price_minor
                    ),
                    "CAMPAIGN_PRODUCT_ELIGIBLE": BoolVal(campaign.product_eligible),
                    "CAMPAIGN_SEGMENT_ELIGIBLE": BoolVal(campaign.segment_eligible),
                    "CAMPAIGN_OFFER_ELIGIBLE": BoolVal(campaign.offer_eligible),
                }
            )
        if context.advanced_verification_required:
            evidence = context.advanced_evidence
            checks.update(
                {
                    "ADVANCED_EVIDENCE_PRESENT": BoolVal(evidence is not None),
                    "ZK_BUDGET_PROOF": BoolVal(bool(evidence and evidence.zk_budget_verified)),
                    "MANDATE_VERIFIER": BoolVal(
                        bool(evidence and evidence.mandate_verifier_approved)
                    ),
                    "POLICY_VERIFIER": BoolVal(
                        bool(evidence and evidence.policy_verifier_approved)
                    ),
                    "RISK_VERIFIER": BoolVal(bool(evidence and evidence.risk_verifier_approved)),
                    "BLS_AGGREGATE": BoolVal(
                        bool(evidence and evidence.bls_aggregate_verified)
                    ),
                    "PROVENANCE_GATE": BoolVal(bool(evidence and evidence.provenance_trusted)),
                }
            )
        for index, line in enumerate(context.lines):
            checks[f"LINE_{index}_CONDITION"] = BoolVal(
                line.condition in context.allowed_conditions
            )
            checks[f"LINE_{index}_BRAND"] = BoolVal(line.brand not in context.excluded_brands)
            checks[f"LINE_{index}_INVENTORY"] = BoolVal(line.quantity <= line.available_quantity)
        labels = []
        for label, assertion in checks.items():
            marker = Bool(f"track_{label}")
            solver.assert_and_track(assertion, marker)
            labels.append(label)
        result = solver.check()
        failed = (
            [str(item).removeprefix("track_") for item in solver.unsat_core()]
            if result != sat
            else []
        )
        return PolicyDecision(
            solver_result="SAT" if result == sat else "UNSAT",
            failed_constraints=failed,
            assertions=labels,
        )


class SecurityOutcome(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class SecurityKernel:
    def __init__(self, policy_service: UnifiedPolicyService | None = None):
        self.policy_service = policy_service or UnifiedPolicyService()

    def authorize(
        self,
        context: UnifiedPolicyContext,
        cart: dict,
        expected_mandate_hash: str,
        actual_mandate_hash: str,
        trusted_sources: bool = True,
    ) -> dict:
        if not trusted_sources or expected_mandate_hash != actual_mandate_hash:
            return {
                "outcome": SecurityOutcome.DENY,
                "reason": "UNTRUSTED_AUTHORITY_OR_MANDATE_MUTATED",
            }
        try:
            decision = self.policy_service.evaluate(context)
        except Exception:  # noqa: BLE001 - authorization must fail closed for any solver failure.
            return {
                "outcome": SecurityOutcome.DENY,
                "reason": "SOLVER_ERROR",
                "solver_result": "ERROR",
            }
        if decision.solver_result != "SAT":
            return {
                "outcome": SecurityOutcome.DENY,
                "reason": "POLICY_UNSAT",
                "decision": decision.model_dump(),
            }
        outcome = (
            SecurityOutcome.ALLOW
            if context.auto_purchase_allowed
            else SecurityOutcome.REQUIRE_APPROVAL
        )
        return {
            "outcome": outcome,
            "decision": decision.model_dump(),
            "approved_hash": cart_commitment(cart),
        }

    @staticmethod
    def verify_current_cart(cart: dict, approved_hash: str) -> bool:
        return cart_commitment(cart) == approved_hash

    def confirm(self, cart: dict, approved_hash: str, human_confirmed: bool) -> SecurityOutcome:
        if not human_confirmed or not self.verify_current_cart(cart, approved_hash):
            return SecurityOutcome.DENY
        return SecurityOutcome.ALLOW
