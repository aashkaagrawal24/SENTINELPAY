from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.schemas.campaign import CampaignPolicy, OpportunityMetrics
from app.schemas.security import UnifiedPolicyContext
from app.services.campaign_services import CampaignService, OpportunityScore
from app.services.security_kernel import UnifiedPolicyService


def base_context(campaign_policy=None):
    return UnifiedPolicyContext(
        final_price_minor=1_949_900,
        buyer_budget_minor=2_500_000,
        quantity=1,
        buyer_max_quantity=2,
        condition="NEW",
        allowed_conditions=["NEW"],
        brand="Sony",
        excluded_brands=[],
        mandate_expires_at=datetime.now(UTC) + timedelta(hours=1),
        mandate_status="ACTIVE",
        execution_count=0,
        max_executions=1,
        merchant_minimum_minor=1_850_000,
        base_price_minor=1_999_900,
        discount_minor=50_000,
        merchant_max_discount_minor=149_992,
        available_quantity=20,
        cart_currency="INR",
        mandate_currency="INR",
        campaign_policy=campaign_policy,
    )


def campaign(**changes):
    values = {
        "campaign_id": uuid4(),
        "status": "ACTIVE",
        "starts_at": datetime.now(UTC) - timedelta(minutes=1),
        "ends_at": datetime.now(UTC) + timedelta(minutes=10),
        "discount_minor": 50_000,
        "max_discount_per_order_minor": 60_000,
        "used_budget_minor": 100_000,
        "reserved_budget_minor": 0,
        "total_budget_minor": 500_000,
        "current_redemptions": 1,
        "reserved_redemptions": 0,
        "maximum_redemptions": 10,
        "final_price_minor": 1_949_900,
        "minimum_final_price_minor": 1_850_000,
        "product_eligible": True,
        "segment_eligible": True,
        "offer_eligible": True,
    }
    values.update(changes)
    return CampaignPolicy(**values)


def test_opportunity_score_is_deterministic_and_explainable():
    metrics = OpportunityMetrics(
        inventory_pressure=1,
        conversion_gap=0.8,
        demand_signal=0.6,
        margin_room=0.075,
        historical_lift=0.2,
        available_quantity=20,
        product_views=7,
        completed_transactions=1,
        abandoned_carts=2,
        demand_sessions=4,
        accepted_growth_events=1,
    )
    score, reasons = OpportunityScore.calculate(metrics)
    assert score == 0.65125
    assert {"EXCESS_INVENTORY", "ABANDONED_CARTS", "POLICY_MARGIN_ROOM"} <= set(reasons)


def test_campaign_assertions_share_existing_solver_run():
    decision = UnifiedPolicyService().evaluate(base_context(campaign()))
    assert decision.solver_result == "SAT"
    assert "BUYER_BUDGET" in decision.assertions
    assert "MERCHANT_FLOOR" in decision.assertions
    assert "CAMPAIGN_BUDGET" in decision.assertions
    assert "CAMPAIGN_PRODUCT_ELIGIBLE" in decision.assertions


def test_expired_campaign_blocks_stale_discount():
    policy = campaign(ends_at=datetime.now(UTC) - timedelta(seconds=1))
    decision = UnifiedPolicyService().evaluate(base_context(policy))
    assert decision.solver_result == "UNSAT"
    assert "CAMPAIGN_NOT_EXPIRED" in decision.failed_constraints


def test_campaign_budget_redemption_and_margin_are_hard_constraints():
    policy = campaign(used_budget_minor=480_000, reserved_budget_minor=10_000)
    decision = UnifiedPolicyService().evaluate(base_context(policy))
    assert "CAMPAIGN_BUDGET" in decision.failed_constraints
    policy = campaign(current_redemptions=9, reserved_redemptions=1)
    decision = UnifiedPolicyService().evaluate(base_context(policy))
    assert "CAMPAIGN_REDEMPTIONS" in decision.failed_constraints
    policy = campaign(minimum_final_price_minor=1_960_000)
    decision = UnifiedPolicyService().evaluate(base_context(policy))
    assert "CAMPAIGN_MARGIN" in decision.failed_constraints


def test_offer_and_segment_eligibility_fail_closed():
    policy = campaign(product_eligible=False, segment_eligible=False, offer_eligible=False)
    decision = UnifiedPolicyService().evaluate(base_context(policy))
    eligibility_assertions = {
        "CAMPAIGN_PRODUCT_ELIGIBLE",
        "CAMPAIGN_SEGMENT_ELIGIBLE",
        "CAMPAIGN_OFFER_ELIGIBLE",
    }
    assert eligibility_assertions <= set(decision.assertions)
    assert eligibility_assertions & set(decision.failed_constraints)


def test_no_campaign_regression_has_no_campaign_assertions():
    decision = UnifiedPolicyService().evaluate(base_context())
    assert decision.solver_result == "SAT"
    assert not any(label.startswith("CAMPAIGN_") for label in decision.assertions)


def test_stop_conditions_cover_time_budget_redemptions_and_inventory():
    base = {
        "end_time": datetime.now(UTC) + timedelta(minutes=5),
        "used_discount_budget_minor": 0,
        "reserved_discount_budget_minor": 0,
        "total_discount_budget_minor": 100,
        "current_redemptions": 0,
        "reserved_redemptions": 0,
        "maximum_redemptions": 2,
        "stop_conditions": {"inventory_below": 2},
    }
    assert CampaignService.stop_reason(base, 1) == "INVENTORY_THRESHOLD_CROSSED"
    assert CampaignService.stop_reason({**base, "used_discount_budget_minor": 100}, 10) == "BUDGET_EXHAUSTED"
    assert CampaignService.stop_reason({**base, "current_redemptions": 2}, 10) == "REDEMPTIONS_EXHAUSTED"
    assert CampaignService.stop_reason(
        {**base, "end_time": datetime.now(UTC) - timedelta(seconds=1)}, 10
    ) == "END_TIME_REACHED"


def test_discount_calculation_uses_basis_points_and_per_order_cap():
    percent = {"discount_type": "PERCENT", "discount_value": 750, "max_discount_per_order_minor": 100_000}
    fixed = {"discount_type": "FIXED", "discount_value": 80_000, "max_discount_per_order_minor": 50_000}
    assert CampaignService.discount_minor(percent, 1_000_000) == 75_000
    assert CampaignService.discount_minor(fixed, 1_000_000) == 50_000
