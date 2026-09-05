from dataclasses import dataclass
from datetime import UTC, datetime

from app.schemas.security import UnifiedPolicyContext
from app.services.security_kernel import cart_commitment


@dataclass(frozen=True)
class VerifierDecision:
    role: str
    approved: bool
    checks: dict[str, bool]


class MandateVerifier:
    role = "MANDATE"

    def evaluate(self, context: UnifiedPolicyContext) -> VerifierDecision:
        checks = {
            "active": context.mandate_status == "ACTIVE",
            "unexpired": context.mandate_expires_at > datetime.now(UTC),
            "execution_available": context.execution_count < context.max_executions,
            "budget": context.final_price_minor <= context.buyer_budget_minor,
            "quantity": context.quantity <= context.buyer_max_quantity,
            "currency": context.cart_currency == context.mandate_currency,
        }
        return VerifierDecision(self.role, all(checks.values()), checks)


class PolicyVerifier:
    role = "POLICY"

    def evaluate(self, context: UnifiedPolicyContext) -> VerifierDecision:
        checks = {
            "merchant_floor": context.final_price_minor >= context.merchant_minimum_minor,
            "discount_limit": context.discount_minor <= context.merchant_max_discount_minor,
            "inventory": context.quantity <= context.available_quantity,
            "line_inventory": all(line.quantity <= line.available_quantity for line in context.lines),
        }
        if context.campaign_policy:
            campaign = context.campaign_policy
            checks |= {
                "campaign_active": campaign.status == "ACTIVE",
                "campaign_current": campaign.starts_at <= datetime.now(UTC) <= campaign.ends_at,
                "campaign_budget": campaign.used_budget_minor
                + campaign.reserved_budget_minor
                + campaign.discount_minor
                <= campaign.total_budget_minor,
                "campaign_margin": campaign.final_price_minor
                >= campaign.minimum_final_price_minor,
            }
        return VerifierDecision(self.role, all(checks.values()), checks)


class RiskVerifier:
    role = "RISK"

    def evaluate(self, cart: dict) -> VerifierDecision:
        checks = {
            "nonempty_cart": bool(cart.get("items")),
            "nonnegative_total": int(cart.get("total_minor", -1)) >= 0,
            "explicit_currency": len(str(cart.get("currency", ""))) == 3,
            "commitment_stable": cart_commitment(cart) == cart_commitment(dict(cart)),
        }
        return VerifierDecision(self.role, all(checks.values()), checks)


class IndependentVerifierSet:
    def evaluate(self, context: UnifiedPolicyContext, cart: dict) -> list[VerifierDecision]:
        return [
            MandateVerifier().evaluate(context),
            PolicyVerifier().evaluate(context),
            RiskVerifier().evaluate(cart),
        ]
