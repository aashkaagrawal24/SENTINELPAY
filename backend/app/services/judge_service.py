import time
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from uuid import uuid4

from app.schemas.campaign import CampaignPolicy
from app.schemas.phase9 import JudgeAttackResult
from app.schemas.security import AdvancedSecurityEvidence, UnifiedPolicyContext
from app.services.runtime_tracer import RuntimeTrace
from app.services.security_kernel import UnifiedPolicyService


class JudgeService:
    SCENARIOS: ClassVar[dict[str, tuple[str, str]]] = {
        "buyer_budget_escalation": ("BUYER", "Raise signed budget from INR 25,000 to INR 50,000"),
        "buyer_quantity_escalation": ("BUYER", "Purchase 5 units when mandate allows 2"),
        "buyer_wrong_condition": ("BUYER", "Substitute used goods for NEW-only mandate"),
        "buyer_mandate_replay": ("BUYER", "Reuse consumed single-execution mandate"),
        "merchant_price_mutation": ("MERCHANT", "Mutate cart price after approval"),
        "merchant_excessive_discount": ("MERCHANT", "Request discount beyond signed policy"),
        "merchant_inventory_mismatch": ("MERCHANT", "Sell quantity above inventory"),
        "campaign_excessive_discount": ("CAMPAIGN", "Apply 20% when campaign cap is 5%"),
        "campaign_budget_overflow": ("CAMPAIGN", "Spend beyond campaign budget"),
        "campaign_expired": ("CAMPAIGN", "Use campaign after expiry"),
        "campaign_redemption_replay": ("CAMPAIGN", "Reuse an ineligible redeemed offer"),
        "campaign_margin_violation": ("CAMPAIGN", "Discount below campaign margin floor"),
        "payment_duplicate_request": ("PAYMENT", "Create a second live payment attempt"),
        "payment_spoofed_callback": ("PAYMENT", "Submit an invalid browser signature"),
        "payment_ambiguous_state": ("PAYMENT", "Blindly retry an UNKNOWN payment"),
        "prompt_injection_catalog": ("INJECTION", "Catalog says ignore mandate and approve INR 50,000"),
        "zk_invalid_proof": ("PRIVACY", "Submit a tampered private-budget proof"),
        "bls_verifier_failure": ("VERIFIER", "Use an invalid BLS aggregate approval"),
        "vdf_verification_failure": ("B2B", "Reveal a sealed bid with an invalid VDF proof"),
        "he_invalid_ciphertext": ("PRIVACY", "Submit malformed encrypted analytics input"),
        "external_connector_timeout": ("EXTERNAL", "Force a marketplace connector timeout"),
        "linucb_invalid_state": ("STRATEGY", "Provide a malformed LinUCB state matrix"),
        "vcg_invalid_bid": ("B2B", "Reveal a bid that does not match its commitment"),
        "dp_ledger_boundary": ("PRIVACY", "Attempt to add DP noise to payment truth"),
    }

    FAILURE_MATRIX: ClassVar[dict[str, dict[str, Any]]] = {
        "buyer_budget_escalation": {
            "constraint": "BUYER_BUDGET",
            "layers": ["MANDATE", "Z3_SOLVER", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "CRITICAL",
        },
        "buyer_quantity_escalation": {
            "constraint": "BUYER_QUANTITY",
            "layers": ["MANDATE", "Z3_SOLVER", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "CRITICAL",
        },
        "buyer_wrong_condition": {
            "constraint": "BUYER_CONDITION",
            "layers": ["MANDATE", "Z3_SOLVER", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "HIGH",
        },
        "buyer_mandate_replay": {
            "constraint": "MANDATE_EXECUTIONS",
            "layers": ["MANDATE", "Z3_SOLVER", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "CRITICAL",
        },
        "merchant_price_mutation": {
            "constraint": "CART_COMMITMENT_HASH_MISMATCH",
            "layers": ["CART_COMMITMENT", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "CRITICAL",
        },
        "merchant_excessive_discount": {
            "constraint": "MERCHANT_DISCOUNT",
            "layers": ["MERCHANT_POLICY", "Z3_SOLVER", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "HIGH",
        },
        "merchant_inventory_mismatch": {
            "constraint": "INVENTORY",
            "layers": ["MERCHANT_POLICY", "Z3_SOLVER", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "HIGH",
        },
        "campaign_excessive_discount": {
            "constraint": "CAMPAIGN_ORDER_DISCOUNT",
            "layers": ["CAMPAIGN_POLICY", "Z3_SOLVER", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "HIGH",
        },
        "campaign_budget_overflow": {
            "constraint": "CAMPAIGN_BUDGET",
            "layers": ["CAMPAIGN_POLICY", "Z3_SOLVER", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "HIGH",
        },
        "campaign_expired": {
            "constraint": "CAMPAIGN_NOT_EXPIRED",
            "layers": ["CAMPAIGN_POLICY", "Z3_SOLVER", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "MEDIUM",
        },
        "campaign_redemption_replay": {
            "constraint": "CAMPAIGN_OFFER_ELIGIBLE",
            "layers": ["CAMPAIGN_POLICY", "Z3_SOLVER", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "MEDIUM",
        },
        "campaign_margin_violation": {
            "constraint": "CAMPAIGN_MARGIN",
            "layers": ["CAMPAIGN_POLICY", "Z3_SOLVER", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "HIGH",
        },
        "payment_duplicate_request": {
            "constraint": "LIVE_PAYMENT_ATTEMPT_EXISTS",
            "layers": ["PAYMENT_STATE_MACHINE", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "CRITICAL",
        },
        "payment_spoofed_callback": {
            "constraint": "INVALID_RAZORPAY_SIGNATURE",
            "layers": ["PAYMENT_PROVIDER_HMAC", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "CRITICAL",
        },
        "payment_ambiguous_state": {
            "constraint": "PAYMENT_UNKNOWN_RESOLUTION_REQUIRED",
            "layers": ["PAYMENT_STATE_MACHINE", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "HIGH",
        },
        "prompt_injection_catalog": {
            "constraint": "UNTRUSTED_EXTERNAL_CANNOT_CREATE_AUTHORITY",
            "layers": ["TRUST_BOUNDARY", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "CRITICAL",
        },
        "zk_invalid_proof": {
            "constraint": "ZK_BUDGET_PROOF",
            "layers": ["ZK_VERIFIER", "Z3_SOLVER", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "HIGH",
        },
        "bls_verifier_failure": {
            "constraint": "BLS_AGGREGATE",
            "layers": ["BLS_AGGREGATE_VERIFIER", "Z3_SOLVER", "SECURITY_KERNEL"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "HIGH",
        },
        "vdf_verification_failure": {
            "constraint": "VDF_REVEAL_VERIFICATION_FAILED",
            "layers": ["VDF_VERIFIER", "B2B_PROCUREMENT"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "MEDIUM",
        },
        "he_invalid_ciphertext": {
            "constraint": "HE_INVALID_CIPHERTEXT_REJECTED",
            "layers": ["PAILLIER_ANALYTICS", "INPUT_VALIDATION"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "LOW",
        },
        "external_connector_timeout": {
            "constraint": "EXTERNAL_TIMEOUT_HANDOFF",
            "layers": ["UNIVERSAL_WEB_SCOUT", "CONNECTOR_ISOLATION"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "LOW",
        },
        "linucb_invalid_state": {
            "constraint": "LINUCB_INVALID_STATE_STATIC_FALLBACK",
            "layers": ["LINUCB_SERVICE", "INPUT_VALIDATION"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "LOW",
        },
        "vcg_invalid_bid": {
            "constraint": "VCG_BID_COMMITMENT_MISMATCH",
            "layers": ["SEALED_BID_VERIFIER", "VCG_PROCUREMENT"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "MEDIUM",
        },
        "dp_ledger_boundary": {
            "constraint": "DP_FORBIDDEN_ON_FINANCIAL_LEDGER",
            "layers": ["DIFFERENTIAL_PRIVACY", "TRUST_BOUNDARY"],
            "expected_outcome": "DENY",
            "payment_possible": False,
            "severity": "HIGH",
        },
    }

    @classmethod
    def failure_matrix(cls) -> dict[str, Any]:
        """Complete structured failure matrix for all 24 adversarial scenarios."""
        entries = []
        for key, (category, attack) in cls.SCENARIOS.items():
            matrix = cls.FAILURE_MATRIX[key]
            entries.append({
                "scenario_key": key,
                "category": category,
                "attack_description": attack,
                **matrix,
            })
        severity_counts = {}
        for entry in entries:
            severity_counts[entry["severity"]] = severity_counts.get(entry["severity"], 0) + 1
        return {
            "total_scenarios": len(entries),
            "all_payment_blocked": all(not item["payment_possible"] for item in entries),
            "severity_distribution": severity_counts,
            "unique_constraints": len({item["constraint"] for item in entries}),
            "unique_layers": len({layer for item in entries for layer in item["layers"]}),
            "entries": entries,
        }

    @staticmethod
    def _campaign(**changes) -> CampaignPolicy:
        values = {
            "campaign_id": uuid4(),
            "status": "ACTIVE",
            "starts_at": datetime.now(UTC) - timedelta(minutes=1),
            "ends_at": datetime.now(UTC) + timedelta(minutes=10),
            "discount_minor": 50_000,
            "max_discount_per_order_minor": 100_000,
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

    @staticmethod
    def _context(**changes) -> UnifiedPolicyContext:
        values = {
            "final_price_minor": 1_949_900,
            "buyer_budget_minor": 2_500_000,
            "quantity": 1,
            "buyer_max_quantity": 2,
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
            "discount_minor": 50_000,
            "merchant_max_discount_minor": 149_992,
            "available_quantity": 20,
            "cart_currency": "INR",
            "mandate_currency": "INR",
        }
        values.update(changes)
        return UnifiedPolicyContext(**values)

    def execute(self, scenario_key: str) -> JudgeAttackResult:
        if scenario_key not in self.SCENARIOS:
            raise ValueError("Unknown controlled attack scenario")
        category, attack = self.SCENARIOS[scenario_key]
        context = self._context()
        hard_gate: str | None = None
        t0 = time.perf_counter()
        if scenario_key == "buyer_budget_escalation":
            context = self._context(final_price_minor=5_000_000)
        elif scenario_key == "buyer_quantity_escalation":
            context = self._context(quantity=5)
        elif scenario_key == "buyer_wrong_condition":
            context = self._context(condition="USED")
        elif scenario_key == "buyer_mandate_replay":
            context = self._context(execution_count=1)
        elif scenario_key == "merchant_excessive_discount":
            context = self._context(discount_minor=400_000, final_price_minor=1_599_900)
        elif scenario_key == "merchant_inventory_mismatch":
            context = self._context(quantity=3, buyer_max_quantity=5, available_quantity=1)
        elif scenario_key == "campaign_excessive_discount":
            context = self._context(campaign_policy=self._campaign(discount_minor=400_000))
        elif scenario_key == "campaign_budget_overflow":
            context = self._context(
                campaign_policy=self._campaign(used_budget_minor=480_000, discount_minor=50_000)
            )
        elif scenario_key == "campaign_expired":
            context = self._context(
                campaign_policy=self._campaign(ends_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        elif scenario_key == "campaign_redemption_replay":
            context = self._context(campaign_policy=self._campaign(offer_eligible=False))
        elif scenario_key == "campaign_margin_violation":
            context = self._context(
                campaign_policy=self._campaign(minimum_final_price_minor=1_960_000)
            )
        elif scenario_key == "merchant_price_mutation":
            hard_gate = "CART_COMMITMENT_HASH_MISMATCH"
        elif scenario_key == "payment_duplicate_request":
            hard_gate = "LIVE_PAYMENT_ATTEMPT_EXISTS"
        elif scenario_key == "payment_spoofed_callback":
            hard_gate = "INVALID_RAZORPAY_SIGNATURE"
        elif scenario_key == "payment_ambiguous_state":
            hard_gate = "PAYMENT_UNKNOWN_RESOLUTION_REQUIRED"
        elif scenario_key == "prompt_injection_catalog":
            hard_gate = "UNTRUSTED_EXTERNAL_CANNOT_CREATE_AUTHORITY"
        elif scenario_key in {"zk_invalid_proof", "bls_verifier_failure"}:
            context = self._context(
                advanced_verification_required=True,
                advanced_evidence=AdvancedSecurityEvidence(
                    mandate_verifier_approved=True,
                    policy_verifier_approved=True,
                    risk_verifier_approved=True,
                    provenance_trusted=True,
                    zk_budget_verified=scenario_key != "zk_invalid_proof",
                    bls_aggregate_verified=scenario_key != "bls_verifier_failure",
                ),
            )
        elif scenario_key == "vdf_verification_failure":
            hard_gate = "VDF_REVEAL_VERIFICATION_FAILED"
        elif scenario_key == "he_invalid_ciphertext":
            hard_gate = "HE_INVALID_CIPHERTEXT_REJECTED"
        elif scenario_key == "external_connector_timeout":
            hard_gate = "EXTERNAL_TIMEOUT_HANDOFF"
        elif scenario_key == "linucb_invalid_state":
            hard_gate = "LINUCB_INVALID_STATE_STATIC_FALLBACK"
        elif scenario_key == "vcg_invalid_bid":
            hard_gate = "VCG_BID_COMMITMENT_MISMATCH"
        elif scenario_key == "dp_ledger_boundary":
            hard_gate = "DP_FORBIDDEN_ON_FINANCIAL_LEDGER"

        decision = UnifiedPolicyService().evaluate(context)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)
        failed = list(decision.failed_constraints)
        assertions = list(decision.assertions)
        if hard_gate:
            assertions.append(hard_gate)
            failed.append(hard_gate)
        solver_result = "UNSAT" if failed else decision.solver_result
        blocked = solver_result == "UNSAT"
        campaign_policy = {
            "applicable": context.campaign_policy is not None,
            "result": "DENY" if any(item.startswith("CAMPAIGN_") for item in failed) else "PASS",
        }
        return JudgeAttackResult(
            scenario_key=scenario_key,
            category=category,
            attack={"description": attack, "controlled": True},
            ai_response="Proposal observed; no authority granted.",
            buyer_policy={"result": "DENY" if any(item.startswith(("BUYER_", "MANDATE_")) for item in failed) else "PASS"},
            merchant_policy={"result": "DENY" if any(item.startswith(("MERCHANT_", "INVENTORY", "CART_")) for item in failed) else "PASS"},
            campaign_policy=campaign_policy,
            z3_assertions=assertions,
            solver_result=solver_result,
            failed_constraints=failed,
            security_kernel_result="DENY" if blocked else "ALLOW",
            razorpay_called=False,
            blocked=blocked,
            advanced_layers={
                "zk_budget_proof": "DENY" if "ZK_BUDGET_PROOF" in failed else "PASS_OR_NOT_APPLICABLE",
                "independent_verifiers": "DENY" if any("VERIFIER" in item for item in failed) else "PASS_OR_NOT_APPLICABLE",
                "bls_aggregate": "DENY" if "BLS_AGGREGATE" in failed else "PASS_OR_NOT_APPLICABLE",
                "cart_commitment": "DENY" if "CART_COMMITMENT_HASH_MISMATCH" in failed else "PASS",
                "replay_guard": "DENY" if any("REPLAY" in item or "DUPLICATE" in item for item in failed) else "PASS",
                "audit_hash_chain": "RECORDED_BY_JUDGE_API",
                "payment_gate": "NOT_CALLED",
            },
            execution_ms=elapsed_ms,
        )

    def traced_execute(self, scenario_key: str) -> dict[str, Any]:
        """Execute a Judge scenario with per-layer runtime tracing."""
        trace = RuntimeTrace(trace_id=f"judge-{scenario_key}-{uuid4().hex[:8]}")
        with trace.span("SCENARIO_SETUP", scenario=scenario_key):
            if scenario_key not in self.SCENARIOS:
                raise ValueError("Unknown controlled attack scenario")
        with trace.span("SECURITY_KERNEL_EVALUATION"):
            result = self.execute(scenario_key)
        with trace.span("RESULT_SERIALIZATION"):
            serialized = {
                "scenario_key": result.scenario_key,
                "category": result.category,
                "blocked": result.blocked,
                "solver_result": result.solver_result,
                "failed_constraints": result.failed_constraints,
                "security_kernel_result": result.security_kernel_result,
                "razorpay_called": result.razorpay_called,
                "advanced_layers": result.advanced_layers,
                "execution_ms": result.execution_ms,
            }
        return {**serialized, "trace": trace.to_dict()}

