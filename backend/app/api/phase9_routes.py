import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.commerce_routes import load_cart
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.db.session import get_db_session
from app.schemas.phase9 import JudgeAttackRequest
from app.services.audit_ledger import AuditLedgerService
from app.services.judge_service import JudgeService
from app.services.mandate_service import MandateService
from app.services.provenance_service import ProvenanceService
from app.services.security_kernel import cart_commitment

router = APIRouter()


def _json(value):
    return value if isinstance(value, (dict, list)) else json.loads(value)


def _store_attack(
    db: Session, run_id: UUID, user: AuthenticatedUser, scenario_key: str
) -> dict:
    result = JudgeService().execute(scenario_key)
    event = AuditLedgerService().append(
        db,
        scope=f"RED_TEAM:{run_id}",
        event_type="SECURITY_ATTACK_BLOCKED" if result.blocked else "SECURITY_ATTACK_ALLOWED",
        actor="JUDGE_MODE",
        payload={
            "scenario_key": scenario_key,
            "result": result.security_kernel_result,
            "razorpay_called": result.razorpay_called,
        },
        user_id=user.id,
        metadata={"controlled_test": True},
    )
    result.audit_event_id = event["id"]
    db.execute(
        text(
            """insert into red_team_attacks(run_id,scenario_key,category,attack,ai_response,buyer_policy,merchant_policy,campaign_policy,z3_assertions,solver_result,security_kernel_result,razorpay_called,audit_event_id,expected_block,blocked,critical)
            values(:run,:scenario,:category,cast(:attack as jsonb),:ai,cast(:buyer as jsonb),cast(:merchant as jsonb),cast(:campaign as jsonb),cast(:assertions as jsonb),:solver,:kernel,:razorpay,:audit,true,:blocked,true)"""
        ),
        {
            "run": run_id,
            "scenario": scenario_key,
            "category": result.category,
            "attack": json.dumps(result.attack),
            "ai": result.ai_response,
            "buyer": json.dumps(result.buyer_policy),
            "merchant": json.dumps(result.merchant_policy),
            "campaign": json.dumps(result.campaign_policy),
            "assertions": json.dumps(result.z3_assertions),
            "solver": result.solver_result,
            "kernel": result.security_kernel_result,
            "razorpay": result.razorpay_called,
            "audit": event["id"],
            "blocked": result.blocked,
        },
    )
    return result.model_dump(mode="json")


def _complete_run(db: Session, run_id: UUID) -> dict:
    metrics = dict(
        db.execute(
            text(
                """select count(*)::int attacks_total,count(*) filter(where blocked)::int attacks_blocked,
                count(*) filter(where critical and not blocked and razorpay_called)::int unsafe_executions,
                count(*) filter(where not expected_block and blocked)::int false_blocks,
                coalesce(count(*) filter(where critical and not blocked and razorpay_called)::numeric/nullif(count(*) filter(where critical),0),0) critical_bypass_rate
                from red_team_attacks where run_id=:run"""
            ),
            {"run": run_id},
        )
        .mappings()
        .one()
    )
    db.execute(
        text(
            """update red_team_runs set status='COMPLETED',attacks_total=:attacks_total,attacks_blocked=:attacks_blocked,
            unsafe_executions=:unsafe_executions,false_blocks=:false_blocks,critical_bypass_rate=:critical_bypass_rate,completed_at=now() where id=:run"""
        ),
        {**metrics, "run": run_id},
    )
    return metrics


@router.get("/api/judge/scenarios")
def judge_scenarios(user: AuthenticatedUser = Depends(get_current_user)):
    del user
    return [
        {"scenario_key": key, "category": value[0], "attack": value[1]}
        for key, value in JudgeService.SCENARIOS.items()
    ]


@router.post("/api/judge/attacks")
def judge_attack(
    body: JudgeAttackRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    run_id = db.execute(
        text(
            "insert into red_team_runs(user_id,merchant_id) values(:user,:merchant) returning id"
        ),
        {"user": user.id, "merchant": body.merchant_id},
    ).scalar_one()
    try:
        result = _store_attack(db, run_id, user, body.scenario_key)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(404, str(exc)) from exc
    metrics = _complete_run(db, run_id)
    db.commit()
    return {"run_id": run_id, "result": result, "metrics": metrics}


@router.post("/api/judge/runs")
def judge_run_all(
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    merchant_id = UUID(str(body["merchant_id"])) if body.get("merchant_id") else None
    run_id = db.execute(
        text(
            "insert into red_team_runs(user_id,merchant_id) values(:user,:merchant) returning id"
        ),
        {"user": user.id, "merchant": merchant_id},
    ).scalar_one()
    results = [_store_attack(db, run_id, user, key) for key in JudgeService.SCENARIOS]
    metrics = _complete_run(db, run_id)
    db.commit()
    return {"run_id": run_id, "results": results, "metrics": metrics}


@router.get("/api/judge/runs/{run_id}")
def judge_run(
    run_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    run = db.execute(
        text("select * from red_team_runs where id=:run and user_id=:user"),
        {"run": run_id, "user": user.id},
    ).mappings().one_or_none()
    if not run:
        raise HTTPException(404, "Red-team run not found")
    attacks = [
        dict(row)
        for row in db.execute(
            text("select * from red_team_attacks where run_id=:run order by created_at"),
            {"run": run_id},
        ).mappings()
    ]
    return {"run": dict(run), "attacks": attacks}


@router.get("/verify/provenance/{record_id}")
def verify_provenance(
    record_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    row = db.execute(
        text(
            """select p.* from provenance_records p where p.id=:id and
            (p.user_id=:user or exists(select 1 from merchant_users mu where mu.merchant_id=p.merchant_id and mu.user_id=:user))"""
        ),
        {"id": record_id, "user": user.id},
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(404, "Provenance record not found")
    safe = ProvenanceService.safe_view(dict(row))
    return {"valid": safe["financial_authority"] != "ALLOWED" or row["trust_class"] in ProvenanceService.AUTHORITY_TRUST, "record": safe}


@router.get("/verify/audit/{event_id}")
def verify_audit(
    event_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    event = db.execute(
        text(
            """select * from audit_events where id=:id and (user_id=:user or exists(
            select 1 from merchant_users mu where mu.merchant_id=audit_events.merchant_id and mu.user_id=:user))"""
        ),
        {"id": event_id, "user": user.id},
    ).mappings().one_or_none()
    if not event:
        raise HTTPException(404, "Audit event not found")
    verification = AuditLedgerService().verify_chain(db, event["chain_scope"])
    return {"event_id": event_id, "event_type": event["event_type"], "scope": event["chain_scope"], "chain": verification}


@router.get("/verify/mandate/{mandate_id}")
def verify_mandate(
    mandate_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    mandate = db.execute(
        text("select * from mandates where id=:id and user_id=:user"),
        {"id": mandate_id, "user": user.id},
    ).mappings().one_or_none()
    if not mandate:
        raise HTTPException(404, "Mandate not found")
    authority = {
        "product_scope": _json(mandate["product_scope"]),
        "max_total_amount_minor": mandate["max_total_amount_minor"],
        "currency": mandate["currency"],
        "max_quantity": mandate["max_quantity"],
        "allowed_conditions": _json(mandate["allowed_conditions"]),
        "preferred_brands": _json(mandate["preferred_brands"]),
        "excluded_brands": _json(mandate["excluded_brands"]),
        "negotiation_allowed": mandate["negotiation_allowed"],
        "upsell_allowed": mandate["upsell_allowed"],
        "cross_sell_allowed": mandate["cross_sell_allowed"],
        "campaign_offer_allowed": mandate["campaign_offer_allowed"],
        "auto_purchase_allowed": False,
        "expires_at": mandate["expires_at"].isoformat(),
    }
    return {
        "mandate_id": mandate_id,
        "status": mandate["status"],
        "not_expired": mandate["expires_at"].astimezone(UTC) > datetime.now(UTC),
        "replay_check": mandate["execution_count"] < mandate["max_executions"],
        "integrity_valid": MandateService().hash(authority) == mandate["integrity_hash"],
        "auto_purchase_allowed": False,
    }


@router.get("/verify/transaction/{transaction_id}")
def verify_transaction(
    transaction_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    transaction = db.execute(
        text("select * from transactions where id=:id and user_id=:user"),
        {"id": transaction_id, "user": user.id},
    ).mappings().one_or_none()
    if not transaction:
        raise HTTPException(404, "Transaction not found")
    evaluation = db.execute(
        text("select * from policy_evaluations where transaction_id=:id order by created_at desc limit 1"),
        {"id": transaction_id},
    ).mappings().one_or_none()
    commitment = db.execute(
        text("select * from cart_commitments where transaction_id=:id"),
        {"id": transaction_id},
    ).mappings().one_or_none()
    payment = db.execute(
        text("select status,verified_at from payment_attempts where transaction_id=:id order by created_at desc limit 1"),
        {"id": transaction_id},
    ).mappings().one_or_none()
    cart = load_cart(db, transaction["cart_id"], user.id)
    failed = _json(evaluation["failed_constraints"]) if evaluation else ["NO_POLICY_EVALUATION"]
    return {
        "transaction_id": transaction_id,
        "mandate": {"id": transaction["mandate_id"], "referenced": True},
        "product_price_seller_checks": not any(item.startswith(("LINE_", "MERCHANT_")) for item in failed),
        "policy_sat": bool(evaluation and evaluation["solver_result"] == "SAT"),
        "campaign_policy": "NOT_APPLICABLE" if not evaluation or not evaluation["campaign_id"] else ("PASS" if not any(item.startswith("CAMPAIGN_") for item in failed) else "DENY"),
        "cart_commitment_valid": bool(commitment and cart_commitment(cart) == commitment["approved_hash"]),
        "replay_check": transaction["status"] not in {"CANCELLED", "DENIED"},
        "payment_verified": bool(payment and payment["status"] == "CAPTURED" and payment["verified_at"]),
        "audit_chain": AuditLedgerService().verify_chain(db, f"TRANSACTION:{transaction_id}"),
        "provenance_valid": not bool(db.execute(text("select 1 from provenance_records where entity_id=:id and financial_authority and trust_class not in ('USER_SIGNED','MERCHANT_SIGNED','RAZORPAY_VERIFIED')"), {"id": transaction_id}).scalar()),
        "private_policy_values_exposed": False,
    }

