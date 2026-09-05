from uuid import UUID, uuid4

from app.services.analytics_services import (
    AttributionCalculator,
    CampaignAssignmentService,
    RevenueAnalyticsService,
    SyntheticEvaluationService,
    safe_rate,
)


def test_stable_assignment_bucket_is_reproducible():
    mandate = UUID("10000000-0000-0000-0000-000000000001")
    campaign = UUID("20000000-0000-0000-0000-000000000001")
    first = CampaignAssignmentService.bucket(mandate, campaign)
    assert first == CampaignAssignmentService.bucket(mandate, campaign)
    assert 0 <= first <= 99


def test_control_receives_no_offer_and_treatment_does():
    assert CampaignAssignmentService.group(19, 20, True) == "CONTROL"
    assert CampaignAssignmentService.group(20, 20, True) == "TREATMENT"
    assert CampaignAssignmentService.group(0, 20, False) == "TREATMENT"


def test_only_successful_captured_real_transaction_counts_revenue():
    assert RevenueAnalyticsService.counts_as_real_revenue("SUCCESS", "CAPTURED")
    assert not RevenueAnalyticsService.counts_as_real_revenue("DENIED", "CAPTURED")
    assert not RevenueAnalyticsService.counts_as_real_revenue("SUCCESS", "FAILED")
    assert not RevenueAnalyticsService.counts_as_real_revenue(
        "SUCCESS", "CAPTURED", "SIMULATED"
    )


def test_controlled_formula_and_label_are_explicit():
    metric = AttributionCalculator.campaign(
        {
            "control_sessions": 20,
            "treatment_sessions": 80,
            "control_conversions": 4,
            "treatment_conversions": 24,
            "control_revenue_minor": 8_000_000,
            "treatment_revenue_minor": 50_400_000,
            "attributed_revenue_minor": 50_400_000,
            "discount_cost_minor": 2_400_000,
            "offers_served": 80,
            "gross_revenue_minor": 58_400_000,
            "upsell_revenue_minor": 0,
            "cross_sell_revenue_minor": 0,
        }
    )
    assert metric["control_conversion_rate"] == 0.2
    assert metric["treatment_conversion_rate"] == 0.3
    assert metric["incremental_revenue_estimate_minor"] == 18_400_000
    assert metric["attribution_label"] == "CONTROLLED EXPERIMENT ESTIMATE"


def test_without_control_only_attributed_label_is_used():
    metric = AttributionCalculator.campaign(
        {
            "control_sessions": 0,
            "treatment_sessions": 10,
            "control_conversions": 0,
            "treatment_conversions": 2,
            "control_revenue_minor": 0,
            "treatment_revenue_minor": 4_000_000,
            "attributed_revenue_minor": 4_000_000,
            "discount_cost_minor": 200_000,
        }
    )
    assert metric["incremental_revenue_estimate_minor"] is None
    assert metric["attribution_label"] == "ATTRIBUTED CAMPAIGN REVENUE"


def test_zero_denominators_are_safe():
    assert safe_rate(100, 0) == 0
    metric = AttributionCalculator.campaign({})
    assert metric["control_aov_minor"] == 0
    assert metric["revenue_per_discount_rupee"] == 0


def test_simulated_session_ids_make_generation_idempotent():
    merchant, campaign = uuid4(), uuid4()
    first = SyntheticEvaluationService.session_id(merchant, campaign, 42, 7)
    assert first == SyntheticEvaluationService.session_id(merchant, campaign, 42, 7)
    assert first != SyntheticEvaluationService.session_id(merchant, campaign, 43, 7)
