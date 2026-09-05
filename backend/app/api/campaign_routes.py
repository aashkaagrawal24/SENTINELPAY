import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.commerce_routes import load_cart, security_inputs
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.campaign import CampaignProposal
from app.services.analytics_services import CampaignAssignmentService
from app.services.audit_ledger import AuditLedgerService
from app.services.campaign_services import (
    CampaignEligibilityService,
    CampaignOpportunityService,
    CampaignService,
)
from app.services.mandate_service import MandateService
from app.services.merchant_services import MerchantService
from app.services.security_kernel import SecurityKernel

router = APIRouter(prefix="/api")


def event(
    db: Session,
    merchant_id: UUID,
    event_type: str,
    actor_type: str,
    campaign_id: UUID | None = None,
    opportunity_id: UUID | None = None,
    actor_id: UUID | None = None,
    payload: dict | None = None,
) -> None:
    db.execute(
        text(
            """insert into campaign_events(campaign_id,opportunity_id,merchant_id,event_type,actor_type,actor_id,payload)
            values(:campaign,:opportunity,:merchant,:event,:actor_type,:actor,cast(:payload as jsonb))"""
        ),
        {
            "campaign": campaign_id,
            "opportunity": opportunity_id,
            "merchant": merchant_id,
            "event": event_type,
            "actor_type": actor_type,
            "actor": actor_id,
            "payload": json.dumps(payload or {}),
        },
    )
    ledger_event = {
        "OPPORTUNITY_GENERATED": "CAMPAIGN_OPPORTUNITY_DETECTED",
        "CAMPAIGN_PROPOSED": "CAMPAIGN_PROPOSED",
        "CAMPAIGN_APPROVED": "CAMPAIGN_APPROVED",
        "CAMPAIGN_ACTIVE": "CAMPAIGN_STARTED",
        "OFFER_APPLIED": "CAMPAIGN_OFFER_SERVED",
    }.get(event_type)
    if ledger_event:
        scope_id = campaign_id or opportunity_id or merchant_id
        AuditLedgerService().append(
            db,
            scope=f"CAMPAIGN:{scope_id}",
            event_type=ledger_event,
            actor=actor_type,
            payload={"domain_event": event_type, **(payload or {})},
            user_id=actor_id,
            merchant_id=merchant_id,
        )


@router.post("/merchants/{merchant_id}/campaign-opportunities/scan")
def scan_opportunities(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    MerchantService.require_operator(db, merchant_id, user.id)
    rows = CampaignOpportunityService.scan(
        db,
        merchant_id,
        "MANUAL",
        settings.campaign_inventory_pressure_threshold,
        settings.campaign_score_weights,
    )
    for row in rows:
        event(
            db,
            merchant_id,
            "OPPORTUNITY_GENERATED",
            "MERCHANT",
            opportunity_id=row["id"],
            actor_id=user.id,
            payload={"score": float(row["score"]), "trigger": "MANUAL"},
        )
    db.commit()
    return rows


@router.post("/merchants/{merchant_id}/campaign-signals")
def realtime_signal(
    merchant_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    MerchantService.require_operator(db, merchant_id, user.id)
    signal = str(body.get("event_type"))
    if signal not in {
        "CART_ABANDONED",
        "INVENTORY_THRESHOLD_EXCEEDED",
        "PRODUCT_VIEW_SPIKE",
    }:
        raise HTTPException(422, "Unsupported campaign signal")
    event(db, merchant_id, signal, "INTERNAL_EVENT", actor_id=user.id)
    db.commit()
    return CampaignOpportunityService.scan(
        db,
        merchant_id,
        "REALTIME",
        settings.campaign_inventory_pressure_threshold,
        settings.campaign_score_weights,
    )


@router.get("/merchants/{merchant_id}/campaign-opportunities")
def list_opportunities(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.role(db, merchant_id, user.id)
    return [
        dict(row)
        for row in db.execute(
            text(
                "select * from campaign_opportunities where merchant_id=:merchant order by generated_at desc"
            ),
            {"merchant": merchant_id},
        ).mappings()
    ]


def validate_campaign_boundaries(
    db: Session, merchant_id: UUID, body: CampaignProposal
) -> None:
    policies = [
        dict(row)
        for row in db.execute(
            text(
                """select p.id product_id,p.base_price_minor,mp.minimum_sale_price_minor,
                mp.campaign_discount_limit_percent,mp.campaign_budget_limit_minor
                from merchant_products p join lateral (select candidate.* from merchant_policies candidate
                where candidate.merchant_id=p.merchant_id and candidate.status='ACTIVE' and candidate.valid_from<=now()
                and (candidate.valid_until is null or candidate.valid_until>now()) and (candidate.scope='GLOBAL'
                or candidate.scope='PRODUCT' and candidate.scope_reference=p.id::text or candidate.scope='CATEGORY' and candidate.scope_reference=p.category)
                order by case candidate.scope when 'PRODUCT' then 3 when 'CATEGORY' then 2 else 1 end desc,candidate.version desc limit 1) mp on true
                where p.merchant_id=:merchant and p.id=any(:products)"""
            ),
            {"merchant": merchant_id, "products": body.product_ids},
        ).mappings()
    ]
    if {row["product_id"] for row in policies} != set(body.product_ids):
        raise HTTPException(409, "Every campaign product requires an active merchant policy")
    for policy in policies:
        limit = policy["campaign_discount_limit_percent"]
        if body.discount_type == "PERCENT" and (
            limit is None or body.discount_value > float(limit) * 100
        ):
            if limit is None:
                raise HTTPException(409, "Campaign discount exceeds policy: No discount limit is set in the active policy.")
            raise HTTPException(409, f"Campaign discount exceeds policy: {body.discount_value / 100}% requested, but policy limits it to {float(limit)}%.")
            
        if body.discount_type == "FIXED" and body.discount_value > body.max_discount_per_order_minor:
            raise HTTPException(409, "Fixed discount exceeds per-order boundary")
            
        budget_limit = policy["campaign_budget_limit_minor"]
        if budget_limit is not None and body.total_discount_budget_minor > budget_limit:
            raise HTTPException(409, f"Campaign budget exceeds policy: {body.total_discount_budget_minor / 100} requested, limit is {budget_limit / 100}.")
            
        if body.minimum_final_price_minor is not None and body.minimum_final_price_minor < int(
            policy["minimum_sale_price_minor"]
        ):
            raise HTTPException(409, f"Campaign margin floor is below policy minimum price: Floor is {body.minimum_final_price_minor / 100}, but policy requires {int(policy['minimum_sale_price_minor']) / 100}.")


@router.post("/merchants/{merchant_id}/campaigns")
def propose_campaign(
    merchant_id: UUID,
    body: CampaignProposal,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.require_operator(db, merchant_id, user.id)
    validate_campaign_boundaries(db, merchant_id, body)
    if body.end_time <= body.start_time:
        raise HTTPException(422, "Campaign end time must follow start time")
    opportunity = None
    if body.opportunity_id:
        opportunity = db.execute(
            text(
                "select * from campaign_opportunities where id=:id and merchant_id=:merchant and status='OPEN' and expires_at>now() for update"
            ),
            {"id": body.opportunity_id, "merchant": merchant_id},
        ).mappings().one_or_none()
        if not opportunity:
            raise HTTPException(409, "Open opportunity required")
    row = (
        db.execute(
            text(
                """insert into campaigns(merchant_id,opportunity_id,name,campaign_type,objective,status,discount_type,discount_value,
                max_discount_per_order_minor,total_discount_budget_minor,maximum_redemptions,minimum_final_price_minor,
                eligibility,start_time,end_time,stop_conditions,created_by,requires_merchant_approval)
                values(:merchant,:opportunity,:name,:type,:objective,'PROPOSED',:discount_type,:discount_value,:max_discount,
                :budget,:redemptions,:floor,cast(:eligibility as jsonb),:start,:end,cast(:stops as jsonb),:creator,true) returning *"""
            ),
            {
                "merchant": merchant_id,
                "opportunity": body.opportunity_id,
                "name": body.name,
                "type": body.campaign_type,
                "objective": body.objective,
                "discount_type": body.discount_type,
                "discount_value": body.discount_value,
                "max_discount": body.max_discount_per_order_minor,
                "budget": body.total_discount_budget_minor,
                "redemptions": body.maximum_redemptions,
                "floor": body.minimum_final_price_minor,
                "eligibility": json.dumps(body.eligibility),
                "start": body.start_time,
                "end": body.end_time,
                "stops": json.dumps(body.stop_conditions),
                "creator": user.id,
            },
        )
        .mappings()
        .one()
    )
    for product_id in body.product_ids:
        db.execute(
            text("insert into campaign_products(campaign_id,product_id) values(:c,:p)"),
            {"c": row["id"], "p": product_id},
        )
    if opportunity:
        db.execute(
            text(
                "update campaign_opportunities set status='ACCEPTED',converted_campaign_id=:campaign where id=:id"
            ),
            {"campaign": row["id"], "id": opportunity["id"]},
        )
    event(db, merchant_id, "CAMPAIGN_PROPOSED", "MERCHANT", row["id"], body.opportunity_id, user.id)
    db.commit()
    return dict(row)


@router.post("/merchants/{merchant_id}/campaigns/{campaign_id}/approve")
def approve_campaign(
    merchant_id: UUID,
    campaign_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.require_operator(db, merchant_id, user.id)
    row = (
        db.execute(
            text(
                """update campaigns set status=case when start_time<=now() and end_time>now() then 'ACTIVE' else 'SCHEDULED' end,
                approved_by=:user,approved_at=now() where id=:id and merchant_id=:merchant and status='PROPOSED'
                and requires_merchant_approval and end_time>now() returning *"""
            ),
            {"user": user.id, "id": campaign_id, "merchant": merchant_id},
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(409, "Only a merchant-approved PROPOSED campaign may advance")
    event(db, merchant_id, "CAMPAIGN_APPROVED", "MERCHANT", campaign_id, actor_id=user.id)
    db.commit()
    return dict(row)


@router.get("/merchants/{merchant_id}/campaigns")
def list_campaigns(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.role(db, merchant_id, user.id)
    return [
        dict(row)
        for row in db.execute(
            text("select * from campaigns where merchant_id=:merchant order by created_at desc"),
            {"merchant": merchant_id},
        ).mappings()
    ]


@router.post("/merchants/{merchant_id}/campaigns/{campaign_id}/{action}")
def control_campaign(
    merchant_id: UUID,
    campaign_id: UUID,
    action: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.require_operator(db, merchant_id, user.id)
    target = {"pause": "PAUSED", "stop": "STOPPED"}.get(action)
    if not target:
        raise HTTPException(404, "Unknown campaign action")
    row = db.execute(
        text(
            "update campaigns set status=:status where id=:id and merchant_id=:merchant and status in ('ACTIVE','SCHEDULED','PAUSED') returning *"
        ),
        {"status": target, "id": campaign_id, "merchant": merchant_id},
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(409, "Campaign cannot transition from its current state")
    event(db, merchant_id, f"CAMPAIGN_{target}", "MERCHANT", campaign_id, actor_id=user.id)
    db.commit()
    return dict(row)


@router.post("/campaign-offers/eligible")
def eligible_offers(
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    cart = load_cart(db, UUID(str(body["cart_id"])), user.id)
    mandate = dict(
        db.execute(
            text("select * from mandates where id=:id and user_id=:user and status='ACTIVE'"),
            {"id": cart["mandate_id"], "user": user.id},
        ).mappings().one()
    )
    if not mandate["campaign_offer_allowed"]:
        return []
    cart_product_ids = [item["product_id"] for item in cart["items"]]
    cart_products = [str(product_id) for product_id in cart_product_ids]
    campaigns = db.execute(
        text(
            """select c.* from campaigns c
            where c.merchant_id=:merchant and c.status='ACTIVE' and c.start_time<=now() and c.end_time>now()
            and exists (select 1 from campaign_products cp where cp.campaign_id=c.id and cp.product_id=any(:products)) and c.used_discount_budget_minor+c.reserved_discount_budget_minor<c.total_discount_budget_minor
            and c.current_redemptions+c.reserved_redemptions<c.maximum_redemptions for update"""
        ),
        {"merchant": cart["merchant_id"], "products": cart_product_ids},
    ).mappings()
    offers = []
    for campaign_row in campaigns:
        campaign = dict(campaign_row)
        products = {
            str(value)
            for value in db.execute(
                text("select product_id from campaign_products where campaign_id=:id"),
                {"id": campaign["id"]},
            ).scalars()
        }
        eligibility = CampaignEligibilityService.evaluate(campaign, mandate, cart, products)
        if not eligibility["eligible"]:
            continue
        assignment = CampaignAssignmentService.assign(
            db,
            campaign["id"],
            mandate["id"],
            int(campaign["control_percentage"]),
            bool(campaign["experiment_enabled"]),
        )
        if assignment["assignment_group"] == "CONTROL":
            continue
        eligible_subtotal = sum(
            int(item["unit_price_minor"]) * int(item["quantity"])
            for item in cart["items"]
            if str(item["product_id"]) in products
        )
        discount = CampaignService.discount_minor(campaign, eligible_subtotal)
        if discount <= 0:
            continue
        offer = (
            db.execute(
                text(
                    """insert into campaign_offers(campaign_id,user_id,mandate_id,product_id,discount_minor,eligibility_snapshot,expires_at,assignment_id)
                    values(:campaign,:user,:mandate,:product,:discount,cast(:eligibility as jsonb),:expires,:assignment)
                    on conflict(campaign_id,mandate_id,product_id) do update set discount_minor=excluded.discount_minor,
                    eligibility_snapshot=excluded.eligibility_snapshot,expires_at=excluded.expires_at,status='ELIGIBLE'
                    where campaign_offers.status in ('ELIGIBLE','EXPIRED','REVOKED') returning *"""
                ),
                {
                    "campaign": campaign["id"],
                    "user": user.id,
                    "mandate": mandate["id"],
                    "product": next(iter(products & set(cart_products))),
                    "discount": discount,
                    "eligibility": json.dumps(eligibility),
                    "expires": campaign["end_time"],
                    "assignment": assignment["id"],
                },
            )
            .mappings()
            .one_or_none()
        )
        if offer:
            offers.append(
                {
                    "offer_id": offer["id"],
                    "campaign_id": campaign["id"],
                    "name": campaign["name"],
                    "objective": campaign["objective"],
                    "discount_minor": discount,
                    "expires_at": campaign["end_time"],
                    "source": "VERIFIED_CAMPAIGN",
                    "eligibility": eligibility,
                }
            )
    db.commit()
    return offers


def mandate_hash(mandate: dict) -> str:
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
    return MandateService().hash(authority)


@router.post("/campaign-offers/{offer_id}/apply")
def apply_offer(
    offer_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    cart = load_cart(db, UUID(str(body["cart_id"])), user.id)
    if cart.get("campaign_offer_id"):
        raise HTTPException(409, "Cart already has a campaign offer")
    offer = db.execute(
        text(
            """select o.*,c.merchant_id,c.status campaign_status,c.start_time,c.end_time,
            c.used_discount_budget_minor,c.reserved_discount_budget_minor,c.total_discount_budget_minor,
            c.current_redemptions,c.reserved_redemptions,c.maximum_redemptions
            from campaign_offers o join campaigns c on c.id=o.campaign_id
            where o.id=:offer and o.user_id=:user and o.mandate_id=:mandate and c.merchant_id=:merchant
            and o.status='ELIGIBLE' for update"""
        ),
        {
            "offer": offer_id,
            "user": user.id,
            "mandate": cart["mandate_id"],
            "merchant": cart["merchant_id"],
        },
    ).mappings().one_or_none()
    now = datetime.now(UTC)
    if not offer or offer["campaign_status"] != "ACTIVE" or not (
        offer["start_time"] <= now < min(offer["end_time"], offer["expires_at"])
    ):
        raise HTTPException(409, "Campaign offer is inactive or expired")
    if int(offer["used_discount_budget_minor"]) + int(
        offer["reserved_discount_budget_minor"]
    ) + int(offer["discount_minor"]) > int(offer["total_discount_budget_minor"]):
        raise HTTPException(409, "Campaign budget exhausted")
    if int(offer["current_redemptions"]) + int(offer["reserved_redemptions"]) >= int(
        offer["maximum_redemptions"]
    ):
        raise HTTPException(409, "Campaign redemptions exhausted")
    if int(offer["discount_minor"]) > int(cart["total_minor"]):
        raise HTTPException(409, "Campaign discount exceeds cart total")
    db.execute(
        text(
            """update carts set discount_minor=discount_minor+:discount,total_minor=total_minor-:discount,
            campaign_discount_minor=:discount,campaign_id=:campaign,campaign_offer_id=:offer,
            campaign_reconfirmation_required=false,version=version+1 where id=:cart"""
        ),
        {
            "discount": offer["discount_minor"],
            "campaign": offer["campaign_id"],
            "offer": offer_id,
            "cart": cart["id"],
        },
    )
    db.execute(
        text("update campaign_offers set status='APPLIED',cart_id=:cart,applied_at=now() where id=:id"),
        {"cart": cart["id"], "id": offer_id},
    )
    modified = load_cart(db, cart["id"], user.id)
    mandate, _policy, context = security_inputs(db, modified)
    outcome = SecurityKernel().authorize(
        context, modified, mandate["integrity_hash"], mandate_hash(mandate)
    )
    if outcome["outcome"] == "DENY":
        failed = outcome.get("decision", {}).get("failed_constraints", [])
        db.rollback()
        if "CAMPAIGN_MARGIN" in failed:
            db.execute(
                text("update campaigns set status='PAUSED' where id=:id"),
                {"id": offer["campaign_id"]},
            )
            event(
                db,
                offer["merchant_id"],
                "CAMPAIGN_AUTO_STOPPED",
                "SECURITY_KERNEL",
                offer["campaign_id"],
                payload={"reason": "MARGIN_RULE_VIOLATION"},
            )
            db.commit()
        raise HTTPException(409, {"message": "Campaign cart denied", "decision": outcome})
    event(
        db,
        offer["merchant_id"],
        "OFFER_APPLIED",
        "BUYER",
        offer["campaign_id"],
        actor_id=user.id,
        payload={"offer_id": str(offer_id), "discount_minor": offer["discount_minor"]},
    )
    db.commit()
    return {"cart": modified, "campaign": dict(offer), "security_recommit": outcome}
