import json
from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.campaign import CampaignPolicy
from app.schemas.security import AdvancedSecurityEvidence, UnifiedPolicyContext
from app.services.audit_ledger import AuditLedgerService
from app.services.campaign_services import CampaignEligibilityService
from app.services.mandate_service import MandateService
from app.services.security_kernel import (
    SecurityKernel,
    SecurityOutcome,
    canonical_cart,
    cart_commitment,
)

router = APIRouter(prefix="/api")


def load_cart(db: Session, cart_id: UUID, user_id: UUID) -> dict:
    row = (
        db.execute(
            text("select * from carts where id=:id and user_id=:user"),
            {"id": cart_id, "user": user_id},
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "Cart not found")
    cart = dict(row)
    cart["items"] = [
        dict(item)
        for item in db.execute(
            text(
                "select product_id,variant_id,quantity,unit_price_minor,condition,product_snapshot,source_version from cart_items where cart_id=:cart order by id"
            ),
            {"cart": cart_id},
        ).mappings()
    ]
    return cart


@router.post("/carts")
def create_cart(
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    mandate = (
        db.execute(
            text(
                "select id,currency from mandates where id=:mandate and user_id=:user and status='ACTIVE'"
            ),
            {"mandate": body["mandate_id"], "user": user.id},
        )
        .mappings()
        .one_or_none()
    )
    if not mandate:
        raise HTTPException(409, "Active owned mandate required")
    row = (
        db.execute(
            text(
                "insert into carts(merchant_id,user_id,mandate_id,currency) values(:merchant,:user,:mandate,:currency) returning *"
            ),
            {
                "merchant": body["merchant_id"],
                "user": user.id,
                "mandate": mandate["id"],
                "currency": mandate["currency"],
            },
        )
        .mappings()
        .one()
    )
    db.commit()
    return dict(row)


@router.post("/carts/{cart_id}/items")
def add_cart_item(
    cart_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    cart = load_cart(db, cart_id, user.id)
    product = (
        db.execute(
            text(
                "select * from merchant_products where id=:product and merchant_id=:merchant and active"
            ),
            {"product": body["product_id"], "merchant": cart["merchant_id"]},
        )
        .mappings()
        .one_or_none()
    )
    if not product:
        raise HTTPException(404, "Active merchant product not found")
    quantity = int(body.get("quantity", 1))
    unit_price = int(product["base_price_minor"])
    db.execute(
        text(
            "insert into cart_items(cart_id,product_id,variant_id,quantity,unit_price_minor,condition,product_snapshot,source_version) values(:cart,:product,:variant,:quantity,:price,:condition,cast(:snapshot as jsonb),:source_version)"
        ),
        {
            "cart": cart_id,
            "product": product["id"],
            "variant": body.get("variant_id"),
            "quantity": quantity,
            "price": unit_price,
            "condition": product["condition"],
            "snapshot": json.dumps(dict(product), default=str),
            "source_version": product["updated_at"],
        },
    )
    db.execute(
        text(
            "update carts set subtotal_minor=subtotal_minor+:amount,total_minor=total_minor+:amount,version=version+1,status='CART_READY' where id=:cart"
        ),
        {"amount": unit_price * quantity, "cart": cart_id},
    )
    db.commit()
    return load_cart(db, cart_id, user.id)


@router.get("/carts/{cart_id}")
def get_cart(
    cart_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    return load_cart(db, cart_id, user.id)


def security_inputs(db: Session, cart: dict, transaction: dict | None = None):
    mandate = dict(
        db.execute(
            text("select * from mandates where id=:id for update"), {"id": cart["mandate_id"]}
        )
        .mappings()
        .one()
    )
    if not cart["items"]:
        raise HTTPException(422, "Cart must contain at least one item")
    policies, lines = [], []
    minimum_total = base_total = maximum_discount = 0
    for item in cart["items"]:
        snapshot = (
            item["product_snapshot"]
            if isinstance(item["product_snapshot"], dict)
            else json.loads(item["product_snapshot"])
        )
        policy = dict(
            db.execute(
                text(
                    "select * from merchant_policies where merchant_id=:merchant and status='ACTIVE' and valid_from<=now() and (valid_until is null or valid_until>now()) and (scope='GLOBAL' or (scope='CATEGORY' and scope_reference=:category) or (scope='PRODUCT' and scope_reference=:product)) order by case scope when 'PRODUCT' then 3 when 'CATEGORY' then 2 else 1 end desc,version desc limit 1"
                ),
                {
                    "merchant": cart["merchant_id"],
                    "category": snapshot["category"],
                    "product": str(item["product_id"]),
                },
            )
            .mappings()
            .one()
        )
        available = int(
            db.execute(
                text(
                    "select coalesce(sum(available_quantity-reserved_quantity),0) from merchant_inventory where product_id=:p"
                ),
                {"p": item["product_id"]},
            ).scalar_one()
        )
        line_base = int(policy.get("base_price_minor") or snapshot["base_price_minor"])
        line_discount = int(
            policy.get("maximum_discount_minor")
            or round(line_base * float(policy.get("maximum_discount_percent") or 0) / 100)
        )
        minimum_total += int(policy["minimum_sale_price_minor"]) * item["quantity"]
        base_total += line_base * item["quantity"]
        maximum_discount += line_discount * item["quantity"]
        policies.append(policy)
        lines.append(
            {
                "product_id": str(item["product_id"]),
                "quantity": item["quantity"],
                "available_quantity": available,
                "condition": item["condition"],
                "brand": snapshot.get("brand"),
            }
        )
    policy = policies[0]
    campaign_policy = None
    if cart.get("campaign_offer_id"):
        campaign = dict(
            db.execute(
                text(
                    """select c.*,o.id offer_id,o.status offer_status,o.discount_minor,o.expires_at offer_expires_at,o.eligibility_snapshot
                    from campaign_offers o join campaigns c on c.id=o.campaign_id
                    where o.id=:offer and o.cart_id=:cart and o.user_id=:user and o.mandate_id=:mandate for update"""
                ),
                {
                    "offer": cart["campaign_offer_id"],
                    "cart": cart["id"],
                    "user": cart["user_id"],
                    "mandate": mandate["id"],
                },
            )
            .mappings()
            .one()
        )
        campaign_products = {
            str(product_id)
            for product_id in db.execute(
                text("select product_id from campaign_products where campaign_id=:campaign"),
                {"campaign": campaign["id"]},
            ).scalars()
        }
        eligibility = CampaignEligibilityService.evaluate(
            campaign, mandate, cart, campaign_products
        )
        campaign_policy = CampaignPolicy(
            campaign_id=campaign["id"],
            status=campaign["status"],
            starts_at=campaign["start_time"],
            ends_at=min(campaign["end_time"], campaign["offer_expires_at"]),
            discount_minor=cart["campaign_discount_minor"],
            max_discount_per_order_minor=campaign["max_discount_per_order_minor"],
            used_budget_minor=campaign["used_discount_budget_minor"],
            reserved_budget_minor=campaign["reserved_discount_budget_minor"],
            total_budget_minor=campaign["total_discount_budget_minor"],
            current_redemptions=campaign["current_redemptions"],
            reserved_redemptions=campaign["reserved_redemptions"],
            maximum_redemptions=campaign["maximum_redemptions"],
            final_price_minor=cart["total_minor"],
            minimum_final_price_minor=max(
                minimum_total, int(campaign["minimum_final_price_minor"] or 0)
            ),
            product_eligible=eligibility["product_eligible"],
            segment_eligible=eligibility["segment_eligible"],
            offer_eligible=campaign["offer_status"] == "APPLIED",
        )
    context = UnifiedPolicyContext(
        final_price_minor=cart["total_minor"],
        buyer_budget_minor=mandate["max_total_amount_minor"],
        quantity=sum(item["quantity"] for item in cart["items"]),
        buyer_max_quantity=mandate["max_quantity"],
        condition=lines[0]["condition"],
        allowed_conditions=mandate["allowed_conditions"],
        brand=lines[0]["brand"],
        excluded_brands=mandate["excluded_brands"],
        mandate_expires_at=mandate["expires_at"].astimezone(UTC),
        mandate_status=mandate["status"],
        execution_count=mandate["execution_count"],
        max_executions=mandate["max_executions"],
        merchant_minimum_minor=minimum_total,
        base_price_minor=base_total,
        discount_minor=cart["discount_minor"],
        merchant_max_discount_minor=maximum_discount,
        available_quantity=sum(line["available_quantity"] for line in lines),
        cart_currency=cart["currency"],
        mandate_currency=mandate["currency"],
        auto_purchase_allowed=mandate["auto_purchase_allowed"],
        lines=lines,
        campaign_policy=campaign_policy,
        advanced_verification_required=bool(
            transaction and transaction.get("advanced_verification_required")
        ),
        advanced_evidence=transaction.get("advanced_evidence") if transaction else None,
    )
    return mandate, policy, context


def resolve_advanced_evidence(
    db: Session, user_id: UUID, cart: dict, supplied: dict | None
) -> AdvancedSecurityEvidence | None:
    if not supplied:
        return None
    references = supplied.get("proof_references", supplied)
    try:
        zk_id = UUID(str(references["zk_proof_id"]))
        bls_id = UUID(str(references["bls_run_id"]))
        provenance_id = UUID(str(references["provenance_record_id"]))
    except (KeyError, TypeError, ValueError):
        return AdvancedSecurityEvidence(proof_references={})
    zk = db.execute(
        text(
            """select verified from zk_budget_proofs where id=:id and user_id=:user
            and user_cart_id=:cart and mandate_id=:mandate and public_price_minor=:price
            and authority_scope='SECURITY_KERNEL_INPUT'"""
        ),
        {
            "id": zk_id,
            "user": user_id,
            "cart": cart["id"],
            "mandate": cart["mandate_id"],
            "price": cart["total_minor"],
        },
    ).scalar()
    bls = db.execute(
        text(
            """select aggregate_valid,verifier_roles,verifier_decisions from bls_approval_runs
            where id=:id and user_id=:user and user_cart_id=:cart and payload_hash=:payload
            and authority_scope='SECURITY_KERNEL_INPUT'
            and key_source in ('INDEPENDENT_DEPLOYMENT_ROLE_SECRETS','DEVELOPMENT_DERIVED_ROLE_KEYS')"""
        ),
        {
            "id": bls_id,
            "user": user_id,
            "cart": cart["id"],
            "payload": cart_commitment(cart),
        },
    ).mappings().one_or_none()
    provenance = db.execute(
        text(
            """select 1 from provenance_records where id=:id and user_id=:user
            and entity_type='CART' and entity_id=:cart and source='SENTINELPAY_SECURITY_EVIDENCE'"""
        ),
        {"id": provenance_id, "user": user_id, "cart": cart["id"]},
    ).scalar()
    decisions = {item["role"]: item for item in bls["verifier_decisions"]} if bls else {}
    roles = set(bls["verifier_roles"]) if bls else set()
    bls_valid = bool(bls and bls["aggregate_valid"])
    return AdvancedSecurityEvidence(
        zk_budget_verified=bool(zk),
        mandate_verifier_approved=bls_valid
        and "MANDATE" in roles
        and decisions.get("MANDATE", {}).get("approved") is True,
        policy_verifier_approved=bls_valid
        and "POLICY" in roles
        and decisions.get("POLICY", {}).get("approved") is True,
        risk_verifier_approved=bls_valid
        and "RISK" in roles
        and decisions.get("RISK", {}).get("approved") is True,
        bls_aggregate_verified=bls_valid,
        provenance_trusted=bool(provenance),
        proof_references={key: str(value) for key, value in references.items()},
    )


@router.post("/checkout/prepare")
def checkout_prepare(
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    cart = load_cart(db, UUID(str(body["cart_id"])), user.id)
    advanced_required = bool(
        body.get("advanced_verification_required")
        or cart["total_minor"] >= settings.advanced_verification_threshold_minor
    )
    evidence = resolve_advanced_evidence(db, user.id, cart, body.get("advanced_evidence"))
    try:
        transaction = (
            db.execute(
                text(
                    "insert into transactions(cart_id,user_id,mandate_id,campaign_offer_id,status,idempotency_key,advanced_verification_required,advanced_evidence) values(:cart,:user,:mandate,:offer,'POLICY_CHECKING',:key,:advanced_required,cast(:advanced_evidence as jsonb)) returning *"
                ),
                {
                    "cart": cart["id"],
                    "user": user.id,
                    "mandate": cart["mandate_id"],
                    "offer": cart.get("campaign_offer_id"),
                    "key": body["idempotency_key"],
                    "advanced_required": advanced_required,
                    "advanced_evidence": evidence.model_dump_json() if evidence else None,
                },
            )
            .mappings()
            .one()
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Duplicate idempotency key") from exc
    mandate, policy, context = security_inputs(db, cart, dict(transaction))
    authority = {
        "product_scope": mandate["product_scope"],
        "max_total_amount_minor": mandate["max_total_amount_minor"],
        "currency": mandate["currency"],
        "max_quantity": mandate["max_quantity"],
        "allowed_conditions": mandate["allowed_conditions"],
        "preferred_brands": mandate["preferred_brands"],
        "excluded_brands": mandate["excluded_brands"],
        "negotiation_allowed": mandate["negotiation_allowed"],
        "upsell_allowed": mandate["upsell_allowed"],
        "cross_sell_allowed": mandate["cross_sell_allowed"],
        "campaign_offer_allowed": mandate["campaign_offer_allowed"],
        "auto_purchase_allowed": False,
        "expires_at": mandate["expires_at"].isoformat(),
    }
    outcome = SecurityKernel().authorize(
        context, cart, mandate["integrity_hash"], MandateService().hash(authority)
    )
    decision = outcome.get("decision")
    if not decision:
        decision = {
            "solver_result": outcome.get("solver_result", "ERROR"),
            "failed_constraints": [outcome.get("reason", "Unknown")],
            "assertions": [],
        }
    db.execute(
        text(
            "insert into policy_evaluations(transaction_id,buyer_mandate_id,merchant_policy_id,merchant_policy_version,campaign_id,input_snapshot,assertions,solver_result,failed_constraints,solver_version) values(:transaction,:mandate,:policy,:version,:campaign,cast(:snapshot as jsonb),cast(:assertions as jsonb),:result,cast(:failed as jsonb),'z3-unified-v1')"
        ),
        {
            "transaction": transaction["id"],
            "mandate": mandate["id"],
            "policy": policy["id"],
            "version": policy["version"],
            "campaign": context.campaign_policy.campaign_id if context.campaign_policy else None,
            "snapshot": context.model_dump_json(),
            "assertions": json.dumps(decision["assertions"]),
            "result": decision["solver_result"],
            "failed": json.dumps(decision["failed_constraints"]),
        },
    )
    status = {
        SecurityOutcome.ALLOW: "AUTHORIZED",
        SecurityOutcome.REQUIRE_APPROVAL: "REQUIRES_APPROVAL",
        SecurityOutcome.DENY: "DENIED",
    }[SecurityOutcome(outcome["outcome"])]
    db.execute(
        text("update transactions set status=:status where id=:id"),
        {"status": status, "id": transaction["id"]},
    )
    stale_campaign = bool(
        context.campaign_policy
        and outcome["outcome"] == SecurityOutcome.DENY
        and any(
            item.startswith("CAMPAIGN_") for item in decision.get("failed_constraints", [])
        )
    )
    if stale_campaign:
        db.execute(
            text(
                """update carts set total_minor=total_minor+campaign_discount_minor,
                discount_minor=discount_minor-campaign_discount_minor,campaign_discount_minor=0,
                campaign_id=null,campaign_offer_id=null,campaign_reconfirmation_required=true,
                status='CART_READY',version=version+1 where id=:cart"""
            ),
            {"cart": cart["id"]},
        )
        db.execute(
            text("update campaign_offers set status='EXPIRED' where id=:offer"),
            {"offer": cart["campaign_offer_id"]},
        )
        db.execute(
            text(
                """insert into campaign_events(campaign_id,merchant_id,event_type,actor_type,payload)
                values(:campaign,:merchant,'STALE_OFFER_REMOVED','SECURITY_KERNEL',cast(:payload as jsonb))"""
            ),
            {
                "campaign": context.campaign_policy.campaign_id,
                "merchant": cart["merchant_id"],
                "payload": json.dumps({"failed_constraints": decision["failed_constraints"]}),
            },
        )
    if outcome.get("approved_hash"):
        db.execute(
            text(
                "insert into cart_commitments(cart_id,transaction_id,approved_hash) values(:cart,:transaction,:hash)"
            ),
            {
                "cart": cart["id"],
                "transaction": transaction["id"],
                "hash": outcome["approved_hash"],
            },
        )
    ledger = AuditLedgerService()
    ledger.append(
        db,
        scope=f"TRANSACTION:{transaction['id']}",
        event_type="POLICY_VERIFIED",
        actor="SECURITY_KERNEL",
        payload={
            "solver_result": decision["solver_result"],
            "failed_constraints": decision["failed_constraints"],
        },
        user_id=user.id,
        merchant_id=cart["merchant_id"],
        transaction_id=transaction["id"],
    )
    ledger.append(
        db,
        scope=f"TRANSACTION:{transaction['id']}",
        event_type="CART_COMMITTED" if outcome.get("approved_hash") else "SECURITY_DENIED",
        actor="SECURITY_KERNEL",
        payload={"outcome": outcome["outcome"], "cart_version": cart["version"]},
        user_id=user.id,
        merchant_id=cart["merchant_id"],
        transaction_id=transaction["id"],
    )
    db.commit()
    return {
        "transaction_id": transaction["id"],
        **outcome,
        "cart_recalculated": stale_campaign,
        "requires_updated_confirmation": stale_campaign,
    }


@router.post("/checkout/{transaction_id}/confirm")
def confirm_checkout(
    transaction_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    row = (
        db.execute(
            text(
                "select t.*,cc.approved_hash from transactions t join cart_commitments cc on cc.transaction_id=t.id where t.id=:id and t.user_id=:user and t.status='REQUIRES_APPROVAL' for update"
            ),
            {"id": transaction_id, "user": user.id},
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(409, "Transaction does not require approval")
    cart = load_cart(db, row["cart_id"], user.id)
    outcome = SecurityKernel().confirm(cart, row["approved_hash"], body.get("confirmed") is True)
    if outcome != SecurityOutcome.ALLOW:
        raise HTTPException(409, "CART_MUTATED or confirmation missing")
    db.execute(
        text("update transactions set status='AUTHORIZED',human_confirmed=true where id=:id"),
        {"id": transaction_id},
    )
    db.commit()
    return {"transaction_id": transaction_id, "outcome": "ALLOW", "payment_created": False}


@router.post("/carts/{cart_id}/verify")
def verify_cart(
    cart_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    cart = load_cart(db, cart_id, user.id)
    return {
        "valid": SecurityKernel.verify_current_cart(cart, body["approved_hash"]),
        "canonical_cart": canonical_cart(cart),
    }


@router.post("/policy/verify")
def diagnostic_verify(
    body: UnifiedPolicyContext, user: AuthenticatedUser = Depends(get_current_user)
):
    return SecurityKernel().policy_service.evaluate(body)
