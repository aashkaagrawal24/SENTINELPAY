"""
SentinelPay — Bulk Commerce API Routes
========================================
Endpoints:
  POST   /api/bulk/rfqs                               — Create RFQ (buyer)
  GET    /api/bulk/rfqs/{rfq_id}                      — Get RFQ detail
  GET    /api/bulk/rfqs/merchant/{merchant_id}        — Merchant: incoming RFQs
  POST   /api/bulk/rfqs/{rfq_id}/analyze              — MerchantAgent: inventory + pricing analysis
  POST   /api/bulk/rfqs/{rfq_id}/quote                — MerchantAgent: send quote
  POST   /api/bulk/negotiations/{neg_id}/counter      — Counter-offer (buyer or merchant)
  POST   /api/bulk/negotiations/{neg_id}/accept       — Accept → create inventory reservation
  POST   /api/bulk/negotiations/{neg_id}/reject       — Reject negotiation
  POST   /api/bulk/quotes/simulate                    — Merchant edits AI quote, recalculate
  GET    /api/bulk/opportunities/{merchant_id}        — Revenue intelligence opportunities
  GET    /api/bulk/analytics/{merchant_id}            — Bulk revenue analytics
  GET    /api/bulk/policies/{merchant_id}             — Get bulk policy rules
  POST   /api/bulk/policies/{merchant_id}             — Create/approve bulk policy rule
  POST   /api/bulk/products/{product_id}/bulk-enable — Enable bulk for a product
  GET    /api/bulk/reservations/{product_id}          — Reservation status
  POST   /api/bulk/reservations/{reservation_id}/release — Release reservation
"""

import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.db.session import get_db_session
from app.services.audit_ledger import AuditLedgerService
from app.services.bulk_commerce_service import (
    BulkOpportunityDetector,
    BulkPolicyEngine,
    BulkPricingOptimizer,
    BuyerBulkAgent,
    InventoryReservationService,
    MerchantBulkAgent,
)
from app.services.event_dispatcher import dispatcher

router = APIRouter(prefix="/api/bulk")


# ─── helpers ─────────────────────────────────────────────────────────────────

def _require_merchant_role(db: Session, merchant_id: UUID, user_id: UUID) -> None:
    ok = db.execute(
        text("SELECT 1 FROM merchant_users WHERE merchant_id=:m AND user_id=:u"),
        {"m": merchant_id, "u": user_id},
    ).scalar()
    if not ok:
        raise HTTPException(403, "Merchant access required")


def _get_rfq(db: Session, rfq_id: UUID) -> dict:
    row = db.execute(
        text("SELECT * FROM bulk_rfqs WHERE id=:id"),
        {"id": rfq_id},
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(404, "RFQ not found")
    return dict(row)


def _get_negotiation(db: Session, neg_id: UUID) -> dict:
    row = db.execute(
        text("SELECT * FROM bulk_negotiations WHERE id=:id"),
        {"id": neg_id},
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(404, "Negotiation not found")
    return dict(row)


def _emit(db: Session, event_type: str, rfq_id: UUID | None, merchant_id: UUID | None, payload: dict):
    """Emit to agent activity stream and audit log."""
    try:
        dispatcher.emit(event_type, {
            "rfq_id": str(rfq_id) if rfq_id else None,
            "merchant_id": str(merchant_id) if merchant_id else None,
            "commerce_type": "BULK",
            **payload,
        })
    except Exception:
        pass  # Activity stream failure must never break the main flow

    if merchant_id:
        try:
            AuditLedgerService().append(
                db,
                scope=f"BULK_RFQ:{rfq_id}",
                event_type=event_type,
                actor="BULK_COMMERCE_SERVICE",
                payload=payload,
            )
        except Exception:
            pass


# ─── POST /api/bulk/rfqs — Create RFQ ────────────────────────────────────────

@router.post("/rfqs")
def create_bulk_rfq(
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    product_id = UUID(str(body["product_id"]))
    merchant_id = UUID(str(body["merchant_id"]))
    quantity = int(body["requested_quantity"])

    # Validate product exists and is bulk-eligible
    product = db.execute(
        text("SELECT * FROM merchant_products WHERE id=:pid AND merchant_id=:mid AND active"),
        {"pid": product_id, "mid": merchant_id},
    ).mappings().one_or_none()
    if not product:
        raise HTTPException(404, "Product not found or not active")

    product = dict(product)
    bulk_min = int(product.get("bulk_min_quantity") or 50)

    if not product.get("bulk_enabled") and quantity >= bulk_min:
        # Auto-enable check: if quantity meets threshold, proceed anyway
        # (merchant can enable later; RFQ creation is always allowed)
        pass

    # Private buyer constraints stored in DB but never returned to merchant
    private_max_budget = body.get("private_max_budget_minor")
    private_target = body.get("private_target_unit_price_minor")

    row = db.execute(
        text("""
            INSERT INTO bulk_rfqs (
                buyer_user_id, merchant_id, product_id, requested_quantity,
                required_by, delivery_mode, allow_substitutes, negotiation_enabled,
                split_delivery, private_max_budget_minor, private_target_unit_price_minor,
                status
            ) VALUES (
                :buyer, :mid, :pid, :qty,
                :required_by, :delivery_mode, :substitutes, :negotiation,
                :split, :budget, :target,
                'SUBMITTED'
            ) RETURNING id, status, created_at, expires_at
        """),
        {
            "buyer": user.id,
            "mid": merchant_id,
            "pid": product_id,
            "qty": quantity,
            "required_by": body.get("required_by"),
            "delivery_mode": body.get("delivery_mode", "SINGLE"),
            "substitutes": bool(body.get("allow_substitutes", False)),
            "negotiation": bool(body.get("negotiation_enabled", True)),
            "split": bool(body.get("split_delivery", False)),
            "budget": private_max_budget,
            "target": private_target,
        },
    ).mappings().one()

    db.commit()
    rfq_id = row["id"]

    _emit(db, "BULK_RFQ_CREATED", rfq_id, merchant_id, {
        "product_id": str(product_id),
        "requested_quantity": quantity,
        "product_name": product.get("name"),
    })

    return {
        "rfq_id": str(rfq_id),
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
        "expires_at": row["expires_at"].isoformat(),
        "product": {
            "id": str(product_id),
            "name": product.get("name"),
            "base_price_inr": round(int(product.get("base_price_minor") or 0) / 100, 2),
        },
        "requested_quantity": quantity,
        "bulk_min_quantity": bulk_min,
        "is_bulk": quantity >= bulk_min,
    }


# ─── GET /api/bulk/rfqs/{rfq_id} — Get RFQ ───────────────────────────────────

@router.get("/rfqs/{rfq_id}")
def get_rfq(
    rfq_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    rfq = _get_rfq(db, rfq_id)

    # Buyer or merchant member can read
    is_buyer = str(rfq["buyer_user_id"]) == str(user.id)
    is_merchant = db.execute(
        text("SELECT 1 FROM merchant_users WHERE merchant_id=:m AND user_id=:u"),
        {"m": rfq["merchant_id"], "u": user.id},
    ).scalar()

    if not is_buyer and not is_merchant:
        raise HTTPException(403, "Access denied")

    product = db.execute(
        text("SELECT id, name, base_price_minor, category FROM merchant_products WHERE id=:pid"),
        {"pid": rfq["product_id"]},
    ).mappings().one_or_none()

    negotiation = db.execute(
        text("SELECT * FROM bulk_negotiations WHERE rfq_id=:rfq"),
        {"rfq": rfq_id},
    ).mappings().one_or_none()

    events = []
    if negotiation:
        events = [
            dict(e) for e in db.execute(
                text("SELECT * FROM bulk_negotiation_events WHERE negotiation_id=:neg ORDER BY sequence"),
                {"neg": negotiation["id"]},
            ).mappings().fetchall()
        ]

    # Privacy: strip private buyer fields when responding to merchant
    response = {
        "rfq_id": str(rfq["id"]),
        "merchant_id": str(rfq["merchant_id"]),
        "product_id": str(rfq["product_id"]),
        "product": dict(product) if product else None,
        "requested_quantity": rfq["requested_quantity"],
        "required_by": rfq["required_by"].isoformat() if rfq.get("required_by") else None,
        "delivery_mode": rfq["delivery_mode"],
        "allow_substitutes": rfq["allow_substitutes"],
        "negotiation_enabled": rfq["negotiation_enabled"],
        "split_delivery": rfq["split_delivery"],
        "status": rfq["status"],
        "created_at": rfq["created_at"].isoformat(),
        "expires_at": rfq["expires_at"].isoformat(),
        "negotiation": dict(negotiation) if negotiation else None,
        "events": [
            {k: v for k, v in e.items() if k not in ("id",)}
            for e in events
        ],
    }

    # Only buyer sees their own private constraints
    if is_buyer:
        response["private_max_budget_minor"] = rfq.get("private_max_budget_minor")
        response["private_target_unit_price_minor"] = rfq.get("private_target_unit_price_minor")

    return response


# ─── GET /api/bulk/rfqs/merchant/{merchant_id} — Merchant Incoming RFQs ──────

@router.get("/rfqs/merchant/{merchant_id}")
def get_merchant_rfqs(
    merchant_id: UUID,
    status: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    _require_merchant_role(db, merchant_id, user.id)

    where = "WHERE r.merchant_id=:mid"
    params: dict = {"mid": merchant_id}
    if status:
        where += " AND r.status=:status"
        params["status"] = status

    rows = db.execute(
        text(f"""
            SELECT r.*, p.name AS product_name, p.base_price_minor, p.category,
                   COALESCE(mi.available_quantity, 0) AS available_quantity,
                   COALESCE(mi.bulk_reserved_quantity, 0) AS bulk_reserved,
                   n.id AS negotiation_id, n.status AS neg_status,
                   n.final_unit_price_minor, n.final_total_minor
            FROM bulk_rfqs r
            JOIN merchant_products p ON p.id = r.product_id
            LEFT JOIN merchant_inventory mi ON mi.product_id = r.product_id
            LEFT JOIN bulk_negotiations n ON n.rfq_id = r.id
            {where}
            ORDER BY r.created_at DESC
            LIMIT 100
        """),
        params,
    ).mappings().fetchall()

    rfqs = []
    for r in rows:
        # Merchant-facing response: NEVER include private_max_budget or private_target
        rfqs.append({
            "rfq_id": str(r["id"]),
            "product_id": str(r["product_id"]),
            "product_name": r["product_name"],
            "base_price_minor": r["base_price_minor"],
            "base_price_inr": round(int(r["base_price_minor"] or 0) / 100, 2),
            "category": r["category"],
            "requested_quantity": r["requested_quantity"],
            "required_by": r["required_by"].isoformat() if r.get("required_by") else None,
            "delivery_mode": r["delivery_mode"],
            "negotiation_enabled": r["negotiation_enabled"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat(),
            "expires_at": r["expires_at"].isoformat(),
            "available_quantity": r["available_quantity"],
            "bulk_reserved": r["bulk_reserved"],
            "available_to_promise": max(0, int(r["available_quantity"]) - int(r["bulk_reserved"])),
            "negotiation_id": str(r["negotiation_id"]) if r.get("negotiation_id") else None,
            "neg_status": r.get("neg_status"),
            "final_unit_price_inr": round(int(r["final_unit_price_minor"] or 0) / 100, 2) if r.get("final_unit_price_minor") else None,
            "final_total_inr": round(int(r["final_total_minor"] or 0) / 100, 2) if r.get("final_total_minor") else None,
        })

    return {"merchant_id": str(merchant_id), "rfqs": rfqs, "total": len(rfqs)}


# ─── POST /api/bulk/rfqs/{rfq_id}/analyze — MerchantAgent Pricing Analysis ───

@router.post("/rfqs/{rfq_id}/analyze")
def analyze_rfq(
    rfq_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    rfq = _get_rfq(db, rfq_id)
    _require_merchant_role(db, UUID(str(rfq["merchant_id"])), user.id)

    product = db.execute(
        text("SELECT * FROM merchant_products WHERE id=:pid"),
        {"pid": rfq["product_id"]},
    ).mappings().one()
    product = dict(product)

    inventory = db.execute(
        text("""
            SELECT COALESCE(available_quantity, 0) AS available_quantity,
                   COALESCE(bulk_reserved_quantity, 0) AS bulk_reserved_quantity,
                   COALESCE(reserved_quantity, 0) AS reserved_quantity
            FROM merchant_inventory
            WHERE product_id=:pid AND merchant_id=:mid
        """),
        {"pid": rfq["product_id"], "mid": rfq["merchant_id"]},
    ).mappings().one_or_none()
    inventory = dict(inventory) if inventory else {}

    # Get active bulk policy for this product
    policy = db.execute(
        text("""
            SELECT * FROM bulk_policy_rules
            WHERE merchant_id=:mid AND (product_id=:pid OR product_id IS NULL)
              AND status='ACTIVE' AND approved_by_merchant=TRUE
            ORDER BY product_id DESC NULLS LAST
            LIMIT 1
        """),
        {"mid": rfq["merchant_id"], "pid": rfq["product_id"]},
    ).mappings().one_or_none()
    policy_dict = dict(policy) if policy else None

    # Run AI pricing optimization
    opt = BulkPricingOptimizer.optimize(
        rfq=dict(rfq),
        product=product,
        policy=policy_dict,
        inventory=inventory,
    )

    atp = InventoryReservationService.available_to_promise(
        db, UUID(str(rfq["product_id"])), UUID(str(rfq["merchant_id"]))
    )

    _emit(db, "BULK_PRICE_OPTIMIZED", rfq_id, UUID(str(rfq["merchant_id"])), {
        "recommended_discount_pct": opt.get("recommended_discount_pct"),
        "recommended_unit_price_inr": opt.get("recommended_unit_price_inr"),
    })

    return {
        "rfq_id": str(rfq_id),
        "product": {
            "id": str(product["id"]),
            "name": product["name"],
            "category": product["category"],
            "base_price_inr": round(int(product["base_price_minor"]) / 100, 2),
        },
        "inventory_analysis": {
            "available_quantity": inventory.get("available_quantity", 0),
            "bulk_reserved": inventory.get("bulk_reserved_quantity", 0),
            "available_to_promise": atp,
            "sufficient": atp >= rfq["requested_quantity"],
        },
        "pricing_optimization": opt,
        "ai_recommended_policy": BulkPolicyEngine.recommend(
            product, inventory, UUID(str(rfq["merchant_id"]))
        ) if not policy_dict else None,
        "active_policy": {
            "id": str(policy_dict["id"]),
            "max_discount_percent": policy_dict["max_discount_percent"],
            "min_margin_percent": policy_dict["min_margin_percent"],
        } if policy_dict else None,
    }


# ─── POST /api/bulk/rfqs/{rfq_id}/quote — MerchantAgent Send Quote ───────────

@router.post("/rfqs/{rfq_id}/quote")
def send_quote(
    rfq_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    rfq = _get_rfq(db, rfq_id)
    _require_merchant_role(db, UUID(str(rfq["merchant_id"])), user.id)

    if rfq["status"] not in ("SUBMITTED", "UNDER_REVIEW"):
        raise HTTPException(409, f"RFQ is in status {rfq['status']}, cannot quote")

    unit_price_minor = int(body["unit_price_minor"])
    quantity = int(body.get("quantity", rfq["requested_quantity"]))
    total_minor = unit_price_minor * quantity

    # Create negotiation if not exists
    neg = db.execute(
        text("SELECT id FROM bulk_negotiations WHERE rfq_id=:rfq"),
        {"rfq": rfq_id},
    ).mappings().one_or_none()

    if not neg:
        neg = db.execute(
            text("""
                INSERT INTO bulk_negotiations (rfq_id, status, rounds)
                VALUES (:rfq, 'OFFER_MADE', 1)
                RETURNING id
            """),
            {"rfq": rfq_id},
        ).mappings().one()
    else:
        db.execute(
            text("UPDATE bulk_negotiations SET status='OFFER_MADE', rounds=rounds+1, updated_at=now() WHERE id=:nid"),
            {"nid": neg["id"]},
        )

    neg_id = neg["id"]

    # Get current sequence
    seq = db.execute(
        text("SELECT COALESCE(MAX(sequence), 0) + 1 FROM bulk_negotiation_events WHERE negotiation_id=:neg"),
        {"neg": neg_id},
    ).scalar()

    db.execute(
        text("""
            INSERT INTO bulk_negotiation_events
                (negotiation_id, rfq_id, sequence, actor, offer_type, quantity, unit_price_minor, total_value_minor, message)
            VALUES (:neg, :rfq, :seq, 'MERCHANT_AGENT', 'QUOTE', :qty, :price, :total, :msg)
        """),
        {
            "neg": neg_id, "rfq": rfq_id, "seq": seq,
            "qty": quantity, "price": unit_price_minor, "total": total_minor,
            "msg": body.get("message", f"Quote: ₹{round(unit_price_minor/100,2)}/unit × {quantity} units"),
        },
    )

    db.execute(
        text("UPDATE bulk_rfqs SET status='QUOTED', updated_at=now() WHERE id=:rfq"),
        {"rfq": rfq_id},
    )
    db.commit()

    product = db.execute(
        text("SELECT name FROM merchant_products WHERE id=:pid"),
        {"pid": rfq["product_id"]},
    ).mappings().one_or_none()

    _emit(db, "BULK_QUOTE_MADE", rfq_id, UUID(str(rfq["merchant_id"])), {
        "unit_price_inr": round(unit_price_minor / 100, 2),
        "quantity": quantity,
        "total_inr": round(total_minor / 100, 2),
        "product_name": product["name"] if product else None,
    })

    # Auto-run BuyerAgent if negotiation_enabled
    buyer_response = None
    if rfq["negotiation_enabled"]:
        rfq_full = _get_rfq(db, rfq_id)
        buyer_eval = BuyerBulkAgent.evaluate_quote(
            rfq=dict(rfq_full),
            offered_unit_price_minor=unit_price_minor,
            offered_quantity=quantity,
            negotiation_round=1,
        )
        buyer_response = buyer_eval

        if buyer_eval["decision"] == "ACCEPT":
            # Buyer accepts immediately
            _auto_accept(db, rfq_id, neg_id, unit_price_minor, quantity, total_minor)
        elif buyer_eval["decision"] == "COUNTER":
            counter_price = buyer_eval["counter_unit_price_minor"]
            _record_buyer_counter(db, rfq_id, neg_id, counter_price, quantity, seq + 1)

    db.commit()
    return {
        "negotiation_id": str(neg_id),
        "rfq_id": str(rfq_id),
        "quote": {
            "unit_price_minor": unit_price_minor,
            "unit_price_inr": round(unit_price_minor / 100, 2),
            "quantity": quantity,
            "total_minor": total_minor,
            "total_inr": round(total_minor / 100, 2),
        },
        "buyer_agent_response": buyer_response,
        "status": "NEGOTIATING" if buyer_response and buyer_response["decision"] == "COUNTER" else
                  "ACCEPTED" if buyer_response and buyer_response["decision"] == "ACCEPT" else "QUOTED",
    }


def _record_buyer_counter(db: Session, rfq_id, neg_id, price, qty, seq):
    total = price * qty
    db.execute(
        text("""
            INSERT INTO bulk_negotiation_events
                (negotiation_id, rfq_id, sequence, actor, offer_type, quantity, unit_price_minor, total_value_minor, message)
            VALUES (:neg, :rfq, :seq, 'BUYER_AGENT', 'COUNTER', :qty, :price, :total, :msg)
        """),
        {
            "neg": neg_id, "rfq": rfq_id, "seq": seq,
            "qty": qty, "price": price, "total": total,
            "msg": f"BuyerAgent counter: ₹{round(price/100,2)}/unit",
        },
    )
    db.execute(
        text("UPDATE bulk_rfqs SET status='NEGOTIATING', updated_at=now() WHERE id=:rfq"),
        {"rfq": rfq_id},
    )
    db.execute(
        text("UPDATE bulk_negotiations SET status='COUNTERED', rounds=rounds+1, updated_at=now() WHERE id=:nid"),
        {"nid": neg_id},
    )
    dispatcher.emit("BULK_COUNTER_OFFER", {
        "rfq_id": str(rfq_id),
        "actor": "BUYER_AGENT",
        "counter_price_inr": round(price / 100, 2),
        "commerce_type": "BULK",
    })


def _auto_accept(db: Session, rfq_id, neg_id, price, qty, total):
    seq = db.execute(
        text("SELECT COALESCE(MAX(sequence), 0) + 1 FROM bulk_negotiation_events WHERE negotiation_id=:neg"),
        {"neg": neg_id},
    ).scalar()
    db.execute(
        text("""
            INSERT INTO bulk_negotiation_events
                (negotiation_id, rfq_id, sequence, actor, offer_type, quantity, unit_price_minor, total_value_minor, message)
            VALUES (:neg, :rfq, :seq, 'BUYER_AGENT', 'ACCEPT', :qty, :price, :total, :msg)
        """),
        {
            "neg": neg_id, "rfq": rfq_id, "seq": seq,
            "qty": qty, "price": price, "total": total,
            "msg": f"BuyerAgent accepted ₹{round(price/100,2)}/unit × {qty} = ₹{round(total/100,2)}",
        },
    )
    db.execute(
        text("""
            UPDATE bulk_negotiations
            SET status='ACCEPTED', final_unit_price_minor=:price,
                final_quantity=:qty, final_total_minor=:total, updated_at=now()
            WHERE id=:nid
        """),
        {"nid": neg_id, "price": price, "qty": qty, "total": total},
    )
    db.execute(
        text("UPDATE bulk_rfqs SET status='ACCEPTED', updated_at=now() WHERE id=:rfq"),
        {"rfq": rfq_id},
    )
    dispatcher.emit("BULK_OFFER_ACCEPTED", {
        "rfq_id": str(rfq_id),
        "unit_price_inr": round(price / 100, 2),
        "quantity": qty,
        "total_inr": round(total / 100, 2),
        "commerce_type": "BULK",
    })


# ─── POST /api/bulk/negotiations/{neg_id}/counter ─────────────────────────────

@router.post("/negotiations/{neg_id}/counter")
def counter_offer(
    neg_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    neg = _get_negotiation(db, neg_id)
    rfq = _get_rfq(db, UUID(str(neg["rfq_id"])))

    is_buyer = str(rfq["buyer_user_id"]) == str(user.id)
    is_merchant = db.execute(
        text("SELECT 1 FROM merchant_users WHERE merchant_id=:m AND user_id=:u"),
        {"m": rfq["merchant_id"], "u": user.id},
    ).scalar()

    if not is_buyer and not is_merchant:
        raise HTTPException(403, "Access denied")
    if neg["status"] not in ("STARTED", "OFFER_MADE", "COUNTERED"):
        raise HTTPException(409, f"Negotiation is in status {neg['status']}")

    actor = "BUYER_AGENT" if is_buyer else "MERCHANT_AGENT"
    unit_price = int(body["unit_price_minor"])
    quantity = int(body.get("quantity", rfq["requested_quantity"]))
    total = unit_price * quantity

    seq = db.execute(
        text("SELECT COALESCE(MAX(sequence), 0) + 1 FROM bulk_negotiation_events WHERE negotiation_id=:neg"),
        {"neg": neg_id},
    ).scalar()

    db.execute(
        text("""
            INSERT INTO bulk_negotiation_events
                (negotiation_id, rfq_id, sequence, actor, offer_type, quantity, unit_price_minor, total_value_minor, message)
            VALUES (:neg, :rfq, :seq, :actor, 'COUNTER', :qty, :price, :total, :msg)
        """),
        {
            "neg": neg_id, "rfq": rfq["id"], "seq": seq,
            "actor": actor, "qty": quantity, "price": unit_price, "total": total,
            "msg": body.get("message", f"{actor} counter: ₹{round(unit_price/100,2)}/unit"),
        },
    )
    db.execute(
        text("UPDATE bulk_negotiations SET status='COUNTERED', rounds=rounds+1, updated_at=now() WHERE id=:nid"),
        {"nid": neg_id},
    )
    db.execute(
        text("UPDATE bulk_rfqs SET status='NEGOTIATING', updated_at=now() WHERE id=:rfq"),
        {"rfq": rfq["id"]},
    )
    db.commit()

    dispatcher.emit("BULK_COUNTER_OFFER", {
        "rfq_id": str(rfq["id"]),
        "actor": actor,
        "unit_price_inr": round(unit_price / 100, 2),
        "quantity": quantity,
        "commerce_type": "BULK",
    })

    # Auto-respond with the other agent if applicable
    auto_response = None
    if actor == "BUYER_AGENT":
        # MerchantAgent evaluates
        product = db.execute(
            text("SELECT * FROM merchant_products WHERE id=:pid"),
            {"pid": rfq["product_id"]},
        ).mappings().one()
        opt = BulkPricingOptimizer.optimize(dict(rfq), dict(product), None, {
            "available_quantity": 9999, "bulk_reserved_quantity": 0
        })
        m_resp = MerchantBulkAgent.evaluate_counter(
            unit_price, quantity, None, opt,
            negotiation_round=int(neg["rounds"]) + 1,
        )
        auto_response = m_resp
        if m_resp["decision"] == "ACCEPT":
            final_p = m_resp.get("unit_price_minor", unit_price)
            final_t = final_p * quantity
            _auto_accept(db, UUID(str(rfq["id"])), neg_id, final_p, quantity, final_t)
        elif m_resp["decision"] == "COUNTER":
            m_price = m_resp["unit_price_minor"]
            _record_merchant_counter(db, UUID(str(rfq["id"])), neg_id, m_price, quantity, seq + 1)
        db.commit()
    elif actor == "MERCHANT_AGENT":
        # BuyerAgent evaluates the merchant counter
        rfq_full = _get_rfq(db, UUID(str(rfq["id"])))
        b_resp = BuyerBulkAgent.evaluate_quote(
            rfq=dict(rfq_full),
            offered_unit_price_minor=unit_price,
            offered_quantity=quantity,
            negotiation_round=int(neg["rounds"]) + 1,
        )
        auto_response = b_resp
        if b_resp["decision"] == "ACCEPT":
            _auto_accept(db, UUID(str(rfq["id"])), neg_id, unit_price, quantity, total)
        elif b_resp["decision"] == "COUNTER":
            _record_buyer_counter(db, UUID(str(rfq["id"])), neg_id, b_resp["counter_unit_price_minor"], quantity, seq + 1)
        db.commit()

    return {
        "negotiation_id": str(neg_id),
        "actor": actor,
        "counter": {"unit_price_minor": unit_price, "unit_price_inr": round(unit_price / 100, 2), "total_inr": round(total / 100, 2)},
        "auto_response": auto_response,
    }


def _record_merchant_counter(db, rfq_id, neg_id, price, qty, seq):
    total = price * qty
    db.execute(
        text("""
            INSERT INTO bulk_negotiation_events
                (negotiation_id, rfq_id, sequence, actor, offer_type, quantity, unit_price_minor, total_value_minor, message)
            VALUES (:neg, :rfq, :seq, 'MERCHANT_AGENT', 'COUNTER', :qty, :price, :total, :msg)
        """),
        {"neg": neg_id, "rfq": rfq_id, "seq": seq, "qty": qty, "price": price, "total": total,
         "msg": f"MerchantAgent counter: ₹{round(price/100,2)}/unit"},
    )
    db.execute(
        text("UPDATE bulk_negotiations SET status='COUNTERED', rounds=rounds+1, updated_at=now() WHERE id=:nid"),
        {"nid": neg_id},
    )
    dispatcher.emit("BULK_COUNTER_OFFER", {
        "rfq_id": str(rfq_id), "actor": "MERCHANT_AGENT",
        "unit_price_inr": round(price / 100, 2), "commerce_type": "BULK",
    })


# ─── POST /api/bulk/negotiations/{neg_id}/accept ─────────────────────────────

@router.post("/negotiations/{neg_id}/accept")
def accept_negotiation(
    neg_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    neg = _get_negotiation(db, neg_id)
    rfq = _get_rfq(db, UUID(str(neg["rfq_id"])))

    is_buyer = str(rfq["buyer_user_id"]) == str(user.id)
    is_merchant = db.execute(
        text("SELECT 1 FROM merchant_users WHERE merchant_id=:m AND user_id=:u"),
        {"m": rfq["merchant_id"], "u": user.id},
    ).scalar()
    if not is_buyer and not is_merchant:
        raise HTTPException(403, "Access denied")

    if neg["status"] == "ACCEPTED":
        # Already accepted — return reservation info
        reservation = db.execute(
            text("SELECT * FROM inventory_reservations WHERE negotiation_id=:nid AND status='ACTIVE'"),
            {"nid": neg_id},
        ).mappings().one_or_none()
        return {
            "negotiation_id": str(neg_id),
            "status": "ACCEPTED",
            "already_accepted": True,
            "reservation": dict(reservation) if reservation else None,
        }

    if neg["status"] not in ("OFFER_MADE", "COUNTERED", "STARTED"):
        raise HTTPException(409, f"Negotiation cannot be accepted in status {neg['status']}")

    # Get latest offer price
    latest_event = db.execute(
        text("""
            SELECT unit_price_minor, quantity FROM bulk_negotiation_events
            WHERE negotiation_id=:neg
            ORDER BY sequence DESC LIMIT 1
        """),
        {"neg": neg_id},
    ).mappings().one_or_none()

    final_price = int(body.get("unit_price_minor") or (latest_event["unit_price_minor"] if latest_event else 0))
    final_qty = int(body.get("quantity") or rfq["requested_quantity"])
    final_total = final_price * final_qty

    _auto_accept(db, UUID(str(rfq["id"])), neg_id, final_price, final_qty, final_total)

    # Create inventory reservation
    policy = db.execute(
        text("""
            SELECT reservation_duration_minutes FROM bulk_policy_rules
            WHERE merchant_id=:mid AND status='ACTIVE' AND approved_by_merchant=TRUE
            ORDER BY product_id DESC NULLS LAST LIMIT 1
        """),
        {"mid": rfq["merchant_id"]},
    ).mappings().one_or_none()
    duration = int(policy["reservation_duration_minutes"]) if policy else 15

    try:
        reservation = InventoryReservationService.reserve(
            db=db,
            product_id=UUID(str(rfq["product_id"])),
            merchant_id=UUID(str(rfq["merchant_id"])),
            quantity=final_qty,
            rfq_id=UUID(str(rfq["id"])),
            negotiation_id=neg_id,
            duration_minutes=duration,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    db.commit()

    dispatcher.emit("INVENTORY_RESERVED", {
        "rfq_id": str(rfq["id"]),
        "quantity": final_qty,
        "expires_in_minutes": duration,
        "commerce_type": "BULK",
    })

    return {
        "negotiation_id": str(neg_id),
        "rfq_id": str(rfq["id"]),
        "status": "ACCEPTED",
        "final_deal": {
            "unit_price_minor": final_price,
            "unit_price_inr": round(final_price / 100, 2),
            "quantity": final_qty,
            "total_minor": final_total,
            "total_inr": round(final_total / 100, 2),
        },
        "reservation": reservation,
        "next_step": "PROCEED_TO_PAYMENT",
        "product_id": str(rfq["product_id"]),
        "merchant_id": str(rfq["merchant_id"]),
    }


# ─── POST /api/bulk/negotiations/{neg_id}/reject ──────────────────────────────

@router.post("/negotiations/{neg_id}/reject")
def reject_negotiation(
    neg_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    neg = _get_negotiation(db, neg_id)
    rfq = _get_rfq(db, UUID(str(neg["rfq_id"])))

    is_buyer = str(rfq["buyer_user_id"]) == str(user.id)
    is_merchant = db.execute(
        text("SELECT 1 FROM merchant_users WHERE merchant_id=:m AND user_id=:u"),
        {"m": rfq["merchant_id"], "u": user.id},
    ).scalar()
    if not is_buyer and not is_merchant:
        raise HTTPException(403, "Access denied")

    db.execute(
        text("UPDATE bulk_negotiations SET status='REJECTED', updated_at=now() WHERE id=:nid"),
        {"nid": neg_id},
    )
    db.execute(
        text("UPDATE bulk_rfqs SET status='REJECTED', updated_at=now() WHERE id=:rfq"),
        {"rfq": rfq["id"]},
    )
    # Release any active reservation
    db.execute(
        text("UPDATE inventory_reservations SET status='RELEASED', updated_at=now() WHERE negotiation_id=:nid AND status='ACTIVE'"),
        {"nid": neg_id},
    )
    db.commit()
    return {"negotiation_id": str(neg_id), "status": "REJECTED"}


# ─── POST /api/bulk/quotes/simulate — Edit & Recalculate ─────────────────────

@router.post("/quotes/simulate")
def simulate_quote(
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """Merchant edits AI quote and sees recalculated EV, margin, acceptance."""
    merchant_id = UUID(str(body["merchant_id"]))
    _require_merchant_role(db, merchant_id, user.id)

    base_price = int(body.get("base_price_minor", 0))
    proposed_price = int(body.get("proposed_unit_price_minor", 0))
    quantity = int(body.get("quantity", 1))
    available = int(body.get("available_quantity", quantity))
    category = str(body.get("category", "General"))

    if base_price <= 0 or proposed_price <= 0:
        raise HTTPException(400, "base_price_minor and proposed_unit_price_minor required")

    from app.services.bulk_commerce_service import BulkPricingOptimizer as BPO
    cost_ratio = BPO._cost_ratio(category)
    cost_per_unit = int(base_price * cost_ratio)
    discount_pct = max(0.0, (base_price - proposed_price) / base_price * 100)
    acceptance = BPO._heuristic_acceptance_probability(discount_pct, quantity, available, base_price, None)
    contrib = (proposed_price - cost_per_unit) * quantity
    margin_pct = (proposed_price - cost_per_unit) / max(1, proposed_price) * 100

    return {
        "proposed_unit_price_minor": proposed_price,
        "proposed_unit_price_inr": round(proposed_price / 100, 2),
        "discount_pct": round(discount_pct, 2),
        "total_minor": proposed_price * quantity,
        "total_inr": round(proposed_price * quantity / 100, 2),
        "acceptance_probability_heuristic": acceptance,
        "contribution_margin_minor": contrib,
        "contribution_margin_inr": round(contrib / 100, 2),
        "margin_percent": round(margin_pct, 2),
        "model_type": "HEURISTIC",
    }


# ─── GET /api/bulk/opportunities/{merchant_id} ────────────────────────────────

@router.get("/opportunities/{merchant_id}")
def get_bulk_opportunities(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    _require_merchant_role(db, merchant_id, user.id)
    opportunities = BulkOpportunityDetector.detect(db, merchant_id)
    return {"merchant_id": str(merchant_id), "opportunities": opportunities, "total": len(opportunities)}


# ─── GET /api/bulk/analytics/{merchant_id} ────────────────────────────────────

@router.get("/analytics/{merchant_id}")
def get_bulk_analytics(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    _require_merchant_role(db, merchant_id, user.id)

    bulk_revenue = db.execute(
        text("""
            SELECT COALESCE(SUM(amount_minor), 0) AS total, COUNT(id) AS cnt
            FROM revenue_ledger
            WHERE merchant_id=:mid AND attribution_type IN ('AGENT_NEGOTIATED_BULK','DIRECT_BULK')
        """),
        {"mid": merchant_id},
    ).mappings().one()

    retail_revenue = db.execute(
        text("""
            SELECT COALESCE(SUM(amount_minor), 0) AS total, COUNT(id) AS cnt
            FROM revenue_ledger
            WHERE merchant_id=:mid AND attribution_type NOT IN ('AGENT_NEGOTIATED_BULK','DIRECT_BULK')
        """),
        {"mid": merchant_id},
    ).mappings().one()

    active_rfqs = db.execute(
        text("SELECT COUNT(id) FROM bulk_rfqs WHERE merchant_id=:mid AND status IN ('SUBMITTED','UNDER_REVIEW','QUOTED','NEGOTIATING')"),
        {"mid": merchant_id},
    ).scalar()

    active_negs = db.execute(
        text("""
            SELECT COUNT(n.id) FROM bulk_negotiations n
            JOIN bulk_rfqs r ON r.id=n.rfq_id
            WHERE r.merchant_id=:mid AND n.status IN ('STARTED','OFFER_MADE','COUNTERED')
        """),
        {"mid": merchant_id},
    ).scalar()

    bulk_orders = int(bulk_revenue["cnt"])
    retail_orders = int(retail_revenue["cnt"])
    bulk_total = int(bulk_revenue["total"])
    retail_total = int(retail_revenue["total"])

    return {
        "merchant_id": str(merchant_id),
        "bulk": {
            "revenue_minor": bulk_total,
            "revenue_inr": round(bulk_total / 100, 2),
            "orders": bulk_orders,
            "avg_order_value_inr": round(bulk_total / 100 / max(1, bulk_orders), 2),
        },
        "retail": {
            "revenue_minor": retail_total,
            "revenue_inr": round(retail_total / 100, 2),
            "orders": retail_orders,
            "avg_order_value_inr": round(retail_total / 100 / max(1, retail_orders), 2),
        },
        "total_revenue_inr": round((bulk_total + retail_total) / 100, 2),
        "active_rfqs": active_rfqs,
        "active_negotiations": active_negs,
    }


# ─── GET/POST /api/bulk/policies/{merchant_id} ───────────────────────────────

@router.get("/policies/{merchant_id}")
def get_bulk_policies(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    _require_merchant_role(db, merchant_id, user.id)
    rows = db.execute(
        text("""
            SELECT bp.*, mp.name AS product_name
            FROM bulk_policy_rules bp
            LEFT JOIN merchant_products mp ON mp.id = bp.product_id
            WHERE bp.merchant_id=:mid
            ORDER BY bp.created_at DESC
        """),
        {"mid": merchant_id},
    ).mappings().fetchall()
    return {"merchant_id": str(merchant_id), "policies": [dict(r) for r in rows]}


@router.post("/policies/{merchant_id}")
def create_bulk_policy(
    merchant_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    _require_merchant_role(db, merchant_id, user.id)
    row = db.execute(
        text("""
            INSERT INTO bulk_policy_rules (
                merchant_id, product_id, min_quantity, max_quantity,
                max_discount_percent, min_margin_percent,
                max_autonomous_order_value_minor, max_inventory_allocation_percent,
                reservation_duration_minutes, ai_recommended, ai_reasoning,
                status, approved_by_merchant
            ) VALUES (
                :mid, :pid, :min_qty, :max_qty,
                :max_disc, :min_margin,
                :max_val, :max_alloc,
                :res_dur, :ai_rec, :ai_reason,
                :status, :approved
            ) RETURNING id, status
        """),
        {
            "mid": merchant_id,
            "pid": body.get("product_id"),
            "min_qty": int(body.get("min_quantity", 1)),
            "max_qty": body.get("max_quantity"),
            "max_disc": float(body.get("max_discount_percent", 10.0)),
            "min_margin": float(body.get("min_margin_percent", 15.0)),
            "max_val": int(body.get("max_autonomous_order_value_minor", 10_000_000)),
            "max_alloc": float(body.get("max_inventory_allocation_percent", 60.0)),
            "res_dur": int(body.get("reservation_duration_minutes", 15)),
            "ai_rec": bool(body.get("ai_recommended", False)),
            "ai_reason": body.get("ai_reasoning"),
            "status": body.get("status", "ACTIVE"),
            "approved": bool(body.get("approved_by_merchant", True)),
        },
    ).mappings().one()
    db.commit()
    return {"policy_id": str(row["id"]), "status": row["status"]}


# ─── POST /api/bulk/products/{product_id}/bulk-enable ────────────────────────

@router.post("/products/{product_id}/bulk-enable")
def enable_bulk_for_product(
    product_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    product = db.execute(
        text("SELECT merchant_id FROM merchant_products WHERE id=:pid"),
        {"pid": product_id},
    ).mappings().one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    _require_merchant_role(db, UUID(str(product["merchant_id"])), user.id)

    db.execute(
        text("""
            UPDATE merchant_products
            SET bulk_enabled=:enabled, bulk_min_quantity=:min_qty,
                bulk_max_quantity=:max_qty, updated_at=now()
            WHERE id=:pid
        """),
        {
            "enabled": bool(body.get("bulk_enabled", True)),
            "min_qty": int(body.get("bulk_min_quantity", 50)),
            "max_qty": body.get("bulk_max_quantity"),
            "pid": product_id,
        },
    )
    db.commit()
    return {"product_id": str(product_id), "bulk_enabled": True}


# ─── GET /api/bulk/reservations/{product_id} ─────────────────────────────────

@router.get("/reservations/{product_id}")
def get_reservations(
    product_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    product = db.execute(
        text("SELECT merchant_id FROM merchant_products WHERE id=:pid"),
        {"pid": product_id},
    ).mappings().one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    _require_merchant_role(db, UUID(str(product["merchant_id"])), user.id)

    atp = InventoryReservationService.available_to_promise(
        db, product_id, UUID(str(product["merchant_id"]))
    )
    reservations = db.execute(
        text("""
            SELECT ir.*, r.requested_quantity AS rfq_quantity
            FROM inventory_reservations ir
            LEFT JOIN bulk_rfqs r ON r.id = ir.rfq_id
            WHERE ir.product_id=:pid
            ORDER BY ir.created_at DESC LIMIT 20
        """),
        {"pid": product_id},
    ).mappings().fetchall()

    return {
        "product_id": str(product_id),
        "available_to_promise": atp,
        "reservations": [dict(r) for r in reservations],
    }


# ─── POST /api/bulk/reservations/{reservation_id}/release ────────────────────

@router.post("/reservations/{reservation_id}/release")
def release_reservation(
    reservation_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    res = db.execute(
        text("SELECT * FROM inventory_reservations WHERE id=:rid"),
        {"rid": reservation_id},
    ).mappings().one_or_none()
    if not res:
        raise HTTPException(404, "Reservation not found")
    _require_merchant_role(db, UUID(str(res["merchant_id"])), user.id)

    InventoryReservationService.release(db, reservation_id)
    db.commit()
    dispatcher.emit("INVENTORY_RESERVATION_RELEASED", {
        "reservation_id": str(reservation_id),
        "product_id": str(res["product_id"]),
        "quantity": res["quantity"],
        "commerce_type": "BULK",
    })
    return {"reservation_id": str(reservation_id), "status": "RELEASED"}
