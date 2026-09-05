from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from app.main import app
from app.services.audit_ledger import ZERO_HASH, AuditLedgerService
from app.services.judge_service import JudgeService
from app.services.provenance_service import ProvenanceService


def chain_rows(payloads: list[dict]) -> list[dict]:
    rows = []
    previous = ZERO_HASH
    for sequence, payload in enumerate(payloads, 1):
        payload_hash, current = AuditLedgerService.hashes(previous, payload)
        rows.append(
            {
                "chain_sequence": sequence,
                "canonical_payload": payload,
                "payload_hash": payload_hash,
                "previous_event_hash": previous,
                "current_event_hash": current,
            }
        )
        previous = current
    return rows


def test_provenance_model_and_external_sources_cannot_create_authority():
    for trust in ("MODEL_INFERRED", "UNTRUSTED_EXTERNAL", "SYSTEM_DERIVED"):
        with pytest.raises(PermissionError, match="cannot create financial authority"):
            ProvenanceService.validate_authority(trust, True)
    ProvenanceService.validate_authority("USER_SIGNED", True)
    ProvenanceService.validate_authority("RAZORPAY_VERIFIED", True)


def test_hash_chain_verifies_and_detects_payload_tampering():
    rows = chain_rows([{"event": "MANDATE_CREATED"}, {"event": "POLICY_VERIFIED"}])
    assert AuditLedgerService.verify_rows(rows)["valid"] is True
    tampered = deepcopy(rows)
    tampered[0]["canonical_payload"]["event"] = "MUTATED"
    result = AuditLedgerService.verify_rows(tampered)
    assert result == {"valid": False, "reason": "PAYLOAD_MUTATION", "at_sequence": 1}


def test_hash_chain_detects_missing_link():
    rows = chain_rows([{"event": "A"}, {"event": "B"}, {"event": "C"}])
    assert AuditLedgerService.verify_rows([rows[0], rows[2]])["reason"] == "MISSING_LINK"


def test_all_controlled_critical_attacks_are_blocked_before_payment():
    results = [JudgeService().execute(key) for key in JudgeService.SCENARIOS]
    assert len(results) >= 8
    assert all(result.security_kernel_result == "DENY" for result in results)
    assert all(result.razorpay_called is False for result in results)
    assert sum(not result.blocked and result.razorpay_called for result in results) == 0


@pytest.mark.parametrize(
    ("scenario", "constraint"),
    [
        ("merchant_price_mutation", "CART_COMMITMENT_HASH_MISMATCH"),
        ("campaign_expired", "CAMPAIGN_NOT_EXPIRED"),
        ("payment_duplicate_request", "LIVE_PAYMENT_ATTEMPT_EXISTS"),
        ("payment_ambiguous_state", "PAYMENT_UNKNOWN_RESOLUTION_REQUIRED"),
        ("prompt_injection_catalog", "UNTRUSTED_EXTERNAL_CANNOT_CREATE_AUTHORITY"),
    ],
)
def test_graceful_and_injection_failures_explain_hard_gate(scenario, constraint):
    result = JudgeService().execute(scenario)
    assert constraint in result.failed_constraints
    assert result.blocked and not result.razorpay_called


def test_phase9_migration_enforces_append_only_rls_and_authority_constraint():
    migration = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "0009_provenance_judge_mode.py"
    ).read_text()
    assert "audit_events_append_only" in migration
    assert "before update or delete" in migration
    for table in (
        "provenance_records",
        "provenance_edges",
        "red_team_runs",
        "red_team_attacks",
    ):
        assert f"alter table public.{table} enable row level security" in migration
    assert "not financial_authority or trust_class in" in migration


@pytest.mark.anyio
async def test_verification_and_judge_apis_require_authentication():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/judge/scenarios")).status_code == 401
        assert (
            await client.get(
                "/verify/transaction/00000000-0000-0000-0000-000000000001"
            )
        ).status_code == 401
        assert (
            await client.get("/verify/mandate/00000000-0000-0000-0000-000000000001")
        ).status_code == 401
        assert (
            await client.get("/verify/audit/00000000-0000-0000-0000-000000000001")
        ).status_code == 401
        assert (
            await client.get(
                "/verify/provenance/00000000-0000-0000-0000-000000000001"
            )
        ).status_code == 401
