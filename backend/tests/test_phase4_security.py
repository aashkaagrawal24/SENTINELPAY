from datetime import UTC, datetime, timedelta

from app.schemas.security import UnifiedPolicyContext
from app.services.security_kernel import SecurityKernel, UnifiedPolicyService, cart_commitment


def context(**changes):
    values = {
        "final_price_minor": 19_999_00,
        "buyer_budget_minor": 25_000_00,
        "quantity": 1,
        "buyer_max_quantity": 1,
        "condition": "NEW",
        "allowed_conditions": ["NEW"],
        "brand": "Sony",
        "excluded_brands": [],
        "mandate_expires_at": datetime.now(UTC) + timedelta(hours=1),
        "mandate_status": "ACTIVE",
        "execution_count": 0,
        "max_executions": 1,
        "merchant_minimum_minor": 18_500_00,
        "base_price_minor": 19_999_00,
        "discount_minor": 0,
        "merchant_max_discount_minor": 149_992,
        "available_quantity": 5,
        "cart_currency": "INR",
        "mandate_currency": "INR",
        "auto_purchase_allowed": False,
    }
    values.update(changes)
    return UnifiedPolicyContext(**values)


def cart():
    return {
        "merchant_id": "m",
        "mandate_id": "x",
        "currency": "INR",
        "subtotal_minor": 1_999_900,
        "discount_minor": 0,
        "shipping_minor": 0,
        "total_minor": 1_999_900,
        "delivery": {},
        "version": 1,
        "items": [{"product_id": "p", "quantity": 1, "unit_price_minor": 1_999_900}],
    }


def test_valid_cart_requires_human_approval():
    result = SecurityKernel().authorize(context(), cart(), "hash", "hash")
    assert result["outcome"] == "REQUIRE_APPROVAL"
    assert result["decision"]["solver_result"] == "SAT"


def test_budget_floor_discount_inventory_and_condition_fail_closed():
    cases = [
        (context(final_price_minor=26_000_00), "BUYER_BUDGET"),
        (context(final_price_minor=17_000_00), "MERCHANT_FLOOR"),
        (context(discount_minor=200_000), "MERCHANT_DISCOUNT"),
        (context(quantity=2, available_quantity=1, buyer_max_quantity=2), "INVENTORY"),
        (context(condition="USED"), "BUYER_CONDITION"),
    ]
    for candidate, reason in cases:
        decision = UnifiedPolicyService().evaluate(candidate)
        assert decision.solver_result == "UNSAT"
        assert reason in decision.failed_constraints


def test_expired_revoked_and_execution_limit_denied():
    for candidate in [
        context(mandate_expires_at=datetime.now(UTC) - timedelta(seconds=1)),
        context(mandate_status="REVOKED"),
        context(execution_count=1),
    ]:
        assert UnifiedPolicyService().evaluate(candidate).solver_result == "UNSAT"


def test_commitment_detects_mutation_and_confirmation_allows_unchanged():
    original = cart()
    approved = cart_commitment(original)
    assert SecurityKernel().confirm(original, approved, True) == "ALLOW"
    original["total_minor"] += 1
    assert SecurityKernel().confirm(original, approved, True) == "DENY"


def test_solver_error_and_bad_integrity_fail_closed():
    class BrokenPolicy:
        def evaluate(self, _):
            raise RuntimeError("z3 failure")

    assert (
        SecurityKernel(BrokenPolicy()).authorize(context(), cart(), "x", "x")["reason"]
        == "SOLVER_ERROR"
    )
    assert SecurityKernel().authorize(context(), cart(), "x", "y")["outcome"] == "DENY"
