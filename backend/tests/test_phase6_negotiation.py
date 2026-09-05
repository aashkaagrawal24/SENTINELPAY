from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.schemas.negotiation import NegotiationActor, NegotiationState, NegotiationStatus
from app.schemas.security import CartLineConstraint, UnifiedPolicyContext
from app.services.negotiation_service import BasketGrowthEngine, NegotiationController
from app.services.security_kernel import UnifiedPolicyService


def state(**changes):
    values = {
        "id": uuid4(),
        "starting_price_minor": 1_999_900,
        "buyer_ceiling_minor": 2_100_000,
        "merchant_floor_minor": 1_850_000,
        "fallback_price_minor": 1_999_900,
        "fallback_valid_until": datetime.now(UTC) + timedelta(minutes=5),
        "current_round": 0,
        "max_rounds": 3,
        "status": NegotiationStatus.OPEN,
        "expires_at": datetime.now(UTC) + timedelta(minutes=10),
    }
    values.update(changes)
    return NegotiationState(**values)


def test_bounded_multi_round_success():
    controller = NegotiationController()
    current = state()
    current, first = controller.step(current, NegotiationActor.BUYER_AGENT, 1_900_000)
    assert first.decision == "CONTINUE"
    current, second = controller.step(current, NegotiationActor.MERCHANT_AGENT, 1_950_000)
    assert second.decision == "CONTINUE"
    current, final = controller.step(current, NegotiationActor.BUYER_AGENT, 1_950_000)
    assert final.decision == "ACCEPT" and final.accepted_price_minor == 1_950_000
    assert current.status == NegotiationStatus.ACCEPTED


def test_no_overlap_and_invalid_agent_amounts_blocked():
    controller = NegotiationController()
    no_deal, decision = controller.step(
        state(merchant_floor_minor=2_200_000), NegotiationActor.BUYER_AGENT, 2_000_000
    )
    assert (
        no_deal.status == NegotiationStatus.REJECTED
        and decision.reason_code == "NO_OVERLAPPING_RANGE"
    )
    unchanged, buyer_block = controller.step(state(), NegotiationActor.BUYER_AGENT, 2_100_001)
    assert unchanged.current_round == 0 and buyer_block.reason_code == "BUYER_CEILING_VIOLATION"
    unchanged, merchant_block = controller.step(state(), NegotiationActor.MERCHANT_AGENT, 1_849_999)
    assert unchanged.current_round == 0 and merchant_block.reason_code == "MERCHANT_FLOOR_VIOLATION"


def test_max_rounds_fallback_and_expiry():
    controller = NegotiationController()
    current = state(max_rounds=1)
    current, decision = controller.step(current, NegotiationActor.BUYER_AGENT, 1_900_000)
    assert decision.decision == "FALLBACK" and current.final_agreed_price_minor == 1_999_900
    expired, decision = controller.step(
        state(expires_at=datetime.now(UTC) - timedelta(seconds=1)),
        NegotiationActor.BUYER_AGENT,
        1_900_000,
    )
    assert expired.status == NegotiationStatus.EXPIRED and decision.decision == "EXPIRE"


def relationships():
    return [
        {
            "source_product_id": "xm4",
            "offered_product_id": "case",
            "relationship_type": "CROSS_SELL",
            "active": True,
            "inventory_available": 5,
            "price_minor": 49_900,
            "currency": "INR",
            "name": "Protective Case",
        },
        {
            "source_product_id": "xm4",
            "offered_product_id": "xm5",
            "relationship_type": "UPSELL",
            "active": True,
            "inventory_available": 0,
            "price_minor": 2_449_900,
            "currency": "INR",
            "name": "XM5",
        },
    ]


def test_growth_permissions_stock_and_authority():
    engine = BasketGrowthEngine()
    assert engine.eligible(relationships(), "CROSS_SELL", False, 100_000, 1) == []
    cross = engine.eligible(relationships(), "CROSS_SELL", True, 100_000, 1)
    assert [item["offered_product_id"] for item in cross] == ["case"] and cross[0][
        "requires_confirmation"
    ]
    assert engine.eligible(relationships(), "UPSELL", True, 3_000_000, 1) == []
    with pytest.raises(ValueError, match="authority"):
        engine.validate_selection("fabricated-product", cross)


def test_accepted_cross_sell_full_unified_policy_recommit():
    context = UnifiedPolicyContext(
        final_price_minor=2_049_800,
        buyer_budget_minor=2_100_000,
        quantity=2,
        buyer_max_quantity=2,
        condition="NEW",
        allowed_conditions=["NEW"],
        brand="Sony",
        excluded_brands=[],
        mandate_expires_at=datetime.now(UTC) + timedelta(hours=1),
        mandate_status="ACTIVE",
        execution_count=0,
        max_executions=1,
        merchant_minimum_minor=1_899_900,
        base_price_minor=2_049_800,
        discount_minor=0,
        merchant_max_discount_minor=149_992,
        available_quantity=25,
        cart_currency="INR",
        mandate_currency="INR",
        auto_purchase_allowed=False,
        lines=[
            CartLineConstraint(
                product_id="xm4", quantity=1, available_quantity=20, condition="NEW", brand="Sony"
            ),
            CartLineConstraint(
                product_id="case",
                quantity=1,
                available_quantity=5,
                condition="NEW",
                brand="Sentinel",
            ),
        ],
    )
    decision = UnifiedPolicyService().evaluate(context)
    assert decision.solver_result == "SAT"
    assert "LINE_1_INVENTORY" in decision.assertions
