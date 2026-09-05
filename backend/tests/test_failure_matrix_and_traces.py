from fastapi.testclient import TestClient

from app.main import app
from app.services.judge_service import JudgeService

client = TestClient(app)

def authenticated(client: TestClient):
    # Mocking authentication for tests by passing header
    # TestClient in SentinelPay has a bypass or valid token usually. 
    # For now, let's just use the direct service to test logic.
    pass

def test_failure_matrix_completeness():
    matrix = JudgeService.failure_matrix()
    assert matrix["total_scenarios"] == 24
    assert matrix["all_payment_blocked"] is True
    assert "CRITICAL" in matrix["severity_distribution"]
    assert "HIGH" in matrix["severity_distribution"]
    assert matrix["unique_constraints"] > 10
    
    # Check that all known scenarios are covered
    scenarios = {entry["scenario_key"] for entry in matrix["entries"]}
    assert "buyer_budget_escalation" in scenarios
    assert "zk_invalid_proof" in scenarios
    assert "prompt_injection_catalog" in scenarios

def test_e2e_runtime_tracer_format():
    result = JudgeService().traced_execute("zk_invalid_proof")
    
    assert result["blocked"] is True
    assert "ZK_BUDGET_PROOF" in result["failed_constraints"]
    assert result["security_kernel_result"] == "DENY"
    assert result["execution_ms"] > 0
    
    trace = result["trace"]
    assert "trace_id" in trace
    assert trace["trace_id"].startswith("judge-zk_invalid_proof-")
    assert trace["total_ms"] > 0
    assert trace["span_count"] == 3
    
    spans = {span["layer"]: span for span in trace["spans"]}
    assert "SCENARIO_SETUP" in spans
    assert "SECURITY_KERNEL_EVALUATION" in spans
    assert "RESULT_SERIALIZATION" in spans
    
    assert spans["SECURITY_KERNEL_EVALUATION"]["duration_ms"] >= 0
    assert spans["SECURITY_KERNEL_EVALUATION"]["status"] == "OK"

def test_all_24_scenarios_execute_safely():
    # Ensure no scenario crashes the judge or tracer
    for scenario_key in JudgeService.SCENARIOS:
        result = JudgeService().traced_execute(scenario_key)
        assert result["blocked"] is True  # All attacks must be blocked
        assert result["trace"].get("status", True)
        assert len(result["trace"]["spans"]) == 3
