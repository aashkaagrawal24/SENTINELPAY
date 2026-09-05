import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.commerce_routes import load_cart, security_inputs
from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.db.session import get_db_session
from app.schemas.negotiation import NegotiationActor, NegotiationState
from app.services.audit_ledger import AuditLedgerService
from app.services.mandate_service import MandateService
from app.services.negotiation_service import BasketGrowthEngine, NegotiationController
from app.services.security_kernel import SecurityKernel

router = APIRouter(prefix="/api")


def safe_session(row: dict) -> dict:
    allowed = {
        "id",
        "mandate_id",
        "merchant_id",
        "product_id",
        "starting_price_minor",
        "buyer_ceiling_minor",
        "fallback_price_minor",
        "fallback_valid_until",
        "current_round",
        "max_rounds",
        "last_buyer_offer_minor",
        "last_merchant_ask_minor",
        "status",
        "final_agreed_price_minor",
        "created_at",
        "expires_at",
    }
    return {key: value for key, value in row.items() if key in allowed}


def state_from_row(row: dict) -> NegotiationState:
    return NegotiationState.model_validate({key: row[key] for key in NegotiationState.model_fields})


def authority_hash(mandate: dict) -> str:
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


@router.post("/negotiations")
def create_negotiation(
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    mandate = (
        db.execute(
            text("select * from mandates where id=:id and user_id=:user and status='ACTIVE'"),
            {"id": body["mandate_id"], "user": user.id},
        )
        .mappings()
        .one_or_none()
    )
    if not mandate or not mandate["negotiation_allowed"]:
        raise HTTPException(403, "Active mandate with negotiation permission required")
    product = (
        db.execute(
            text("select * from merchant_products where id=:id and active"),
            {"id": body["product_id"]},
        )
        .mappings()
        .one_or_none()
    )
    if not product:
        raise HTTPException(404, "Product not found")
    policy = (
        db.execute(
            text(
                "select * from merchant_policies where merchant_id=:merchant and status='ACTIVE' and negotiation_enabled and valid_from<=now() and (valid_until is null or valid_until>now()) and (scope='GLOBAL' or (scope='CATEGORY' and scope_reference=:category) or (scope='PRODUCT' and scope_reference=:product)) order by case scope when 'PRODUCT' then 3 when 'CATEGORY' then 2 else 1 end desc,version desc limit 1"
            ),
            {
                "merchant": product["merchant_id"],
                "category": product["category"],
                "product": str(product["id"]),
            },
        )
        .mappings()
        .one_or_none()
    )
    if not policy:
        raise HTTPException(409, "Merchant does not support negotiation for this product")
    now = datetime.now(UTC)
    max_budget = int(mandate["max_total_amount_minor"])
    starting = int(product["base_price_minor"])
    ceiling = min(max_budget, starting)
    fallback_price = starting if starting <= max_budget else None
    status = "OPEN" if int(policy["minimum_sale_price_minor"]) <= max_budget else "REJECTED"
    row = (
        db.execute(
            text(
                "insert into negotiation_sessions(buyer_user_id,mandate_id,merchant_id,product_id,merchant_policy_id,merchant_policy_version,starting_price_minor,buyer_ceiling_minor,merchant_floor_minor,fallback_price_minor,fallback_valid_until,current_round,max_rounds,status,expires_at) values(:user,:mandate,:merchant,:product,:policy,:version,:starting,:ceiling,:floor,:fallback,:fallback_until,0,:max_rounds,:status,:expires) returning *"
            ),
            {
                "user": user.id,
                "mandate": mandate["id"],
                "merchant": product["merchant_id"],
                "product": product["id"],
                "policy": policy["id"],
                "version": policy["version"],
                "starting": starting,
                "ceiling": ceiling,
                "floor": policy["minimum_sale_price_minor"],
                "fallback": fallback_price,
                "fallback_until": now + timedelta(minutes=5) if fallback_price else None,
                "max_rounds": max(1, int(policy["max_negotiation_rounds"])),
                "status": status,
                "expires": min(mandate["expires_at"].astimezone(UTC), now + timedelta(minutes=15)),
            },
        )
        .mappings()
        .one()
    )
    db.execute(
        text(
            "insert into negotiation_messages(session_id,actor,round_number,text,structured_action) values(:session,'SYSTEM',0,:message,:action)"
        ),
        {
            "session": row["id"],
            "message": "Negotiation opened with deterministic private boundaries."
            if status == "OPEN"
            else "No overlapping legal price range.",
            "action": "OPEN" if status == "OPEN" else "REJECT",
        },
    )
    AuditLedgerService().append(
        db,
        scope=f"NEGOTIATION:{row['id']}",
        event_type="NEGOTIATION_STARTED",
        actor="BUYER_AGENT",
        payload={"session_id": str(row["id"]), "status": status},
        user_id=user.id,
        merchant_id=product["merchant_id"],
    )
    db.commit()
    response = safe_session(dict(row))
    response["decision"] = "CONTINUE" if status == "OPEN" else "REJECT"
    response["reason_code"] = "BOUNDS_VALID" if status == "OPEN" else "NO_OVERLAPPING_RANGE"
    return response


@router.post("/negotiations/{session_id}/step")
def negotiation_step(
    session_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    row = (
        db.execute(
            text(
                "select * from negotiation_sessions where id=:id and buyer_user_id=:user for update"
            ),
            {"id": session_id, "user": user.id},
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "Negotiation not found")
    if body.get("actor", NegotiationActor.BUYER_AGENT) != NegotiationActor.BUYER_AGENT:
        raise HTTPException(403, "MerchantAgent turns are server-owned")
    controller = NegotiationController()
    actor = NegotiationActor.BUYER_AGENT
    updated, decision = controller.step(
        state_from_row(dict(row)), actor, int(body["proposed_amount_minor"])
    )
    messages = [
        {
            "actor": actor.value,
            "round": updated.current_round,
            "message": str(body.get("text", "Bounded structured offer"))[:1000],
            "amount": body["proposed_amount_minor"],
            "action": decision.decision,
            "provider": body.get("model_provider"),
            "model": body.get("model_name"),
            "model_version": body.get("model_version"),
        }
    ]
    if decision.decision == "CONTINUE":
        previous_ask = updated.last_merchant_ask_minor or updated.starting_price_minor
        counter_amount = min(
            updated.starting_price_minor,
            max(
                updated.merchant_floor_minor,
                (previous_ask + int(body["proposed_amount_minor"]) + 1) // 2,
            ),
        )
        updated, decision = controller.step(
            updated, NegotiationActor.MERCHANT_AGENT, counter_amount
        )
        messages.append(
            {
                "actor": NegotiationActor.MERCHANT_AGENT.value,
                "round": updated.current_round,
                "message": "MerchantAgent generated a deterministic bounded counter.",
                "amount": counter_amount,
                "action": decision.decision,
                "provider": None,
                "model": None,
                "model_version": None,
            }
        )
    db.execute(
        text(
            "update negotiation_sessions set current_round=:round,last_buyer_offer_minor=:buyer,last_merchant_ask_minor=:merchant,status=:status,final_agreed_price_minor=:final where id=:id"
        ),
        {
            "round": updated.current_round,
            "buyer": updated.last_buyer_offer_minor,
            "merchant": updated.last_merchant_ask_minor,
            "status": updated.status.value,
            "final": updated.final_agreed_price_minor,
            "id": session_id,
        },
    )
    for message in messages:
        db.execute(
            text(
                "insert into negotiation_messages(session_id,actor,round_number,text,proposed_amount_minor,structured_action,model_provider,model_name,model_version) values(:session,:actor,:round,:message,:amount,:action,:provider,:model,:model_version)"
            ),
            {"session": session_id, **message},
        )
    AuditLedgerService().append(
        db,
        scope=f"NEGOTIATION:{session_id}",
        event_type="COUNTEROFFER_RECEIVED",
        actor="MERCHANT_AGENT",
        payload={
            "session_id": str(session_id),
            "decision": decision.decision,
            "round": updated.current_round,
        },
        user_id=user.id,
        merchant_id=row["merchant_id"],
    )
    db.commit()
    response = safe_session({**dict(row), **updated.model_dump()})
    response.update(decision=decision.decision, reason_code=decision.reason_code)
    return response


@router.get("/negotiations/{session_id}")
def get_negotiation(
    session_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    row = (
        db.execute(
            text("select * from negotiation_sessions where id=:id and buyer_user_id=:user"),
            {"id": session_id, "user": user.id},
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "Negotiation not found")
    messages = [
        dict(item)
        for item in db.execute(
            text(
                "select actor,round_number,text,proposed_amount_minor,structured_action,created_at from negotiation_messages where session_id=:id order by created_at"
            ),
            {"id": session_id},
        ).mappings()
    ]
    return {**safe_session(dict(row)), "messages": messages}


@router.post("/negotiations/{session_id}/apply-to-cart")
def apply_negotiation_to_cart(
    session_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    session = (
        db.execute(
            text(
                "select * from negotiation_sessions where id=:id and buyer_user_id=:user and status in ('ACCEPTED','FALLBACK') for update"
            ),
            {"id": session_id, "user": user.id},
        )
        .mappings()
        .one_or_none()
    )
    if not session:
        raise HTTPException(409, "Negotiation has no applicable final price")
    cart = load_cart(db, UUID(str(body["cart_id"])), user.id)
    if db.execute(
        text(
            "select 1 from payment_attempts pa join transactions t on t.id=pa.transaction_id where t.cart_id=:cart and pa.status in ('CREATED','ORDER_CREATED','PAYMENT_PENDING','CAPTURED','UNKNOWN')"
        ),
        {"cart": cart["id"]},
    ).scalar():
        raise HTTPException(409, "Cannot modify cart with active payment attempt")
    item = (
        db.execute(
            text("select * from cart_items where cart_id=:cart and product_id=:product for update"),
            {"cart": cart["id"], "product": session["product_id"]},
        )
        .mappings()
        .one_or_none()
    )
    if not item:
        raise HTTPException(404, "Negotiated product is not in cart")
    final_price = int(session["final_agreed_price_minor"])
    old_total = int(item["unit_price_minor"]) * int(item["quantity"])
    new_total = final_price * int(item["quantity"])
    discount = old_total - new_total
    db.execute(
        text(
            "update cart_items set unit_price_minor=:price,product_snapshot=jsonb_set(product_snapshot,'{negotiation}',cast(:negotiation as jsonb),true) where id=:id"
        ),
        {
            "price": final_price,
            "negotiation": json.dumps(
                {
                    "session_id": str(session_id),
                    "policy_id": str(session["merchant_policy_id"]),
                    "policy_version": session["merchant_policy_version"],
                }
            ),
            "id": item["id"],
        },
    )
    db.execute(
        text(
            "update carts set subtotal_minor=subtotal_minor-:old+:new,discount_minor=discount_minor+:discount,total_minor=total_minor-:old+:new,version=version+1,status='CART_READY' where id=:cart"
        ),
        {"old": old_total, "new": new_total, "discount": discount, "cart": cart["id"]},
    )
    modified = load_cart(db, cart["id"], user.id)
    mandate, _policy, context = security_inputs(db, modified)
    outcome = SecurityKernel().authorize(
        context, modified, mandate["integrity_hash"], authority_hash(mandate)
    )
    if outcome["outcome"] == "DENY":
        db.rollback()
        raise HTTPException(
            409, {"message": "Negotiated cart failed SecurityKernel", "decision": outcome}
        )
    db.execute(
        text("update negotiation_sessions set fallback_cart_id=:cart where id=:id"),
        {"cart": cart["id"], "id": session_id},
    )
    db.commit()
    return {"cart": modified, "security_recommit": outcome}


def relationship_rows(db: Session, source_product_id: UUID) -> list[dict]:
    return [
        dict(row)
        for row in db.execute(
            text(
                "select mr.source_product_id,mr.target_product_id offered_product_id,mr.relationship_type,mr.active,p.name,p.base_price_minor price_minor,p.currency,coalesce(sum(mi.available_quantity-mi.reserved_quantity),0) inventory_available from merchant_relationships mr join merchant_products p on p.id=mr.target_product_id left join merchant_inventory mi on mi.product_id=p.id where mr.source_product_id=:source and p.active group by mr.source_product_id,mr.target_product_id,mr.relationship_type,mr.active,p.name,p.base_price_minor,p.currency,mr.priority order by mr.priority desc"
            ),
            {"source": source_product_id},
        ).mappings()
    ]


@router.post("/growth/recommendations")
def growth_recommendations(
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    mandate = (
        db.execute(
            text("select * from mandates where id=:id and user_id=:user and status='ACTIVE'"),
            {"id": body["mandate_id"], "user": user.id},
        )
        .mappings()
        .one_or_none()
    )
    if not mandate:
        raise HTTPException(404, "Active mandate not found")
    cart = load_cart(db, UUID(str(body["cart_id"])), user.id) if body.get("cart_id") else None
    spent = int(cart["total_minor"]) if cart else int(body.get("current_total_minor", 0))
    quantity = (
        sum(item["quantity"] for item in cart["items"])
        if cart
        else int(body.get("current_quantity", 1))
    )
    relationships = relationship_rows(db, UUID(str(body["source_product_id"])))
    engine = BasketGrowthEngine()
    remaining_budget = int(mandate["max_total_amount_minor"]) - spent
    remaining_quantity = int(mandate["max_quantity"]) - quantity
    upsells = engine.eligible(
        relationships,
        "UPSELL",
        bool(mandate["upsell_allowed"]),
        remaining_budget,
        remaining_quantity,
    )
    cross_relationships = [
        {**row, "relationship_type": "CROSS_SELL"}
        if row["relationship_type"] == "ACCESSORY"
        else row
        for row in relationships
    ]
    cross_sells = engine.eligible(
        cross_relationships,
        "CROSS_SELL",
        bool(mandate["cross_sell_allowed"]),
        remaining_budget,
        remaining_quantity,
    )
    event_ids = {}
    for kind, candidates in (("upsell", upsells), ("cross_sell", cross_sells)):
        table = "upsell_events" if kind == "upsell" else "cross_sell_events"
        for candidate in candidates:
            event_id = db.execute(
                text(
                    f"insert into {table}(user_id,mandate_id,merchant_id,source_product_id,offered_product_id,cart_id,offered_amount_minor) select :user,:mandate,p.merchant_id,:source,:offered,:cart,:amount from merchant_products p where p.id=:source returning id"
                ),
                {
                    "user": user.id,
                    "mandate": mandate["id"],
                    "source": candidate["source_product_id"],
                    "offered": candidate["offered_product_id"],
                    "cart": cart["id"] if cart else None,
                    "amount": candidate["price_minor"],
                },
            ).scalar_one()
            event_ids[str(candidate["offered_product_id"])] = str(event_id)
    if upsells:
        AuditLedgerService().append(
            db,
            scope=f"MANDATE:{mandate['id']}",
            event_type="UPSELL_OFFERED",
            actor="BUYER_AGENT",
            payload={"product_ids": [str(item["offered_product_id"]) for item in upsells]},
            user_id=user.id,
            merchant_id=cart["merchant_id"] if cart else None,
        )
    db.commit()
    return {
        "upsells": upsells,
        "cross_sells": cross_sells,
        "event_ids": event_ids,
        "auto_added": False,
        "requires_confirmation": True,
    }


@router.post("/growth/{event_type}/{event_id}/accept")
def accept_growth(
    event_type: str,
    event_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    table = {"upsell": "upsell_events", "cross_sell": "cross_sell_events"}.get(event_type)
    if not table:
        raise HTTPException(404, "Unknown growth event type")
    event = (
        db.execute(
            text(f"select * from {table} where id=:id and user_id=:user for update"),
            {"id": event_id, "user": user.id},
        )
        .mappings()
        .one_or_none()
    )
    if not event or event["accepted"]:
        raise HTTPException(409, "Growth event unavailable")
    mandate = dict(
        db.execute(
            text(
                "select * from mandates where id=:id and user_id=:user and status='ACTIVE' for update"
            ),
            {"id": event["mandate_id"], "user": user.id},
        )
        .mappings()
        .one()
    )
    permission = (
        mandate["upsell_allowed"] if event_type == "upsell" else mandate["cross_sell_allowed"]
    )
    if not permission or body.get("confirmed") is not True:
        raise HTTPException(403, "Explicit buyer permission and confirmation required")
    cart = load_cart(db, UUID(str(body["cart_id"])), user.id)
    if db.execute(
        text(
            "select 1 from payment_attempts pa join transactions t on t.id=pa.transaction_id where t.cart_id=:cart and pa.status in ('CREATED','ORDER_CREATED','PAYMENT_PENDING','CAPTURED','UNKNOWN')"
        ),
        {"cart": cart["id"]},
    ).scalar():
        raise HTTPException(409, "Cannot modify cart with active payment attempt")
    product = (
        db.execute(
            text(
                "select p.*,coalesce(sum(mi.available_quantity-mi.reserved_quantity),0) inventory_available from merchant_products p left join merchant_inventory mi on mi.product_id=p.id where p.id=:id and p.active group by p.id"
            ),
            {"id": event["offered_product_id"]},
        )
        .mappings()
        .one()
    )
    if product["inventory_available"] <= 0 or product["merchant_id"] != cart["merchant_id"]:
        raise HTTPException(409, "Offered product is unavailable")
    db.execute(
        text(
            "insert into cart_items(cart_id,product_id,quantity,unit_price_minor,condition,product_snapshot,source_version) values(:cart,:product,1,:price,:condition,cast(:snapshot as jsonb),:version)"
        ),
        {
            "cart": cart["id"],
            "product": product["id"],
            "price": product["base_price_minor"],
            "condition": product["condition"],
            "snapshot": json.dumps(dict(product), default=str),
            "version": product["updated_at"],
        },
    )
    db.execute(
        text(
            "update carts set subtotal_minor=subtotal_minor+:price,total_minor=total_minor+:price,version=version+1,status='CART_READY' where id=:cart"
        ),
        {"price": product["base_price_minor"], "cart": cart["id"]},
    )
    modified = load_cart(db, cart["id"], user.id)
    mandate_row, _policy, context = security_inputs(db, modified)
    outcome = SecurityKernel().authorize(
        context, modified, mandate_row["integrity_hash"], authority_hash(mandate_row)
    )
    if outcome["outcome"] == "DENY":
        db.rollback()
        raise HTTPException(
            409, {"message": "Modified basket failed SecurityKernel", "decision": outcome}
        )
    db.execute(
        text(
            f"update {table} set accepted=true,cart_id=:cart,incremental_revenue_minor=:amount,recommit_result=:result,recommit_hash=:hash,accepted_at=now() where id=:id"
        ),
        {
            "cart": cart["id"],
            "amount": product["base_price_minor"],
            "result": outcome["outcome"],
            "hash": outcome["approved_hash"],
            "id": event_id,
        },
    )
    if event_type == "upsell":
        AuditLedgerService().append(
            db,
            scope=f"MANDATE:{mandate['id']}",
            event_type="UPSELL_ACCEPTED",
            actor="BUYER",
            payload={
                "event_id": str(event_id),
                "product_id": str(product["id"]),
                "recommit_result": outcome["outcome"],
            },
            user_id=user.id,
            merchant_id=product["merchant_id"],
        )
    db.commit()
    return {"accepted": True, "cart": modified, "security_recommit": outcome}
