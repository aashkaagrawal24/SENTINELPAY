from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.payment_repository import SqlPaymentRepository
from app.db.session import get_db_session
from app.schemas.payment import PaymentCallback, PaymentStatus, RefundRequest
from app.schemas.phase9 import ProvenanceCreate
from app.services.audit_ledger import AuditLedgerService
from app.services.payment_service import PaymentService, RazorpayHttpProvider
from app.services.provenance_service import ProvenanceService

router = APIRouter(prefix="/api")


def payment_service(
    db: Session, settings: Settings, require_webhook: bool = False
) -> PaymentService:
    if not settings.razorpay_test_key_id or not settings.razorpay_test_key_secret:
        raise HTTPException(503, "Razorpay Test Mode credentials are not configured")
    if require_webhook and not settings.razorpay_webhook_secret:
        raise HTTPException(503, "Razorpay webhook secret is not configured")
    provider = RazorpayHttpProvider(
        settings.razorpay_test_key_id,
        settings.razorpay_test_key_secret.get_secret_value(),
        settings.razorpay_webhook_secret.get_secret_value()
        if settings.razorpay_webhook_secret
        else "",
        settings.razorpay_api_url,
        settings.payment_timeout_seconds,
    )
    return PaymentService(SqlPaymentRepository(db), provider)


def require_attempt_owner(db: Session, attempt_id: UUID, user_id: UUID) -> None:
    owned = db.execute(
        text(
            "select 1 from payment_attempts pa join transactions t on t.id=pa.transaction_id where pa.id=:attempt and t.user_id=:user"
        ),
        {"attempt": attempt_id, "user": user_id},
    ).scalar()
    if not owned:
        raise HTTPException(404, "Payment attempt not found")


@router.post("/payments/order")
def create_payment_order(
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    transaction_id = UUID(str(body["transaction_id"]))
    owned = db.execute(
        text("select 1 from transactions where id=:transaction and user_id=:user"),
        {"transaction": transaction_id, "user": user.id},
    ).scalar()
    if not owned:
        raise HTTPException(404, "Transaction not found")
    try:
        checkout = payment_service(db, settings).create_order(
            transaction_id, str(body["idempotency_key"])
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    AuditLedgerService().append(
        db,
        scope=f"TRANSACTION:{transaction_id}",
        event_type="PAYMENT_ORDER_CREATED",
        actor="PAYMENT_SERVICE",
        payload={
            "payment_attempt_id": str(checkout.payment_attempt_id),
            "amount_minor": checkout.amount_minor,
            "currency": checkout.currency,
            "test_mode": True,
        },
        user_id=user.id,
        transaction_id=transaction_id,
    )
    db.commit()
    return checkout


@router.post("/payments/verify")
def verify_payment_callback(
    body: PaymentCallback,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_attempt_owner(db, body.payment_attempt_id, user.id)
    try:
        attempt = payment_service(db, settings).verify_browser_callback(
            body.payment_attempt_id,
            body.razorpay_order_id,
            body.razorpay_payment_id,
            body.razorpay_signature,
        )
    except PermissionError as exc:
        raise HTTPException(400, str(exc)) from exc
    provenance_ids = []
    if attempt.status == PaymentStatus.CAPTURED:
        payment_provenance = ProvenanceService().create(
            db,
            ProvenanceCreate(
                entity_type="TRANSACTION",
                entity_id=attempt.transaction_id,
                field_name="captured_amount_minor",
                value_snapshot=attempt.amount_minor,
                unit=f"{attempt.currency}_MINOR",
                value_type="REAL_DATA",
                trust_class="RAZORPAY_VERIFIED",
                method="Trusted backend payment state verification",
                source="RAZORPAY_TEST_MODE",
                source_reference=attempt.razorpay_payment_id,
                financial_authority=True,
                user_id=user.id,
            ),
        )
        provenance_ids.append(str(payment_provenance["id"]))
    AuditLedgerService().append(
        db,
        scope=f"TRANSACTION:{attempt.transaction_id}",
        event_type="PAYMENT_CAPTURED" if attempt.status == PaymentStatus.CAPTURED else "PAYMENT_EVENT_RECEIVED",
        actor="PAYMENT_SERVICE",
        payload={"payment_attempt_id": str(attempt.id), "status": attempt.status},
        user_id=user.id,
        transaction_id=attempt.transaction_id,
        provenance_ids=provenance_ids,
    )
    if attempt.status == PaymentStatus.CAPTURED:
        # Determine attribution and record revenue
        transaction = db.execute(
            text("select cart_id, order_type, bulk_rfq_id from transactions where id=:tid"),
            {"tid": attempt.transaction_id}
        ).mappings().one()
        cart = db.execute(
            text("select merchant_id, subtotal_minor, discount_minor, campaign_id from carts where id=:cid"),
            {"cid": transaction["cart_id"]}
        ).mappings().one()
        
        # Bulk detection: if transaction has bulk_rfq_id, use bulk attribution
        order_type = transaction.get("order_type") or "RETAIL"
        bulk_rfq_id = transaction.get("bulk_rfq_id")
        
        if order_type == "BULK" or bulk_rfq_id:
            # Check if negotiation was involved
            has_negotiation = False
            if bulk_rfq_id:
                has_negotiation = db.execute(
                    text("SELECT 1 FROM bulk_negotiations WHERE rfq_id=:rfq AND status='ACCEPTED'"),
                    {"rfq": bulk_rfq_id},
                ).scalar()
            attr_type = "AGENT_NEGOTIATED_BULK" if has_negotiation else "DIRECT_BULK"
        else:
            attr_type = "DIRECT_PURCHASE"
            if cart["campaign_id"]:
                attr_type = "CAMPAIGN_INFLUENCED"
            elif cart["discount_minor"] > 0:
                attr_type = "AGENT_NEGOTIATED"
            
        try:
            with db.begin_nested():
                db.execute(text("""
                    INSERT INTO revenue_ledger 
                    (transaction_id, merchant_id, payment_attempt_id, amount_minor, currency, attribution_type, order_type)
                    VALUES (:tid, :mid, :paid, :amt, :curr, :attr, :otype)
                """), {
                    "tid": attempt.transaction_id,
                    "mid": cart["merchant_id"],
                    "paid": attempt.id,
                    "amt": attempt.amount_minor,
                    "curr": attempt.currency,
                    "attr": attr_type,
                    "otype": order_type,
                })
        except Exception:
            # Handle unique constraint violation gracefully if already inserted (idempotency)
            pass

        # Convert any active inventory reservation for this bulk RFQ
        if bulk_rfq_id:
            try:
                db.execute(
                    text("""
                        UPDATE inventory_reservations
                        SET status = 'CONVERTED', order_id = :txn, updated_at = now()
                        WHERE rfq_id = :rfq AND status = 'ACTIVE'
                    """),
                    {"rfq": bulk_rfq_id, "txn": attempt.transaction_id},
                )
                # Decrement physical inventory for converted reservations
                db.execute(
                    text("""
                        UPDATE merchant_inventory mi
                        SET available_quantity = GREATEST(0, mi.available_quantity - ir.quantity),
                            updated_at = now()
                        FROM inventory_reservations ir
                        WHERE ir.rfq_id = :rfq AND ir.product_id = mi.product_id
                          AND ir.status = 'CONVERTED'
                    """),
                    {"rfq": bulk_rfq_id},
                )
                # Mark RFQ as converted
                db.execute(
                    text("UPDATE bulk_rfqs SET status='CONVERTED_TO_ORDER', updated_at=now() WHERE id=:rfq"),
                    {"rfq": bulk_rfq_id},
                )
            except Exception:
                pass  # Non-critical — reservation bookkeeping must not block payment confirmation

        AuditLedgerService().append(
            db,
            scope=f"TRANSACTION:{attempt.transaction_id}",
            event_type="RECEIPT_GENERATED",
            actor="PAYMENT_SERVICE",
            payload={
                "payment_attempt_id": str(attempt.id),
                "test_mode": True,
                "receipt_kind": "VERIFIED_PAYMENT_EVIDENCE",
            },
            user_id=user.id,
            transaction_id=attempt.transaction_id,
            provenance_ids=provenance_ids,
        )
    db.commit()
    return {
        "payment_attempt_id": attempt.id,
        "status": attempt.status,
        "captured": attempt.status == PaymentStatus.CAPTURED,
        "source": "TRUSTED_BACKEND_VERIFICATION",
    }


@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(...),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    raw_body = await request.body()
    try:
        attempt = payment_service(db, settings, require_webhook=True).process_webhook(
            raw_body, x_razorpay_signature
        )
    except PermissionError as exc:
        raise HTTPException(400, str(exc)) from exc

    if attempt and attempt.status == PaymentStatus.CAPTURED:
        try:
            transaction = db.execute(
                text("select cart_id from transactions where id=:tid"),
                {"tid": attempt.transaction_id}
            ).mappings().one()
            cart = db.execute(
                text("select merchant_id, subtotal_minor, discount_minor, campaign_id from carts where id=:cid"),
                {"cid": transaction["cart_id"]}
            ).mappings().one()
            
            attr_type = "DIRECT_PURCHASE"
            if cart["campaign_id"]:
                attr_type = "CAMPAIGN_INFLUENCED"
            elif cart["discount_minor"] > 0:
                attr_type = "AGENT_NEGOTIATED"
                
            db.execute(text("""
                INSERT INTO revenue_ledger 
                (transaction_id, merchant_id, payment_attempt_id, amount_minor, currency, attribution_type)
                VALUES (:tid, :mid, :paid, :amt, :curr, :attr)
            """), {
                "tid": attempt.transaction_id,
                "mid": cart["merchant_id"],
                "paid": attempt.id,
                "amt": attempt.amount_minor,
                "curr": attempt.currency,
                "attr": attr_type
            })
            db.commit()
        except Exception:
            db.rollback()
            pass

    return {
        "accepted": True,
        "payment_attempt_id": attempt.id if attempt else None,
        "status": attempt.status if attempt else "IGNORED",
    }


@router.get("/payments/{attempt_id}/status")
def payment_status(
    attempt_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_attempt_owner(db, attempt_id, user.id)
    attempt = SqlPaymentRepository(db).get_attempt(attempt_id)
    if attempt.status == PaymentStatus.UNKNOWN and settings.razorpay_test_key_id:
        attempt = payment_service(db, settings).resolve_unknown(attempt_id)
    message = (
        "Payment state is being verified. SentinelPay will not retry until the previous attempt is resolved."
        if attempt.status == PaymentStatus.UNKNOWN
        else None
    )
    return {
        "payment_attempt_id": attempt.id,
        "transaction_id": attempt.transaction_id,
        "razorpay_order_id": attempt.razorpay_order_id,
        "razorpay_payment_id": attempt.razorpay_payment_id,
        "amount_minor": attempt.amount_minor,
        "currency": attempt.currency,
        "status": attempt.status,
        "message": message,
        "verified": attempt.status == PaymentStatus.CAPTURED,
    }


@router.post("/payments/refunds")
def create_refund(
    body: RefundRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_attempt_owner(db, body.payment_attempt_id, user.id)
    try:
        refund = payment_service(db, settings).create_refund(
            body.payment_attempt_id,
            user.id,
            body.amount_minor,
            body.reason,
            body.idempotency_key,
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    attempt = SqlPaymentRepository(db).get_attempt(body.payment_attempt_id)
    AuditLedgerService().append(
        db,
        scope=f"TRANSACTION:{attempt.transaction_id}",
        event_type="REFUND_REQUESTED",
        actor="PAYMENT_SERVICE",
        payload={
            "refund_id": str(refund.id),
            "amount_minor": refund.amount_minor,
            "currency": refund.currency,
            "status": refund.status,
            "test_mode": True,
        },
        user_id=user.id,
        transaction_id=attempt.transaction_id,
    )
    db.commit()
    return refund


@router.get("/payments/refunds/{refund_id}")
def refund_status(
    refund_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    owned = db.execute(
        text("select 1 from refunds where id=:refund and user_id=:user"),
        {"refund": refund_id, "user": user.id},
    ).scalar()
    if not owned:
        raise HTTPException(404, "Refund not found")
    refund = payment_service(db, settings).reconcile_refund(refund_id)
    return refund


@router.post("/payments/{attempt_id}/reconcile")
def reconcile_payment(
    attempt_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    require_attempt_owner(db, attempt_id, user.id)
    attempt = payment_service(db, settings).reconcile_payment(attempt_id)
    AuditLedgerService().append(
        db,
        scope=f"TRANSACTION:{attempt.transaction_id}",
        event_type="PAYMENT_RECONCILED",
        actor="PAYMENT_SERVICE",
        payload={"payment_attempt_id": str(attempt.id), "status": attempt.status},
        user_id=user.id,
        transaction_id=attempt.transaction_id,
    )
    db.commit()
    return {
        "payment_attempt_id": attempt.id,
        "status": attempt.status,
        "resolution": "MANUAL_REVIEW" if attempt.status == PaymentStatus.UNKNOWN else "RESOLVED",
    }
