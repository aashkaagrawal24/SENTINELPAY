import base64
import hashlib
import inspect
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.core.config import Settings, get_settings
from app.main import app
from app.schemas.advanced import (
    BanditArm,
    BanditContext,
    MultiVerifierRequest,
    ProcurementOptimizeRequest,
    SignedAttestation,
    SupplierQuoteInput,
)
from app.schemas.security import UnifiedPolicyContext
from app.services import advanced_services
from app.services.advanced_services import (
    BudgetRangeProofService,
    ContextualBanditService,
    ExternalMarketService,
    MultiVerifierService,
    NegotiationSimulator,
    ProcurementOptimizer,
    StaticEvaluationConnector,
)
from app.services.security_kernel import SecurityKernel


def test_all_completed_advanced_feature_flags_default_on():
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_anon_key="anon",
        supabase_database_url="postgresql://example",
    )
    flags = [
        name
        for name in Settings.model_fields
        if name.startswith("feature_")
    ]
    assert len(flags) == 8
    assert all(getattr(settings, flag) is True for flag in flags)


def test_external_connector_capability_is_explicit_and_failure_hands_off():
    result = ExternalMarketService().search(
        StaticEvaluationConnector([], fail=True), "Sony headphones"
    )
    assert result["status"] == "FALLBACK"
    assert result["fallback"] == "HANDOFF"
    assert result["offers"] == []
    assert result["metrics"]["connector_success_rate"] == 0


@pytest.mark.anyio
async def test_feature_off_endpoint_fails_before_extension_execution():
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_anon_key="anon",
        supabase_database_url="postgresql://example",
        feature_contextual_bandit=False,
    )
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(uuid4(), None)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/advanced/bandit/select",
                json={
                    "context": {
                        "listing_age_days": 1,
                        "seller_type": "MERCHANT",
                        "category": "AUDIO",
                        "prior_rounds": 0,
                        "remaining_budget_minor": 100,
                        "fallback_available": False,
                    },
                    "arms": [],
                },
            )
        assert response.status_code == 404
        assert "core behavior is unchanged" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_extension_failure_does_not_change_security_kernel_authorization():
    context = UnifiedPolicyContext(
        final_price_minor=100,
        buyer_budget_minor=100,
        quantity=1,
        buyer_max_quantity=1,
        condition="NEW",
        allowed_conditions=["NEW"],
        mandate_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        mandate_status="ACTIVE",
        merchant_minimum_minor=90,
        base_price_minor=100,
        discount_minor=0,
        merchant_max_discount_minor=10,
        available_quantity=1,
        cart_currency="INR",
        mandate_currency="INR",
    )
    cart = {
        "merchant_id": "m",
        "mandate_id": "x",
        "currency": "INR",
        "subtotal_minor": 100,
        "discount_minor": 0,
        "shipping_minor": 0,
        "total_minor": 100,
        "delivery": {},
        "version": 1,
        "items": [],
    }
    before = SecurityKernel().authorize(context, cart, "same", "same")
    ExternalMarketService().search(StaticEvaluationConnector([], fail=True), "attack")
    after = SecurityKernel().authorize(context, cart, "same", "same")
    assert before == after
    assert after["outcome"] == "REQUIRE_APPROVAL"


def test_bandit_selects_strategy_without_modifying_numeric_authority():
    context = BanditContext(
        listing_age_days=45,
        seller_type="MERCHANT",
        category="HEADPHONES",
        prior_rounds=1,
        remaining_budget_minor=500_000,
        fallback_available=True,
    )
    result = ContextualBanditService().select(
        context,
        [
            BanditArm(action="AGGRESSIVE", pulls=10, cumulative_reward=50),
            BanditArm(action="BALANCED", pulls=0, cumulative_reward=0),
            BanditArm(action="FAST_CLOSE", pulls=10, cumulative_reward=40),
        ],
    )
    assert result["action"] == "BALANCED"
    assert result["authority_changes"] == {}
    assert ContextualBanditService().select(context, [])["action"] == "BALANCED"


def test_budget_range_proof_verifies_without_exposing_budget_and_tamper_fails():
    proof = BudgetRangeProofService.prove(2_500_000, 1_999_900)
    assert "budget" not in {
        key for key in proof if key not in {"budget_commitment"}
    }
    assert BudgetRangeProofService.verify(
        1_999_900, proof["budget_commitment"], proof
    )["verified"]
    tampered = deepcopy(proof)
    tampered["bit_proofs"][0]["responses"][0] = str(
        int(tampered["bit_proofs"][0]["responses"][0]) + 1
    )
    assert not BudgetRangeProofService.verify(
        1_999_900, tampered["budget_commitment"], tampered
    )["verified"]
    with pytest.raises(ValueError, match="insufficient"):
        BudgetRangeProofService.prove(100, 101)


def signed_attestation(
    verifier_id: str, payload_hash: str, decision: str = "APPROVE"
) -> SignedAttestation:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    unsigned = SignedAttestation(
        verifier_id=verifier_id,
        decision=decision,
        payload_hash=payload_hash,
        public_key=base64.b64encode(public_key).decode(),
        signature="placeholder",
        issued_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    signature = private_key.sign(MultiVerifierService.canonical(unsigned))
    return unsigned.model_copy(update={"signature": base64.b64encode(signature).decode()})


def test_multi_verifier_k_of_n_and_invalid_signature_fallback():
    payload_hash = hashlib.sha256(b"transaction").hexdigest()
    first = signed_attestation("MANDATE", payload_hash)
    second = signed_attestation("POLICY", payload_hash)
    request = MultiVerifierRequest(
        payload_hash=payload_hash,
        required_k=2,
        expected_verifiers=["MANDATE", "POLICY", "RISK"],
        attestations=[first, second],
    )
    approved = MultiVerifierService().evaluate(request)
    assert approved["status"] == "APPROVED"
    assert approved["security_kernel_still_required"] is True
    invalid = second.model_copy(update={"signature": base64.b64encode(b"invalid").decode()})
    denied = MultiVerifierService().evaluate(
        request.model_copy(update={"attestations": [first, invalid]})
    )
    assert denied["status"] == "DENIED" and denied["fallback"] == "DENY"


def procurement_request(max_budget: int = 1_000_000):
    vendors = [uuid4(), uuid4()]
    now = datetime.now(UTC)
    return ProcurementOptimizeRequest(
        required_quantity=10,
        max_budget_minor=max_budget,
        delivery_deadline=now + timedelta(days=7),
        approved_vendor_ids=vendors,
        quotes=[
            SupplierQuoteInput(
                quote_id=uuid4(), merchant_id=vendors[0], unit_price_minor=80_000,
                available_quantity=6, delivery_at=now + timedelta(days=3),
                vendor_risk_basis_points=100, merchant_minimum_quantity=2,
            ),
            SupplierQuoteInput(
                quote_id=uuid4(), merchant_id=vendors[1], unit_price_minor=85_000,
                available_quantity=8, delivery_at=now + timedelta(days=2),
                vendor_risk_basis_points=50, merchant_minimum_quantity=2,
            ),
        ],
    )


def test_b2b_optimizer_fills_quantity_under_budget_without_payment():
    result = ProcurementOptimizer().optimize(procurement_request())
    assert result["status"] == "SUCCESS"
    assert result["metrics"]["fill_rate"] >= 1
    assert result["metrics"]["cost_minor"] <= 1_000_000
    assert result["payment_created"] is False
    assert result["security_kernel_still_required"] is True
    failed = ProcurementOptimizer().optimize(procurement_request(max_budget=100))
    assert failed["status"] == "FALLBACK" and failed["allocations"] == []


def test_negotiation_simulator_is_reproducible_and_off_core_path():
    first = NegotiationSimulator().compare(42, 100, "BALANCED")
    second = NegotiationSimulator().compare(42, 100, "BALANCED")
    assert first == second
    assert first["provenance"] == "SIMULATED"
    assert first["core_transaction_path"] is False


def test_advanced_services_have_no_payment_service_dependency():
    source = inspect.getsource(advanced_services)
    assert "PaymentService" not in source
    assert "create_order" not in source


def test_phase10_migration_has_rls_for_every_advanced_table():
    migration = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "0010_advanced_extensions.py"
    ).read_text()
    tables = (
        "advanced_feature_runs",
        "external_offer_snapshots",
        "bandit_strategy_stats",
        "zk_budget_proofs",
        "multi_verifier_requests",
        "verifier_attestations",
        "procurement_rfqs",
        "supplier_quotes",
        "procurement_allocations",
        "negotiation_simulation_runs",
    )
    for table in tables:
        assert f"alter table public.{table} enable row level security" in migration
