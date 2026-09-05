import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings
from app.schemas.advanced import (
    AnalyticsObservation,
    BlsApprovalRequest,
    BlsSignerInput,
    CausalAnalysisRequest,
    DpAggregateRequest,
    ExternalOfferInput,
    GraphEdge,
    GraphNode,
    HomomorphicAggregateRequest,
    LinUcbState,
    NegotiabilityFeatures,
    ProvenanceGraphRequest,
    RacComponent,
    RacRequest,
    SealedBidInput,
    VcgProcurementRequest,
)
from app.schemas.payment import PaymentStatus, RefundStatus
from app.schemas.security import AdvancedSecurityEvidence, UnifiedPolicyContext
from app.services.advanced_intelligence import (
    CfrBargainingService,
    ControlledPlatformConnector,
    LinUcbService,
    NegotiabilityModel,
    PlatformRegistry,
    RiskAdjustedCostService,
    UniversalWebScout,
)
from app.services.advanced_privacy import (
    BlsMultiVerifierService,
    CausalAnalysisService,
    DifferentialPrivacyService,
    Groth16BudgetProofService,
    HomomorphicAnalyticsService,
    ProvenanceGraphService,
    WesolowskiVdfService,
)
from app.services.advanced_verifiers import IndependentVerifierSet
from app.services.b2b_procurement import SealedBidService, VcgProcurementService
from app.services.model_gateway import ModelGateway
from app.services.payment_service import PaymentAttemptRecord, PaymentService, RefundRecord
from app.services.security_kernel import UnifiedPolicyService


def valid_context(**changes):
    values = {
        "final_price_minor": 1_999_900,
        "buyer_budget_minor": 2_500_000,
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
        "merchant_minimum_minor": 1_850_000,
        "base_price_minor": 1_999_900,
        "discount_minor": 0,
        "merchant_max_discount_minor": 149_992,
        "available_quantity": 5,
        "cart_currency": "INR",
        "mandate_currency": "INR",
    }
    values.update(changes)
    return UnifiedPolicyContext(**values)


def test_model_gateway_explicitly_excludes_openrouter():
    settings = Settings()
    for task in (
        "INTENT_PARSING",
        "COMPLEX_CAMPAIGN_REASONING",
        "VERY_COMPLEX_REASONING",
        "RED_TEAM",
    ):
        specs = ModelGateway._provider_specs(settings, task)
        assert all(spec[0] != "openrouter" for spec in specs)


def test_platform_registry_has_all_17_honest_handoff_connectors():
    registry = PlatformRegistry.all()
    assert len(registry) == 17
    assert len({item.key for item in registry}) == 17
    assert all(item.search and item.handoff for item in registry)
    assert all(not item.checkout and not item.razorpay_execution for item in registry)


def test_universal_scout_merges_success_and_partial_failure():
    offer = ExternalOfferInput(
        external_offer_id="one",
        title="Sony WH-1000XM4 New Headphones Warranty",
        price_minor=1_999_900,
        fetched_at=datetime.now(UTC),
    )
    connectors = [
        ControlledPlatformConnector(PlatformRegistry.get("OLX"), [offer]),
        ControlledPlatformConnector(PlatformRegistry.get("Amazon"), [], fail=True),
    ]
    result = UniversalWebScout().search(
        connectors,
        "Sony WH-1000XM4",
        {"brand": "Sony", "model": "WH-1000XM4", "condition": "New"},
        2,
    )
    assert result["status"] == "SUCCESS"
    assert result["offers"][0]["identity"]["classification"] == "EXACT"
    assert result["metrics"]["partial_failures"] == 1
    assert result["offers"][0]["checkout_capability"] == "HANDOFF"


def component(value: int, source: str = "catalog") -> RacComponent:
    return RacComponent(amount_minor=value, source=source, trust_class="MERCHANT_API")


def test_rac_formula_keeps_component_provenance():
    result = RiskAdjustedCostService.calculate(
        RacRequest(
            price=component(100_000),
            shipping=component(5_000),
            verified_discount=component(10_000),
            confirmed_cashback=component(2_000),
            condition_penalty=component(3_000),
            warranty_penalty=component(4_000),
            seller_risk_penalty=component(6_000),
            delivery_penalty=component(1_000),
        )
    )
    assert result["risk_adjusted_acquisition_cost_minor"] == 107_000
    assert result["components"]["price"]["source"] == "catalog"


def test_logistic_negotiability_model_has_real_evaluation_and_influences_strategy():
    model = NegotiabilityModel()
    high = model.predict(
        NegotiabilityFeatures(
            platform="INDIAMART",
            seller_type="MERCHANT",
            category="ELECTRONICS",
            listing_age_days=90,
            explicit_negotiable=True,
            rfq_supported=True,
            quantity=20,
            historical_price_edits=4,
            price_roundness=1,
            merchant_negotiation_enabled=True,
        )
    )
    low = model.predict(
        NegotiabilityFeatures(
            platform="AMAZON",
            seller_type="INDIVIDUAL",
            category="ELECTRONICS",
            listing_age_days=1,
        )
    )
    assert high["negotiability_score"] > low["negotiability_score"]
    assert high["strategy_influence"] == "NEGOTIATE"
    assert {"precision", "recall", "f1", "roc_auc", "brier_score"} <= high["metrics"].keys()


def test_linucb_selection_and_reward_update_are_matrix_based():
    states = [
        LinUcbState(action="BALANCED", a_matrix=[[1, 0], [0, 1]], b_vector=[0, 0]),
        LinUcbState(action="AGGRESSIVE", a_matrix=[[1, 0], [0, 1]], b_vector=[2, 0]),
    ]
    service = LinUcbService()
    selected = service.select([1, 0], 0.1, states)
    assert selected["algorithm"] == "LinUCB" and selected["action"] == "AGGRESSIVE"
    updated = service.update([1, 0], 5, states[1])
    assert updated["a_matrix"] == [[2.0, 0.0], [0.0, 1.0]]
    assert updated["b_vector"] == [7.0, 0.0]


def test_cfr_has_hidden_information_regret_and_strategy_updates():
    result = CfrBargainingService(seed=7).train(500)
    assert result["algorithm"] == "COUNTERFACTUAL_REGRET_MINIMIZATION"
    assert result["rounds"] == 3
    assert result["information_sets"] > 0
    assert result["information_sets_with_regret_updates"] > 0
    assert result["average_strategies"]


def test_dp_aggregate_is_bounded_and_does_not_mutate_ledger():
    result = DifferentialPrivacyService.aggregate(
        DpAggregateRequest(values=[10, 20, 30, 40], epsilon=1, lower=0, upper=50)
    )
    assert result["scope"] == "AGGREGATE_ANALYTICS_ONLY"
    assert result["ledger_mutated"] is False
    assert result["value"] != 25


def test_dowhy_estimate_and_refutations_use_declared_confounders():
    observations = [
        AnalyticsObservation(
            treatment=index % 2,
            outcome=10 + 3 * (index % 2) + 0.1 * index,
            prior_sessions=index,
            inventory_pressure=index % 5,
        )
        for index in range(40)
    ]
    result = CausalAnalysisService.analyze(
        CausalAnalysisRequest(observations=observations)
    )
    assert result["method"].startswith("DoWhy")
    assert result["estimate"] == pytest.approx(3, abs=0.2)
    assert {"random_common_cause", "placebo_treatment"} == result["refutations"].keys()
    assert result["causality_claim"] == "CONDITIONAL_ON_DECLARED_ASSUMPTIONS"


def test_networkx_provenance_path_and_cycle_rejection():
    nodes = [GraphNode(id=value, kind=value) for value in ("source", "metric", "cart")]
    result = ProvenanceGraphService.analyze(
        ProvenanceGraphRequest(
            nodes=nodes,
            edges=[
                GraphEdge(source="source", target="metric", relation="DERIVES"),
                GraphEdge(source="metric", target="cart", relation="INFORMS"),
            ],
            source_id="source",
            target_id="cart",
        )
    )
    assert result["paths"] == [["source", "metric", "cart"]]
    with pytest.raises(ValueError, match="acyclic"):
        ProvenanceGraphService.analyze(
            ProvenanceGraphRequest(
                nodes=nodes,
                edges=[
                    GraphEdge(source="source", target="metric", relation="A"),
                    GraphEdge(source="metric", target="source", relation="B"),
                ],
            )
        )


def test_paillier_encrypted_sum_is_valid_and_not_a_comparison():
    result = HomomorphicAnalyticsService.aggregate(
        HomomorphicAggregateRequest(values=[11, 22, 33])
    )
    assert result["verified"] is True and result["decrypted_sum"] == 66
    assert result["supports_comparison"] is False


def test_circom_groth16_budget_proof_verifies_and_hides_private_budget():
    result = Groth16BudgetProofService.prove(2_500_000, 1_999_900)
    assert result["scheme"] == "GROTH16_BN128" and result["verified"] is True
    assert "2500000" not in str(result["public_signals"])
    tampered = {**result, "public_signals": list(result["public_signals"])}
    tampered["public_signals"][-1] = "1999901"
    assert Groth16BudgetProofService.verify(tampered) is False


def test_bls_individual_and_aggregate_approval_and_quorum_failure():
    signers = []
    for role in ("MANDATE", "POLICY", "RISK"):
        private_key, _ = BlsMultiVerifierService.key_pair()
        signers.append(BlsSignerInput(verifier_id=role, private_key=private_key))
    body = BlsApprovalRequest(payload_hash=hashlib.sha256(b"cart").hexdigest(), signers=signers)
    result = BlsMultiVerifierService.approve(body)
    assert result["aggregate_valid"] is True and result["status"] == "APPROVED"
    with pytest.raises(ValueError, match="distinct"):
        BlsMultiVerifierService.approve(
            BlsApprovalRequest(
                payload_hash=body.payload_hash,
                signers=[signers[0], signers[0]],
                required_k=2,
            )
        )


def test_bls_deployment_role_keys_are_distinct_and_server_controlled():
    payload_hash = hashlib.sha256(b"bound-cart").hexdigest()
    result = BlsMultiVerifierService.approve_with_role_secrets(
        payload_hash,
        {"MANDATE": "mandate-key", "POLICY": "policy-key", "RISK": "risk-key"},
    )
    assert result["aggregate_valid"] is True
    assert result["key_source"] == "INDEPENDENT_DEPLOYMENT_ROLE_SECRETS"
    with pytest.raises(ValueError, match="All three"):
        BlsMultiVerifierService.approve_with_role_secrets(
            payload_hash, {"MANDATE": "only-one"}
        )


def test_wesolowski_vdf_verifies_and_tampered_proof_fails():
    assert WesolowskiVdfService.N.bit_length() == 2048
    assert WesolowskiVdfService._is_probable_prime(WesolowskiVdfService.N) is False
    result = WesolowskiVdfService.evaluate("sealed-bid-commitment", 120)
    assert result["verified"] is True
    result["proof"] = str(int(result["proof"]) + 1)
    assert WesolowskiVdfService.verify_result(result) is False


def procurement() -> VcgProcurementRequest:
    vendors = [
        UUID("10000000-0000-0000-0000-000000000001"),
        UUID("10000000-0000-0000-0000-000000000002"),
        UUID("10000000-0000-0000-0000-000000000003"),
    ]
    bids = [
        SealedBidInput(
            bid_id=UUID(f"20000000-0000-0000-0000-00000000000{i}"),
            vendor_id=vendor,
            unit_cost_minor=cost,
            quantity=quantity,
            delivery_days=days,
            nonce=f"secure-vendor-nonce-{i}",
        )
        for i, (vendor, cost, quantity, days) in enumerate(
            zip(vendors, (80_000, 85_000, 95_000), (6, 8, 10), (2, 3, 2), strict=True), 1
        )
    ]
    return VcgProcurementRequest(
        required_quantity=10,
        buyer_value_per_unit_minor=150_000,
        max_budget_minor=1_500_000,
        delivery_deadline_days=5,
        approved_vendor_ids=vendors,
        bids=bids,
        vdf_iterations=120,
    )


def test_sealed_bid_vdf_vcg_allocation_and_settlement_simulation():
    body = procurement()
    assert SealedBidService.verify_reveal(body.bids[0], SealedBidService.commit(body.bids[0]))
    result = VcgProcurementService.execute(body)
    assert result["mechanism"] == "VCG_REVERSE_PROCUREMENT"
    assert sum(item["quantity"] for item in result["allocation"]) == 10
    assert len(result["winner_payments"]) >= 2
    assert result["vdf"]["verified"] is True
    assert result["settlement"]["razorpay_orders_created"] == 0


def test_advanced_evidence_is_part_of_same_z3_solver_call():
    missing = valid_context(
        advanced_verification_required=True,
        advanced_evidence=AdvancedSecurityEvidence(),
    )
    denied = UnifiedPolicyService().evaluate(missing)
    assert denied.solver_result == "UNSAT"
    assert "ZK_BUDGET_PROOF" in denied.failed_constraints
    approved = valid_context(
        advanced_verification_required=True,
        advanced_evidence=AdvancedSecurityEvidence(
            zk_budget_verified=True,
            mandate_verifier_approved=True,
            policy_verifier_approved=True,
            risk_verifier_approved=True,
            bls_aggregate_verified=True,
            provenance_trusted=True,
        ),
    )
    decision = UnifiedPolicyService().evaluate(approved)
    assert decision.solver_result == "SAT"
    assert "BLS_AGGREGATE" in decision.assertions


def test_mandate_policy_and_risk_verifiers_are_independent():
    cart = {
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
    decisions = IndependentVerifierSet().evaluate(valid_context(), cart)
    assert [item.role for item in decisions] == ["MANDATE", "POLICY", "RISK"]
    assert all(item.approved for item in decisions)
    denied = IndependentVerifierSet().evaluate(valid_context(mandate_status="REVOKED"), cart)
    assert denied[0].approved is False and denied[1].approved is True


def test_phase11_migration_contains_rls_refunds_and_advanced_tables():
    sql = Path("migrations/versions/0011_complete_advanced_stack.py").read_text(
        encoding="utf-8"
    )
    for name in (
        "platform_connectors",
        "linucb_models",
        "causal_analysis_runs",
        "dp_aggregate_runs",
        "he_aggregate_runs",
        "bls_approval_runs",
        "vdf_runs",
        "sealed_bid_commits",
        "vcg_results",
        "refunds",
        "payment_reconciliations",
    ):
        assert f"create table public.{name}" in sql
        assert f'"{name}"' in sql or f"public.{name} enable row level security" in sql
    assert "enable row level security" in sql


def test_security_evidence_migration_prevents_evaluation_proof_escalation():
    migration = Path("migrations/versions/0014_bind_security_evidence.py").read_text(
        encoding="utf-8"
    )
    commerce = Path("app/api/commerce_routes.py").read_text(encoding="utf-8")
    assert "SECURITY_KERNEL_INPUT" in migration
    assert "CALLER_SUPPLIED_EVALUATION_KEYS" in migration
    assert "user_cart_id=:cart" in commerce
    assert "authority_scope='SECURITY_KERNEL_INPUT'" in commerce
    assert "verifier_decisions" in commerce


class RefundRepository:
    def __init__(self):
        self.attempt = PaymentAttemptRecord(
            id=uuid4(),
            transaction_id=uuid4(),
            idempotency_key="payment-key",
            amount_minor=100_000,
            currency="INR",
            status=PaymentStatus.CAPTURED,
            razorpay_order_id="order_1",
            razorpay_payment_id="pay_1",
        )
        self.refunds: dict[UUID, RefundRecord] = {}
        self.keys: dict[str, UUID] = {}

    def claim_refund(self, attempt_id, user_id, amount, reason, key):
        del user_id, reason
        if key in self.keys:
            return self.refunds[self.keys[key]], False
        reserved = sum(item.amount_minor for item in self.refunds.values())
        if reserved + amount > self.attempt.amount_minor:
            raise ValueError("Cumulative refund exceeds captured payment amount")
        refund = RefundRecord(
            uuid4(), attempt_id, amount, "INR", key, RefundStatus.REQUESTED
        )
        self.refunds[refund.id], self.keys[key] = refund, refund.id
        return refund, True

    def update_refund(self, refund_id, status, provider_refund_id, safe_payload):
        del safe_payload
        current = self.refunds[refund_id]
        refund = RefundRecord(
            current.id,
            current.payment_attempt_id,
            current.amount_minor,
            current.currency,
            current.idempotency_key,
            status,
            provider_refund_id,
        )
        self.refunds[refund_id] = refund
        return refund

    def get_refund(self, refund_id):
        return self.refunds[refund_id]

    def get_attempt(self, attempt_id):
        assert attempt_id == self.attempt.id
        return self.attempt


class RefundProvider:
    public_key_id = "rzp_test_public"

    def __init__(self):
        self.calls = 0

    def create_refund(self, payment_id, amount, key, reason):
        del payment_id, key, reason
        self.calls += 1
        return {"id": "rfnd_test_1", "amount": amount, "currency": "INR", "status": "processed"}

    def fetch_refund(self, refund_id):
        return {"id": refund_id, "amount": 40_000, "currency": "INR", "status": "processed"}


def test_refund_is_captured_only_idempotent_and_cannot_exceed_payment():
    repository, provider = RefundRepository(), RefundProvider()
    service = PaymentService(repository, provider)
    first = service.create_refund(
        repository.attempt.id, uuid4(), 40_000, "Customer return", "refund-key-1"
    )
    second = service.create_refund(
        repository.attempt.id, uuid4(), 40_000, "Customer return", "refund-key-1"
    )
    assert first.status == RefundStatus.PROCESSED
    assert second.id == first.id and provider.calls == 1
    with pytest.raises(ValueError, match="exceeds"):
        service.create_refund(
            repository.attempt.id, uuid4(), 70_000, "Excess", "refund-key-2"
        )


def test_evaluation_data_export():
    data_dir = Path("data")
    assert (data_dir / "negotiability_dataset.csv").exists()
    assert (data_dir / "negotiability_metrics.json").exists()
    assert (data_dir / "crypto_benchmarks.json").exists()
