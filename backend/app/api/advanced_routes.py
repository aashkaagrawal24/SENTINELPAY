import hashlib
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.commerce_routes import load_cart, security_inputs
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.b2b_repository import B2bProcurementRepository
from app.db.session import get_db_session
from app.schemas.advanced import (
    BanditRequest,
    BlsApprovalRequest,
    CausalAnalysisRequest,
    CfrRequest,
    DpAggregateRequest,
    ExternalSearchRequest,
    HomomorphicAggregateRequest,
    LinUcbSelectRequest,
    LinUcbUpdateRequest,
    MultiVerifierRequest,
    NegotiabilityRequest,
    ProcurementOptimizeRequest,
    ProvenanceGraphRequest,
    RacRequest,
    SecurityEvidenceRequest,
    SimulatorRequest,
    UniversalScoutRequest,
    VcgProcurementRequest,
    VdfRequest,
    ZkProveRequest,
    ZkVerifyRequest,
)
from app.schemas.phase9 import ProvenanceCreate
from app.services.advanced_intelligence import (
    CfrBargainingService,
    ControlledPlatformConnector,
    LinUcbService,
    PlatformRegistry,
    RiskAdjustedCostService,
    UniversalWebScout,
    get_negotiability_model,
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
from app.services.advanced_services import (
    BudgetRangeProofService,
    ContextualBanditService,
    ExternalMarketService,
    MultiVerifierService,
    NegotiationSimulator,
    ProcurementOptimizer,
    StaticEvaluationConnector,
)
from app.services.advanced_verifiers import IndependentVerifierSet
from app.services.audit_ledger import AuditLedgerService
from app.services.b2b_procurement import VcgProcurementService
from app.services.provenance_service import ProvenanceService
from app.services.security_kernel import cart_commitment

router = APIRouter(prefix="/api/advanced")

FEATURES = {
    "EXTERNAL_MARKET_INTELLIGENCE": "feature_external_market_intelligence",
    "CONTEXTUAL_BANDIT": "feature_contextual_bandit",
    "ZK_BUDGET_SUFFICIENCY": "feature_zk_budget_sufficiency",
    "MULTI_VERIFIER": "feature_multi_verifier",
    "B2B_PROCUREMENT": "feature_b2b_procurement",
    "NEGOTIATION_SIMULATOR": "feature_negotiation_simulator",
    "ADVANCED_ANALYTICS": "feature_advanced_analytics",
    "PRIVACY_STACK": "feature_privacy_stack",
}


def require_feature(settings: Settings, feature: str) -> None:
    if not getattr(settings, FEATURES[feature]):
        raise HTTPException(404, f"{feature} is disabled; core behavior is unchanged")


def record_run(
    db: Session,
    user: AuthenticatedUser,
    *,
    feature: str,
    status: str,
    safe_input: dict[str, Any],
    result: dict[str, Any],
    metrics: dict[str, Any],
    baseline: dict[str, Any],
    value_type: str,
    merchant_id: UUID | None = None,
) -> UUID:
    run_id = db.execute(
        text(
            """insert into advanced_feature_runs(user_id,merchant_id,feature_key,status,input_safe,result_safe,metrics,baseline)
            values(:user,:merchant,:feature,:status,cast(:input as jsonb),cast(:result as jsonb),cast(:metrics as jsonb),cast(:baseline as jsonb)) returning id"""
        ),
        {
            "user": user.id,
            "merchant": merchant_id,
            "feature": feature,
            "status": status,
            "input": json.dumps(safe_input, default=str),
            "result": json.dumps(result, default=str),
            "metrics": json.dumps(metrics, default=str),
            "baseline": json.dumps(baseline, default=str),
        },
    ).scalar_one()
    provenance = ProvenanceService().create(
        db,
        ProvenanceCreate(
            entity_type="ADVANCED_FEATURE_RUN",
            entity_id=run_id,
            field_name="result",
            value_snapshot=result,
            value_type=value_type,
            trust_class="SYSTEM_DERIVED",
            method=f"Feature-gated {feature} evaluation",
            source="SENTINELPAY_ADVANCED_EVALUATOR",
            financial_authority=False,
            user_id=user.id,
            merchant_id=merchant_id,
        ),
    )
    audit = AuditLedgerService().append(
        db,
        scope=f"ADVANCED:{run_id}",
        event_type="ADVANCED_EXTENSION_EVALUATED",
        actor="ADVANCED_EVALUATOR",
        payload={"feature": feature, "status": status, "payment_created": False},
        user_id=user.id,
        merchant_id=merchant_id,
        provenance_ids=[str(provenance["id"])],
    )
    db.execute(
        text(
            "update advanced_feature_runs set provenance_id=:provenance,audit_event_id=:audit where id=:id"
        ),
        {"provenance": provenance["id"], "audit": audit["id"], "id": run_id},
    )
    db.commit()
    return run_id


@router.get("/status")
def advanced_status(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    del user
    maturity = {
        "EXTERNAL_MARKET_INTELLIGENCE": "17_CONNECTORS_CAPABILITY_AWARE_HANDOFF",
        "CONTEXTUAL_BANDIT": "LINUCB_WITH_UPDATE_PATH",
        "ZK_BUDGET_SUFFICIENCY": "REAL_NARROW_RANGE_PROOF_UNAUDITED",
        "MULTI_VERIFIER": "BLS_AGGREGATE_2_OF_3",
        "B2B_PROCUREMENT": "SEALED_BID_VDF_VCG_CONTROLLED_SETTLEMENT",
        "NEGOTIATION_SIMULATOR": "CFR_HIDDEN_INFORMATION",
        "ADVANCED_ANALYTICS": "DOWHY_DP_NETWORKX_ML",
        "PRIVACY_STACK": "ZK_HE_BLS_VDF_DISTINCT_ROLES",
    }
    return [
        {
            "feature": feature,
            "enabled": bool(getattr(settings, setting)),
            "maturity": maturity[feature],
            "payment_bypass": False,
        }
        for feature, setting in FEATURES.items()
    ]


@router.get("/failure-matrix")
def get_failure_matrix(user: AuthenticatedUser = Depends(get_current_user)):
    from app.services.judge_service import JudgeService
    del user
    return JudgeService.failure_matrix()


@router.post("/e2e-trace")
def execute_e2e_trace(
    body: dict[str, str],
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings)
):
    from app.services.judge_service import JudgeService
    del user
    require_feature(settings, "PRIVACY_STACK")
    scenario = body.get("scenario_key")
    if not scenario:
        raise HTTPException(400, "scenario_key is required")
    try:
        return JudgeService().traced_execute(scenario)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/external/search")
def external_search(
    body: ExternalSearchRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    feature = "EXTERNAL_MARKET_INTELLIGENCE"
    require_feature(settings, feature)
    result = ExternalMarketService().search(
        StaticEvaluationConnector(body.offers), body.query, body.expected_product_key
    )
    run_id = record_run(
        db,
        user,
        feature=feature,
        status=result["status"],
        safe_input={"query": body.query, "offer_count": len(body.offers)},
        result={"offers": result["offers"], "fallback": result["fallback"]},
        metrics=result["metrics"],
        baseline={"connector": "NONE", "result": "HANDOFF"},
        value_type="SIMULATED",
    )
    return {"run_id": run_id, **result, "payment_created": False}


@router.post("/bandit/select")
def bandit_select(
    body: BanditRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    feature = "CONTEXTUAL_BANDIT"
    require_feature(settings, feature)
    result = ContextualBanditService().select(body.context, body.arms)
    run_id = record_run(
        db,
        user,
        feature=feature,
        status=result["status"],
        safe_input={"context": body.context.model_dump(mode="json")},
        result=result,
        metrics={"selected_action": result["action"], "arm_count": len(body.arms)},
        baseline={"static_strategy": "BALANCED"},
        value_type="OPTIMIZED",
        merchant_id=body.merchant_id,
    )
    return {"run_id": run_id, **result, "payment_created": False}


@router.post("/zk/prove")
def zk_prove(
    body: ZkProveRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    feature = "ZK_BUDGET_SUFFICIENCY"
    require_feature(settings, feature)
    try:
        proof = Groth16BudgetProofService.prove(
            body.private_budget_minor, body.public_price_minor
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc
    proof_fingerprint = hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest()
    row_id = db.execute(
        text(
            """insert into zk_budget_proofs(user_id,mandate_id,public_price_minor,budget_commitment,proof,verified,circuit_statement,generation_ms,verification_ms,authority_scope)
            values(:user,:mandate,:price,:commitment,cast(:proof as jsonb),:verified,:statement,:generation,:verification,'EVALUATION_ONLY') returning id"""
        ),
        {
            "user": user.id,
            "mandate": body.mandate_id,
            "price": body.public_price_minor,
            "commitment": proof_fingerprint,
            "proof": json.dumps(proof),
            "verified": proof["verified"],
            "statement": proof["statement"],
            "generation": proof["generation_ms"],
            "verification": 0,
        },
    ).scalar_one()
    result = {
        "proof_id": str(row_id),
        "public_price_minor": body.public_price_minor,
        "budget_commitment": proof_fingerprint,
        "proof": proof,
        "verified": proof["verified"],
        "scheme": proof["scheme"],
        "security_kernel_still_required": True,
    }
    run_id = record_run(
        db,
        user,
        feature=feature,
        status="SUCCESS",
        safe_input={"public_price_minor": body.public_price_minor, "mandate_id": body.mandate_id},
        result={key: value for key, value in result.items() if key != "proof"},
        metrics={
            "generation_ms": proof["generation_ms"],
            "verification_ms": 0,
            "proof_bytes": len(json.dumps(proof).encode()),
        },
        baseline={"standard_check": "SecurityKernel buyer budget assertion"},
        value_type="DERIVED",
    )
    return {"run_id": run_id, **result, "payment_created": False}


@router.post("/zk/verify")
def zk_verify(
    body: ZkVerifyRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    del user
    require_feature(settings, "ZK_BUDGET_SUFFICIENCY")
    if body.proof.get("scheme") == "GROTH16_BN128":
        return {"verified": Groth16BudgetProofService.verify(body.proof)}
    return BudgetRangeProofService.verify(
        body.public_price_minor, body.budget_commitment, body.proof
    )


@router.post("/multi-verifier/evaluate")
def multi_verifier(
    body: MultiVerifierRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    feature = "MULTI_VERIFIER"
    require_feature(settings, feature)
    result = MultiVerifierService().evaluate(body)
    run_id = record_run(
        db,
        user,
        feature=feature,
        status="SUCCESS" if result["status"] == "APPROVED" else "FALLBACK",
        safe_input={
            "payload_hash": body.payload_hash,
            "required_k": body.required_k,
            "expected_verifiers": body.expected_verifiers,
        },
        result=result,
        metrics={"verified_approvals": result["verified_approvals"]},
        baseline={"single_verifier": 1},
        value_type="DERIVED",
    )
    return {"run_id": run_id, **result, "payment_created": False}


@router.post("/procurement/optimize")
def procurement_optimize(
    body: ProcurementOptimizeRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    feature = "B2B_PROCUREMENT"
    require_feature(settings, feature)
    result = ProcurementOptimizer().optimize(body)
    run_id = record_run(
        db,
        user,
        feature=feature,
        status=result["status"],
        safe_input={
            "required_quantity": body.required_quantity,
            "max_budget_minor": body.max_budget_minor,
            "approved_vendor_ids": body.approved_vendor_ids,
            "delivery_deadline": body.delivery_deadline,
        },
        result=result,
        metrics=result.get("metrics", {"fill_rate": 0}),
        baseline={"strategy": "CHEAPEST_SINGLE_APPROVED_VENDOR"},
        value_type="OPTIMIZED",
    )
    return {"run_id": run_id, **result}


@router.post("/simulator/run")
def simulator_run(
    body: SimulatorRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    feature = "NEGOTIATION_SIMULATOR"
    require_feature(settings, feature)
    result = NegotiationSimulator().compare(
        body.seed, body.episodes, body.candidate_strategy
    )
    run_id = record_run(
        db,
        user,
        feature=feature,
        status="RESEARCH_ONLY",
        safe_input=body.model_dump(mode="json"),
        result=result,
        metrics={
            "reward_lift": result["reward_lift"],
            "agreement_rate": result["candidate"]["agreement_rate"],
        },
        baseline=result["baseline"],
        value_type="SIMULATED",
    )
    return {"run_id": run_id, **result, "payment_created": False}


@router.get("/platforms")
def platform_registry(user: AuthenticatedUser = Depends(get_current_user)):
    del user
    return {
        "registered": len(PlatformRegistry.all()),
        "platforms": [item.__dict__ for item in PlatformRegistry.all()],
        "autonomous_external_checkout_claimed": False,
    }


@router.post("/scout/search")
def universal_scout(
    body: UniversalScoutRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    feature = "EXTERNAL_MARKET_INTELLIGENCE"
    require_feature(settings, feature)
    connectors = [
        ControlledPlatformConnector(
            PlatformRegistry.get(snapshot.platform),
            snapshot.offers,
            snapshot.simulate_failure,
        )
        for snapshot in body.snapshots
    ]
    result = UniversalWebScout().search(
        connectors, body.query, body.expected_product, body.timeout_seconds
    )
    run_id = record_run(
        db,
        user,
        feature=feature,
        status=result["status"],
        safe_input={"query": body.query, "platforms": [item.platform for item in body.snapshots]},
        result={"offers": result["offers"], "connector_results": result["connector_results"]},
        metrics=result["metrics"],
        baseline={"strategy": "SINGLE_SOURCE_HANDOFF"},
        value_type="CONTROLLED_EXTERNAL",
    )
    return {"run_id": run_id, **result}


@router.post("/negotiability/predict")
def predict_negotiability(
    body: NegotiabilityRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_feature(settings, "ADVANCED_ANALYTICS")
    result = get_negotiability_model().predict(body.features)
    run_id = record_run(
        db,
        user,
        feature="ADVANCED_ANALYTICS",
        status="SUCCESS",
        safe_input=body.model_dump(mode="json"),
        result=result,
        metrics=result["metrics"],
        baseline={"strategy": "STATIC_NEGOTIATION_FLAG"},
        value_type="MODEL_DERIVED",
    )
    return {"run_id": run_id, **result, "financial_authority": False}


@router.post("/rac/calculate")
def calculate_rac(
    body: RacRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_feature(settings, "ADVANCED_ANALYTICS")
    result = RiskAdjustedCostService.calculate(body)
    run_id = record_run(
        db,
        user,
        feature="ADVANCED_ANALYTICS",
        status="SUCCESS",
        safe_input={"component_sources": {key: value.source for key, value in body}},
        result=result,
        metrics={"components": len(result["components"])},
        baseline={"metric": "LISTED_PRICE_ONLY"},
        value_type="DERIVED",
    )
    return {"run_id": run_id, **result}


@router.post("/linucb/select")
def linucb_select(
    body: LinUcbSelectRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_feature(settings, "CONTEXTUAL_BANDIT")
    result = LinUcbService().select(body.context, body.alpha, body.states)
    if body.merchant_id:
        member = db.execute(
            text("select 1 from merchant_users where merchant_id=:merchant and user_id=:user"),
            {"merchant": body.merchant_id, "user": user.id},
        ).scalar()
        if not member:
            raise HTTPException(403, "Merchant membership required for persistent LinUCB state")
        for state in body.states:
            db.execute(
                text(
                    """insert into linucb_models(merchant_id,context_key,action,dimension,alpha,a_matrix,b_vector,observations)
                    values(:merchant,:context,:action,:dimension,:alpha,cast(:a as jsonb),cast(:b as jsonb),:observations)
                    on conflict(merchant_id,context_key,action) do update set alpha=excluded.alpha,a_matrix=excluded.a_matrix,
                    b_vector=excluded.b_vector,observations=excluded.observations,updated_at=now()"""
                ),
                {
                    "merchant": body.merchant_id,
                    "context": body.context_key,
                    "action": state.action,
                    "dimension": len(body.context),
                    "alpha": body.alpha,
                    "a": json.dumps(state.a_matrix),
                    "b": json.dumps(state.b_vector),
                    "observations": state.observations,
                },
            )
    run_id = record_run(
        db,
        user,
        feature="CONTEXTUAL_BANDIT",
        status="SUCCESS",
        safe_input={"context_dimension": len(body.context), "alpha": body.alpha},
        result=result,
        metrics={"actions": len(body.states)},
        baseline={"strategy": "BALANCED"},
        value_type="OPTIMIZED",
        merchant_id=body.merchant_id,
    )
    return {"run_id": run_id, **result}


@router.post("/linucb/update")
def linucb_update(
    body: LinUcbUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_feature(settings, "CONTEXTUAL_BANDIT")
    result = LinUcbService().update(body.context, body.reward, body.state)
    if body.merchant_id:
        member = db.execute(
            text("select 1 from merchant_users where merchant_id=:merchant and user_id=:user"),
            {"merchant": body.merchant_id, "user": user.id},
        ).scalar()
        if not member:
            raise HTTPException(403, "Merchant membership required for persistent LinUCB update")
        model_id = db.execute(
            text(
                """insert into linucb_models(merchant_id,context_key,action,dimension,alpha,a_matrix,b_vector,observations)
                values(:merchant,:context,:action,:dimension,1,cast(:a as jsonb),cast(:b as jsonb),:observations)
                on conflict(merchant_id,context_key,action) do update set a_matrix=excluded.a_matrix,b_vector=excluded.b_vector,
                observations=excluded.observations,updated_at=now() returning id"""
            ),
            {
                "merchant": body.merchant_id,
                "context": body.context_key,
                "action": result["action"],
                "dimension": len(body.context),
                "a": json.dumps(result["a_matrix"]),
                "b": json.dumps(result["b_vector"]),
                "observations": result["observations"],
            },
        ).scalar_one()
        db.execute(
            text(
                """insert into linucb_outcomes(model_id,context_vector,reward)
                values(:model,cast(:context as jsonb),:reward)"""
            ),
            {"model": model_id, "context": json.dumps(body.context), "reward": body.reward},
        )
        db.commit()
        result["model_id"] = str(model_id)
    return result


@router.post("/cfr/train")
def cfr_train(
    body: CfrRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_feature(settings, "NEGOTIATION_SIMULATOR")
    result = CfrBargainingService(body.seed).train(body.iterations)
    run_id = record_run(
        db,
        user,
        feature="NEGOTIATION_SIMULATOR",
        status="SUCCESS",
        safe_input=body.model_dump(),
        result=result,
        metrics={
            "information_sets": result["information_sets"],
            "regret_updates": result["information_sets_with_regret_updates"],
        },
        baseline=result["benchmarks"],
        value_type="SIMULATED",
    )
    return {"run_id": run_id, **result, "payment_created": False}


@router.post("/causal/analyze")
def causal_analysis(
    body: CausalAnalysisRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_feature(settings, "ADVANCED_ANALYTICS")
    try:
        result = CausalAnalysisService.analyze(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    causal_id = db.execute(
        text(
            """insert into causal_analysis_runs(method,common_causes,estimand,estimate,simple_estimate,refutations,assumptions)
            values(:method,cast(:causes as jsonb),:estimand,:estimate,:simple,cast(:refutations as jsonb),cast(:assumptions as jsonb)) returning id"""
        ),
        {
            "method": result["method"],
            "causes": json.dumps(result["common_causes"]),
            "estimand": result["estimand"],
            "estimate": result["estimate"],
            "simple": result["simple_control_treatment_difference"],
            "refutations": json.dumps(result["refutations"]),
            "assumptions": json.dumps(result["assumptions"]),
        },
    ).scalar_one()
    run_id = record_run(
        db,
        user,
        feature="ADVANCED_ANALYTICS",
        status="SUCCESS",
        safe_input={"observations": len(body.observations)},
        result=result,
        metrics={"estimate": result["estimate"]},
        baseline={"simple_difference": result["simple_control_treatment_difference"]},
        value_type="CAUSAL_ESTIMATE",
    )
    return {"run_id": run_id, "causal_analysis_id": causal_id, **result}


@router.post("/privacy/dp-aggregate")
def dp_aggregate(
    body: DpAggregateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_feature(settings, "PRIVACY_STACK")
    try:
        result = DifferentialPrivacyService.aggregate(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row_id = db.execute(
        text(
            """insert into dp_aggregate_runs(statistic,epsilon,lower_bound,upper_bound,record_count,private_value)
            values(:statistic,:epsilon,:lower,:upper,:records,:value) returning id"""
        ),
        {
            "statistic": result["statistic"],
            "epsilon": result["epsilon"],
            "lower": result["bounds"][0],
            "upper": result["bounds"][1],
            "records": result["records"],
            "value": result["value"],
        },
    ).scalar_one()
    db.commit()
    return {"dp_run_id": row_id, **result, "user_id": user.id}


@router.post("/provenance/graph")
def provenance_graph(
    body: ProvenanceGraphRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_feature(settings, "ADVANCED_ANALYTICS")
    try:
        result = ProvenanceGraphService.analyze(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row_id = db.execute(
        text(
            """insert into provenance_graph_runs(user_id,node_count,edge_count,query_safe,result_safe)
            values(:user,:nodes,:edges,cast(:query as jsonb),cast(:result as jsonb)) returning id"""
        ),
        {
            "user": user.id,
            "nodes": result["nodes"],
            "edges": result["edges"],
            "query": body.model_dump_json(),
            "result": json.dumps(result),
        },
    ).scalar_one()
    db.commit()
    return {"graph_run_id": row_id, **result}


@router.post("/privacy/he-aggregate")
def homomorphic_aggregate(
    body: HomomorphicAggregateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_feature(settings, "PRIVACY_STACK")
    result = HomomorphicAnalyticsService.aggregate(body)
    row_id = db.execute(
        text(
            """insert into he_aggregate_runs(scheme,operation,record_count,ciphertext_fingerprint,verified,elapsed_ms)
            values(:scheme,:operation,:records,:fingerprint,:verified,:elapsed) returning id"""
        ),
        {
            "scheme": result["scheme"],
            "operation": result["operation"],
            "records": result["records"],
            "fingerprint": result["ciphertext_fingerprint"],
            "verified": result["verified"],
            "elapsed": result["elapsed_ms"],
        },
    ).scalar_one()
    db.commit()
    return {"he_run_id": row_id, **result, "user_id": user.id}


@router.post("/bls/approve")
def bls_approve(
    body: BlsApprovalRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_feature(settings, "MULTI_VERIFIER")
    try:
        result = BlsMultiVerifierService.approve(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    bls_run_id = db.execute(
        text(
            """insert into bls_approval_runs(user_id,payload_hash,required_k,verifier_roles,public_keys,aggregate_signature,aggregate_valid,authority_scope,key_source)
            values(:user,:payload,:required,cast(:roles as jsonb),cast(:keys as jsonb),:signature,:valid,'EVALUATION_ONLY','CALLER_SUPPLIED_EVALUATION_KEYS') returning id"""
        ),
        {
            "user": user.id,
            "payload": result["payload_hash"],
            "required": result["required_k"],
            "roles": json.dumps(result["independent_verifiers"]),
            "keys": json.dumps(result["public_keys"]),
            "signature": result["aggregate_signature"],
            "valid": result["aggregate_valid"],
        },
    ).scalar_one()
    run_id = record_run(
        db,
        user,
        feature="MULTI_VERIFIER",
        status="SUCCESS" if result["status"] == "APPROVED" else "FAILED",
        safe_input={"payload_hash": body.payload_hash, "roles": result["independent_verifiers"]},
        result={key: value for key, value in result.items() if key != "aggregate_signature"},
        metrics={"valid": sum(result["individual_valid"])},
        baseline={"verifiers": 1},
        value_type="CRYPTOGRAPHIC_PROOF",
    )
    return {"run_id": run_id, "bls_run_id": bls_run_id, **result}


@router.post("/security/evidence")
def create_security_evidence(
    body: SecurityEvidenceRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_feature(settings, "ZK_BUDGET_SUFFICIENCY")
    require_feature(settings, "MULTI_VERIFIER")
    if not settings.supabase_server_secret:
        raise HTTPException(503, "Server verifier secret is not configured")
    cart = load_cart(db, body.cart_id, user.id)
    mandate = db.execute(
        text("select * from mandates where id=:id and user_id=:user"),
        {"id": cart["mandate_id"], "user": user.id},
    ).mappings().one()
    _mandate, _policy, policy_context = security_inputs(db, cart)
    verifier_decisions = IndependentVerifierSet().evaluate(policy_context, cart)
    if not all(item.approved for item in verifier_decisions):
        raise HTTPException(
            409,
            {
                "reason": "INDEPENDENT_VERIFIER_DENIED",
                "verifiers": [item.__dict__ for item in verifier_decisions],
            },
        )
    try:
        proof = Groth16BudgetProofService.prove(
            int(mandate["max_total_amount_minor"]), int(cart["total_minor"])
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc
    proof_fingerprint = hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest()
    zk_id = db.execute(
        text(
            """insert into zk_budget_proofs(user_id,mandate_id,user_cart_id,public_price_minor,budget_commitment,proof,verified,circuit_statement,generation_ms,verification_ms,authority_scope)
            values(:user,:mandate,:cart,:price,:commitment,cast(:proof as jsonb),:verified,:statement,:generation,:verification,'SECURITY_KERNEL_INPUT') returning id"""
        ),
        {
            "user": user.id,
            "mandate": mandate["id"],
            "cart": cart["id"],
            "price": cart["total_minor"],
            "commitment": proof_fingerprint,
            "proof": json.dumps(proof),
            "verified": proof["verified"],
            "statement": proof["statement"],
            "generation": proof["generation_ms"],
            "verification": 0,
        },
    ).scalar_one()
    payload_hash = cart_commitment(cart)
    configured_role_keys = {
        "MANDATE": settings.bls_mandate_signing_key,
        "POLICY": settings.bls_policy_signing_key,
        "RISK": settings.bls_risk_signing_key,
    }
    if all(configured_role_keys.values()):
        bls = BlsMultiVerifierService.approve_with_role_secrets(
            payload_hash,
            {
                role: secret.get_secret_value()
                for role, secret in configured_role_keys.items()
            },
        )
    elif settings.app_env == "production":
        raise HTTPException(503, "Independent BLS verifier role keys are not configured")
    else:
        bls = BlsMultiVerifierService.approve_with_server_secret(
            payload_hash, settings.supabase_server_secret.get_secret_value()
        )
    bls_id = db.execute(
        text(
            """insert into bls_approval_runs(user_id,user_cart_id,payload_hash,required_k,verifier_roles,public_keys,aggregate_signature,aggregate_valid,authority_scope,key_source,verifier_decisions)
            values(:user,:cart,:payload,:required,cast(:roles as jsonb),cast(:keys as jsonb),:signature,:valid,'SECURITY_KERNEL_INPUT',:key_source,cast(:decisions as jsonb)) returning id"""
        ),
        {
            "user": user.id,
            "cart": cart["id"],
            "payload": payload_hash,
            "required": bls["required_k"],
            "roles": json.dumps(bls["independent_verifiers"]),
            "keys": json.dumps(bls["public_keys"]),
            "signature": bls["aggregate_signature"],
            "valid": bls["aggregate_valid"],
            "key_source": bls["key_source"],
            "decisions": json.dumps([item.__dict__ for item in verifier_decisions]),
        },
    ).scalar_one()
    provenance = ProvenanceService().create(
        db,
        ProvenanceCreate(
            entity_type="CART",
            entity_id=cart["id"],
            field_name="advanced_security_evidence",
            value_snapshot={"zk_proof_id": str(zk_id), "bls_run_id": str(bls_id)},
            value_type="DERIVED",
            trust_class="SYSTEM_DERIVED",
            method="Server-resolved ZK and BLS verification bundle",
            source="SENTINELPAY_SECURITY_EVIDENCE",
            financial_authority=False,
            user_id=user.id,
            merchant_id=cart["merchant_id"],
        ),
    )
    db.commit()
    return {
        "cart_id": cart["id"],
        "payload_hash": payload_hash,
        "proof_references": {
            "zk_proof_id": str(zk_id),
            "bls_run_id": str(bls_id),
            "provenance_record_id": str(provenance["id"]),
        },
        "verified": bool(proof["verified"] and bls["aggregate_valid"]),
        "independent_verifiers": [item.__dict__ for item in verifier_decisions],
        "financial_authority": False,
        "security_kernel_still_required": True,
    }


@router.post("/vdf/evaluate")
def vdf_evaluate(
    body: VdfRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_feature(settings, "PRIVACY_STACK")
    result = WesolowskiVdfService.evaluate(body.challenge, body.iterations)
    row_id = db.execute(
        text(
            """insert into vdf_runs(purpose,challenge_hash,iterations,output,proof,verified,evaluation_ms)
            values(:purpose,:challenge,:iterations,:output,:proof,:verified,:elapsed) returning id"""
        ),
        {
            "purpose": result["purpose"],
            "challenge": hashlib.sha256(body.challenge.encode()).hexdigest(),
            "iterations": result["iterations"],
            "output": result["y"],
            "proof": result["proof"],
            "verified": result["verified"],
            "elapsed": result["evaluation_ms"],
        },
    ).scalar_one()
    db.commit()
    return {"vdf_run_id": row_id, **result, "user_id": user.id}


@router.post("/procurement/vcg")
def procurement_vcg(
    body: VcgProcurementRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_feature(settings, "B2B_PROCUREMENT")
    result = VcgProcurementService.execute(body)
    try:
        persistence = B2bProcurementRepository().persist(
            db, user_id=user.id, request=body, result=result
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    run_id = record_run(
        db,
        user,
        feature="B2B_PROCUREMENT",
        status="SUCCESS" if result["status"] == "ALLOCATED" else "FALLBACK",
        safe_input={
            "required_quantity": body.required_quantity,
            "approved_vendor_count": len(body.approved_vendor_ids),
            "bid_count": len(body.bids),
        },
        result={key: value for key, value in result.items() if key != "commitments"},
        metrics={
            "reported_total_minor": result.get("reported_total_minor", 0),
            "vcg_total_minor": result.get("vcg_total_minor", 0),
        },
        baseline={"mechanism": "LOWEST_PRICE_SINGLE_VENDOR"},
        value_type="OPTIMIZED",
    )
    return {"run_id": run_id, "persistence": persistence, **result}
